# Plan: Dynamic TA-Lib Indicators

Replace hardcoded indicator plugins with config-driven TA-Lib indicators.

## Overview

| Phase | Goal | Risk | Changes |
|-------|------|------|---------|
| **Phase 1** | Use TA-Lib for compute() | Low | Update 7 plugins, keep signal/filter logic |
| **Phase 2** | Config-driven generic solution | Medium | Delete plugins, expression-based rules |
| **Phase 3** | Advanced patterns & regime detection | Low | Add candlestick patterns, volume, regime switching |

## Current State

- 14 indicator plugin files in `_components/indicators/plugins/`
- 7 hardcoded config dataclasses (`RSIConfig`, `MACDConfig`, etc.)
- Manual parsing for each indicator in `config.py`
- Each indicator implements: `compute()`, `get_signal()`, `filter_signal()`

## Goal

- Single `TALibIndicator` class that wraps any TA-Lib function
- Config-driven signal and filter rules (no code changes to add indicators)
- Access to all 158 TA-Lib indicators automatically

---

## Phase 1: Replace compute() with TA-Lib

**Goal**: Use TA-Lib for calculations, keep existing plugin structure and signal/filter logic.

**Risk**: Low - same API, just faster/cleaner compute()

### Changes

Replace manual calculations with TA-Lib calls in each plugin:

```python
# Before (rsi.py)
def compute(self, df: pl.DataFrame) -> pl.DataFrame:
    delta = df["close"].diff()
    gains = delta.clip(lower_bound=0)
    losses = (-delta).clip(lower_bound=0)
    avg_gain = gains.rolling_mean(window_size=self._period)
    avg_loss = losses.rolling_mean(window_size=self._period)
    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return df.with_columns(rsi.alias("rsi"))

# After (rsi.py)
import talib

def compute(self, df: pl.DataFrame) -> pl.DataFrame:
    rsi = talib.RSI(df["close"], timeperiod=self._period)
    return df.with_columns(rsi.alias("rsi"))
```

### Indicators to Update

| Indicator | TA-Lib Function | Notes |
|-----------|-----------------|-------|
| RSI | `talib.RSI(close, timeperiod)` | Direct replacement |
| MACD | `talib.MACD(close, fastperiod, slowperiod, signalperiod)` | Returns 3 arrays |
| ADX | `talib.ADX(high, low, close, timeperiod)` | Also need PLUS_DI, MINUS_DI |
| Bollinger | `talib.BBANDS(close, timeperiod, nbdevup, nbdevdn)` | Returns upper, middle, lower |
| EMA Crossover | `talib.EMA(close, timeperiod)` | Call twice for fast/slow |
| Stochastic | `talib.STOCH(high, low, close, ...)` | Returns slowk, slowd |
| Keltner | `talib.EMA` + `talib.ATR` | Combine two functions |
| VWAP Bands | Manual | TA-Lib doesn't have VWAP |
| Pivot Points | Manual | TA-Lib doesn't have pivots |
| Fibonacci | Manual | TA-Lib doesn't have fib levels |
| Volume Profile | Manual | TA-Lib doesn't have this |

### Steps

1. Add TA-Lib dependency
   ```bash
   brew install ta-lib
   uv add ta-lib
   ```

2. Update each plugin's `compute()` method (keep `get_signal()` and `filter_signal()` unchanged)

3. Run tests to verify identical behavior

4. Benchmark to confirm performance improvement

### Benefits

- Faster execution (C library)
- Less code in compute() methods
- Battle-tested calculations
- No API changes - all tests should pass

---

## Phase 2: Config-Driven Generic Indicators

**Goal**: Replace all plugin files with single dynamic class + config-driven rules.

**Risk**: Medium - changes API and config schema

## TA-Lib Python Support

TA-Lib Python (v0.6+) natively supports Polars:
```python
import talib
from talib import abstract

# Direct usage with Polars Series
rsi = talib.RSI(df["close"], timeperiod=14)  # Returns Polars Series

# Abstract API for introspection
func = abstract.Function("RSI")
func.input_names      # ['close']
func.output_names     # ['real']
func.parameters       # {'timeperiod': 14}
```

## Config Schema

```toml
[tradingbot.strategy.indicators]
enabled = ["rsi", "macd", "adx", "bbands"]  # Any TA-Lib function name
filter_mode = "all"    # all | any
signal_mode = "filter" # filter | signal | both

# TA-Lib params at top level (use TA-Lib's exact param names)
[tradingbot.strategy.indicators.rsi]
timeperiod = 14

# Signal rules: conditions that generate BUY/SELL
[tradingbot.strategy.indicators.rsi.signal]
buy = "rsi_real crosses_above 30"
sell = "rsi_real crosses_below 70"

# Filter rules: conditions that must pass for signal to be allowed
[tradingbot.strategy.indicators.rsi.filter]
buy = "rsi_real < 70"
sell = "rsi_real > 30"

[tradingbot.strategy.indicators.macd]
fastperiod = 12
slowperiod = 26
signalperiod = 9

[tradingbot.strategy.indicators.macd.signal]
buy = "macd_macd crosses_above macd_macdsignal"
sell = "macd_macd crosses_below macd_macdsignal"

[tradingbot.strategy.indicators.macd.filter]
buy = "macd_macdhist > 0"
sell = "macd_macdhist < 0"

[tradingbot.strategy.indicators.adx]
timeperiod = 14

# Array = AND (all conditions must be true)
[tradingbot.strategy.indicators.adx.signal]
buy = ["adx_plus_di crosses_above adx_minus_di", "adx_real > 25"]
sell = ["adx_minus_di crosses_above adx_plus_di", "adx_real > 25"]

[tradingbot.strategy.indicators.adx.filter]
buy = "adx_plus_di > adx_minus_di"
sell = "adx_minus_di > adx_plus_di"

# Filter-only indicator (no signal generation)
[tradingbot.strategy.indicators.bbands]
timeperiod = 20
nbdevup = 2.0
nbdevdn = 2.0

[tradingbot.strategy.indicators.bbands.filter]
all = "close < bbands_upperband"  # Block all signals if price at upper band
```

## Expression Syntax

**Operators:**
- Comparison: `<`, `>`, `<=`, `>=`, `==`, `!=`
- Crossover: `crosses_above`, `crosses_below`

**Operands:**
- Column names: `rsi_real`, `macd_macd`, `close`, `high`, `low`
- Numeric literals: `30`, `70`, `25.0`

**Column naming convention:**
- TA-Lib outputs: `{indicator}_{output}` (e.g., `rsi_real`, `macd_macdsignal`)
- OHLCV columns: `open`, `high`, `low`, `close`, `volume`

**Compound conditions:**
- Array syntax: `["condition1", "condition2"]` (all must pass)

## Implementation

### 1. Expression Parser

```python
# src/tradingbot/_components/indicators/expression.py

@dataclass
class Condition:
    left: str       # Column name or value
    op: str         # Operator
    right: str      # Column name or value

def parse_expression(expr: str) -> Condition:
    """Parse 'rsi_real < 70' into Condition."""
    parts = expr.split()
    return Condition(left=parts[0], op=parts[1], right=parts[2])

def eval_condition(cond: Condition, df: pl.DataFrame, idx: int) -> bool:
    """Evaluate condition at index."""
    left_val = _get_value(cond.left, df, idx)
    right_val = _get_value(cond.right, df, idx)

    match cond.op:
        case "<": return left_val < right_val
        case ">": return left_val > right_val
        case "<=": return left_val <= right_val
        case ">=": return left_val >= right_val
        case "==": return left_val == right_val
        case "!=": return left_val != right_val
        case "crosses_above":
            left_prev = _get_value(cond.left, df, idx - 1)
            right_prev = _get_value(cond.right, df, idx - 1)
            return left_prev <= right_prev and left_val > right_val
        case "crosses_below":
            left_prev = _get_value(cond.left, df, idx - 1)
            right_prev = _get_value(cond.right, df, idx - 1)
            return left_prev >= right_prev and left_val < right_val
    return False

def _get_value(token: str, df: pl.DataFrame, idx: int) -> float:
    """Get value from column or parse as literal."""
    if token in df.columns:
        return df[token][idx]
    return float(token)
```

### 2. Dynamic Indicator Class

```python
# src/tradingbot/_components/indicators/talib_indicator.py

from talib import abstract
import polars as pl
from tradingbot.types import Signal
from .expression import parse_expression, eval_condition

class TALibIndicator:
    """Universal wrapper for any TA-Lib indicator."""

    def __init__(self, name: str, config: dict):
        self._name = name.upper()
        self._func = abstract.Function(self._name)

        # Separate TA-Lib params from signal/filter config
        talib_params = self._func.parameters.keys()
        self._params = {k: v for k, v in config.items()
                       if k in talib_params}
        self._signal_config = config.get("signal", {})
        self._filter_config = config.get("filter", {})

        self._func.set_parameters(self._params)

    @property
    def name(self) -> str:
        return self._name.lower()

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add indicator columns to DataFrame."""
        # Build inputs from DataFrame
        inputs = {}
        for inp in self._func.input_names:
            if inp in df.columns:
                inputs[inp] = df[inp]
            elif inp == "prices":  # Some functions use 'prices' for close
                inputs[inp] = df["close"]

        result = self._func(inputs)

        # Add output columns with prefix
        outputs = result if isinstance(result, tuple) else (result,)
        for col_name, values in zip(self._func.output_names, outputs):
            df = df.with_columns(values.alias(f"{self.name}_{col_name}"))

        return df

    def get_signal(self, df: pl.DataFrame, idx: int) -> Signal | None:
        """Generate signal from crossover conditions."""
        if idx < 1:
            return None

        for direction in ("buy", "sell"):
            exprs = self._signal_config.get(direction, [])
            if isinstance(exprs, str):
                exprs = [exprs]

            if exprs and all(self._eval_expr(e, df, idx) for e in exprs):
                return Signal.BUY if direction == "buy" else Signal.SELL

        return None

    def filter_signal(self, signal: Signal, df: pl.DataFrame, idx: int) -> bool:
        """Filter signal based on conditions."""
        direction = "buy" if signal == Signal.BUY else "sell"

        # Check direction-specific filter
        exprs = self._filter_config.get(direction, [])
        if isinstance(exprs, str):
            exprs = [exprs]

        # Check 'all' filter (applies to both directions)
        all_exprs = self._filter_config.get("all", [])
        if isinstance(all_exprs, str):
            all_exprs = [all_exprs]

        combined = exprs + all_exprs
        return all(self._eval_expr(e, df, idx) for e in combined) if combined else True

    def _eval_expr(self, expr: str, df: pl.DataFrame, idx: int) -> bool:
        cond = parse_expression(expr)
        return eval_condition(cond, df, idx)
```

### 3. Factory Function

```python
# src/tradingbot/_components/indicators/factory.py

from talib import get_functions
from .talib_indicator import TALibIndicator

TALIB_FUNCTIONS = set(f.lower() for f in get_functions())

def create_indicator(name: str, config: dict) -> TALibIndicator:
    """Create indicator from config."""
    if name.lower() not in TALIB_FUNCTIONS:
        raise ValueError(f"Unknown TA-Lib indicator: {name}")
    return TALibIndicator(name, config)

def create_indicators(indicators_config: dict) -> list[TALibIndicator]:
    """Create all enabled indicators from config."""
    enabled = indicators_config.get("enabled", [])
    return [
        create_indicator(name, indicators_config.get(name, {}))
        for name in enabled
    ]
```

### 4. Config Parsing

```python
# Update config.py

@dataclass(frozen=True)
class IndicatorConfig:
    enabled: list[str] = field(default_factory=list)
    filter_mode: str = "all"
    signal_mode: str = "filter"
    indicators: dict[str, dict] = field(default_factory=dict)  # Raw config per indicator

def _parse_indicator_config(ind_data: dict) -> IndicatorConfig:
    """Parse indicator config, preserving raw indicator sections."""
    enabled = ind_data.get("enabled", [])
    filter_mode = ind_data.get("filter_mode", "all")
    signal_mode = ind_data.get("signal_mode", "filter")

    # Collect all indicator-specific configs
    indicators = {}
    for name in enabled:
        if name in ind_data:
            indicators[name] = ind_data[name]

    return IndicatorConfig(
        enabled=enabled,
        filter_mode=filter_mode,
        signal_mode=signal_mode,
        indicators=indicators,
    )
```

## Phase 2 Migration Steps

1. **Create new modules**
   - `_components/indicators/expression.py` - Expression parser
   - `_components/indicators/talib_indicator.py` - Dynamic indicator class
   - `_components/indicators/factory.py` - Factory functions

2. **Update config parsing**
   - Simplify `IndicatorConfig` to store raw dicts
   - Remove individual `*Config` dataclasses (RSIConfig, MACDConfig, etc.)

3. **Update strategy to use factory**
   - Replace registry lookup with `create_indicators(config)`

4. **Migrate existing config**
   - Convert current TOML sections to new schema
   - Add signal/filter subsections

5. **Delete old plugin files**
   - Remove 14 files from `_components/indicators/plugins/`

6. **Update tests**
   - Test expression parser
   - Test dynamic indicator creation
   - Test signal/filter evaluation

7. **Keep manual indicators** (not in TA-Lib)
   - VWAP Bands, Pivot Points, Fibonacci, Volume Profile
   - These remain as custom plugins or get expression-based compute()

## Benefits

- **158 indicators available** without writing any wrapper code
- **Config-driven** - add indicators without code changes
- **Flexible** - traders define their own signal/filter rules
- **Less code** - delete ~1000 lines of plugin code
- **Battle-tested math** - TA-Lib is industry standard since 1999

## Considerations

- **TA-Lib installation** - requires C library (brew install ta-lib)
- **Column naming** - must match TA-Lib output names
- **Expression validation** - should validate at config load time
- **Error messages** - need clear errors for invalid expressions

---

## Phase 3: Advanced Patterns & Regime Detection

**Goal**: Leverage TA-Lib's full capabilities - candlestick patterns, volume indicators, and regime-based strategy switching.

**Risk**: Low - builds on Phase 2 infrastructure

**Prereq**: Phase 2 completed

### 3.1 Candlestick Pattern Recognition

TA-Lib has 61 candlestick patterns. Add as entry signals or filters.

**Pattern Categories:**

| Category | Patterns | Use Case |
|----------|----------|----------|
| Bullish Reversal | Hammer, Morning Star, Engulfing, Piercing | BUY at support |
| Bearish Reversal | Shooting Star, Evening Star, Dark Cloud | SELL at resistance |
| Continuation | Three White Soldiers, Three Black Crows | Trend confirmation |
| Indecision | Doji, Spinning Top | Wait / tighten stops |

**Key Patterns:**

```
Hammer (Bullish)          Shooting Star (Bearish)    Engulfing (Both)
                                  │
    │                            ┌┴┐                  ┌───┐
   ┌┴┐                           │ │                  │   │
   │ │                           └┬┘                ┌─┴───┴─┐
   └┬┘                            │                 │       │
    │                             │                 └───────┘
    │                             │
```

**Config Example:**

```toml
[tradingbot.strategy.indicators]
enabled = ["rsi", "adx", "cdlhammer", "cdlshootingstar", "cdlengulfing"]

# Hammer - bullish reversal at bottoms
[tradingbot.strategy.indicators.cdlhammer]
[tradingbot.strategy.indicators.cdlhammer.signal]
buy = ["cdlhammer_integer == 100", "rsi < 40", "adx < 30"]

# Shooting Star - bearish reversal at tops
[tradingbot.strategy.indicators.cdlshootingstar]
[tradingbot.strategy.indicators.cdlshootingstar.signal]
sell = ["cdlshootingstar_integer == -100", "rsi > 60", "adx < 30"]

# Engulfing - works both directions
[tradingbot.strategy.indicators.cdlengulfing]
[tradingbot.strategy.indicators.cdlengulfing.signal]
buy = "cdlengulfing_integer == 100"
sell = "cdlengulfing_integer == -100"
```

**High-Value Patterns to Implement First:**

| Pattern | TA-Lib Function | Signal Value | Best Context |
|---------|-----------------|--------------|--------------|
| Hammer | `CDLHAMMER` | 100 | Oversold + support |
| Inverted Hammer | `CDLINVERTEDHAMMER` | 100 | Oversold + support |
| Shooting Star | `CDLSHOOTINGSTAR` | -100 | Overbought + resistance |
| Hanging Man | `CDLHANGINGMAN` | -100 | Overbought + resistance |
| Engulfing | `CDLENGULFING` | ±100 | Reversal zones |
| Morning Star | `CDLMORNINGSTAR` | 100 | Strong bullish reversal |
| Evening Star | `CDLEVENINGSTAR` | -100 | Strong bearish reversal |
| Doji | `CDLDOJI` | 100 | Indecision, wait |

### 3.2 Volume Confirmation

Add volume-based filters to confirm price moves.

**Volume Indicators:**

| Indicator | TA-Lib | Use |
|-----------|--------|-----|
| OBV | `OBV` | Trend confirmation (OBV should confirm price direction) |
| AD | `AD` | Accumulation/Distribution |
| ADOSC | `ADOSC` | A/D Oscillator |
| MFI | `MFI` | Volume-weighted RSI (money flow) |

**Config Example:**

```toml
[tradingbot.strategy.indicators.obv]
# On Balance Volume - no params

[tradingbot.strategy.indicators.obv.filter]
# OBV should be rising for buys, falling for sells
buy = "obv > obv_sma20"    # Need to compute OBV's SMA separately
sell = "obv < obv_sma20"

[tradingbot.strategy.indicators.mfi]
timeperiod = 14

[tradingbot.strategy.indicators.mfi.filter]
buy = "mfi < 80"    # Not overbought on volume
sell = "mfi > 20"   # Not oversold on volume

[tradingbot.strategy.indicators.mfi.signal]
buy = "mfi crosses_above 20"   # Emerging from oversold
sell = "mfi crosses_below 80"  # Dropping from overbought
```

### 3.3 Regime Detection

Switch indicator sets based on market regime (trending vs ranging).

**Concept:**

```
Market Regime
     │
     ├── Trending (ADX > 25)
     │   └── Use: MACD, ADX, EMA crossover
     │       Strategy: Trend-following
     │
     └── Ranging (ADX < 20)
         └── Use: RSI, Bollinger, Stochastic
             Strategy: Mean-reversion
```

**Config Schema:**

```toml
[tradingbot.strategy.regime]
enabled = true
detector = "adx"  # Indicator used for regime detection

[tradingbot.strategy.regime.trending]
condition = "adx > 25"
indicators = ["macd", "adx", "ema_crossover"]
entry = "swing_break"

[tradingbot.strategy.regime.ranging]
condition = "adx < 20"
indicators = ["rsi", "bbands", "stochastic"]
entry = "vwap_reversion"

[tradingbot.strategy.regime.neutral]
# ADX between 20-25
condition = "adx >= 20 AND adx <= 25"
indicators = ["rsi"]  # Conservative
entry = "swing_break"
```

**Implementation:**

```python
class RegimeDetector:
    def __init__(self, config: dict):
        self._regimes = config.get("regime", {})

    def detect_regime(self, df: pl.DataFrame, idx: int) -> str:
        """Return current regime: 'trending', 'ranging', or 'neutral'."""
        for regime_name, regime_config in self._regimes.items():
            if regime_name in ("enabled", "detector"):
                continue
            condition = regime_config.get("condition", "")
            if eval_condition(parse_expression(condition), df, idx):
                return regime_name
        return "neutral"

    def get_indicators_for_regime(self, regime: str) -> list[str]:
        """Get indicator list for current regime."""
        return self._regimes.get(regime, {}).get("indicators", [])
```

### 3.4 Volatility Filters

Filter trades based on volatility conditions.

```toml
[tradingbot.strategy.indicators.atr]
timeperiod = 14

[tradingbot.strategy.indicators.atr.filter]
# Skip very low volatility (dead market) and extreme volatility (chaos)
all = ["natr > 0.5", "natr < 5.0"]

[tradingbot.strategy.indicators.natr]
timeperiod = 14
# Normalized ATR (percentage) for cross-asset comparison
```

### 3.5 Multi-Pattern Confluence

Combine patterns with indicators for higher-probability setups.

```toml
[tradingbot.strategy.confluence]
# Require multiple confirmations for entry
min_confirmations = 3

[tradingbot.strategy.confluence.buy]
signals = [
    "cdlhammer_integer == 100",      # Hammer pattern
    "rsi < 35",                       # Oversold
    "close < bbands_lowerband",       # At lower Bollinger
    "adx < 25",                       # Not strong downtrend
    "obv > obv_sma20",               # Volume confirming
]

[tradingbot.strategy.confluence.sell]
signals = [
    "cdlshootingstar_integer == -100",  # Shooting star
    "rsi > 65",                          # Overbought
    "close > bbands_upperband",          # At upper Bollinger
    "adx < 25",                          # Not strong uptrend
]
```

### Phase 3 Migration Steps

1. **Add pattern indicators to config**
   - Enable candlestick patterns in `enabled` list
   - Add signal/filter conditions

2. **Add volume indicators**
   - OBV, MFI, AD as filter confirmations

3. **Implement regime detection** (optional)
   - Add `RegimeDetector` class
   - Switch indicators based on market state

4. **Add confluence scoring** (optional)
   - Count confirmations before entry
   - Require minimum score

5. **Backtest pattern performance**
   - Test individual patterns
   - Test pattern + indicator combinations
   - Find optimal contexts for each pattern

### Phase 3 Benefits

- **61 candlestick patterns** available as signals/filters
- **Volume confirmation** reduces false signals
- **Regime adaptation** uses right strategy for market conditions
- **Confluence scoring** improves win rate by requiring multiple confirmations
- **All config-driven** - no code changes to add new setups

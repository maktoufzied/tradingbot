# Quick Fixes - Immediate Improvements

This document contains quick fixes that can be applied immediately to improve code quality.

## 1. Add Logging to Core Modules

**Files to update:**
- `src/tradingbot/_components/engine/engine.py`
- `src/tradingbot/_components/bot.py`
- `src/tradingbot/_components/signals.py`
- `src/tradingbot/_components/risk.py`

**Action:** Add logging import and logger at top of each file:
```python
import logging
logger = logging.getLogger(__name__)
```

## 2. Improve Error Handling in Engine

**File:** `src/tradingbot/_components/engine/engine.py:196`

**Current:**
```python
except Exception as e:
    await self._emit_message(f"✗ {symbol}: {e}", MessageLevel.ERROR)
```

**Fix:**
```python
except (ValueError, ConnectionError, TimeoutError) as e:
    await self._emit_message(f"✗ {symbol}: Failed to load history: {e}", MessageLevel.ERROR)
    logger.exception(f"Error loading history for {symbol}")
except Exception as e:
    await self._emit_message(f"✗ {symbol}: Unexpected error: {e}", MessageLevel.ERROR)
    logger.exception(f"Unexpected error loading history for {symbol}", exc_info=True)
```

## 3. Add Input Validation to PositionSizer

**File:** `src/tradingbot/_components/risk.py`

**Add validation:**
```python
def calc_size(self, entry: float, stop: float) -> float:
    """Calculate position size based on risk amount and stop distance."""
    if entry <= 0:
        raise ValueError(f"Entry price must be positive, got {entry}")
    if stop <= 0:
        raise ValueError(f"Stop price must be positive, got {stop}")
    if entry == stop:
        raise ValueError("Entry and stop prices cannot be equal")
    
    risk_amt: float = self.capital * self.risk_pct
    risk_per_unit: float = abs(entry - stop)
    if risk_per_unit == 0:
        return 0.0
    size = risk_amt / risk_per_unit
    return float(int(size))  # Round down to whole shares
```

## 4. Add Config Validation

**File:** `src/tradingbot/config.py`

**Add after `_parse_config` function:**
```python
def _validate_config(config: Config) -> None:
    """Validate configuration values."""
    if not 0 < config.strategy.risk_pct <= 1.0:
        raise ValueError(
            f"risk_pct must be between 0 and 1, got {config.strategy.risk_pct}"
        )
    if config.strategy.rr_ratio <= 0:
        raise ValueError(
            f"rr_ratio must be positive, got {config.strategy.rr_ratio}"
        )
    if config.strategy.swing_lb < 1:
        raise ValueError(
            f"swing_lb must be at least 1, got {config.strategy.swing_lb}"
        )
    if config.bot.capital <= 0:
        raise ValueError(
            f"capital must be positive, got {config.bot.capital}"
        )
```

**Update `_parse_config` to call validation:**
```python
def _parse_config(data: dict[str, Any]) -> Config:
    # ... existing code ...
    config = Config(...)
    _validate_config(config)
    return config
```

## 5. Add API Key Security Warning

**File:** `src/tradingbot/_components/brokers/plugins/alpaca.py`

**Update `_get_client` method:**
```python
def _get_client(self) -> TradingClient:
    """Get or create the Alpaca trading client (lazy initialization)."""
    if self._client is not None:
        return self._client

    config = get_engine_config().alpaca

    # Environment variables take priority over config file
    api_key = os.environ.get(ALPACA_API_KEY_ENV) or config.api_key
    secret_key = os.environ.get(ALPACA_SECRET_KEY_ENV) or config.secret_key
    
    # Security warning if keys in config
    if config.api_key and not os.environ.get(ALPACA_API_KEY_ENV):
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            "API key found in config file. For security, use environment variables instead. "
            "Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables."
        )
    
    paper_env = os.environ.get(ALPACA_PAPER_ENV)
    self._paper = paper_env.lower() == "true" if paper_env else config.paper

    if not api_key or not secret_key:
        raise ValueError(
            f"Alpaca API credentials not found. "
            f"Set {ALPACA_API_KEY_ENV} and {ALPACA_SECRET_KEY_ENV} environment variables, "
            f"or configure in tradingbot.toml under [tradingbot.engine.alpaca]."
        )

    self._client = TradingClient(api_key, secret_key, paper=self._paper)
    return self._client
```

## 6. Fix String Parsing in Optimizer

**File:** `src/tradingbot/_components/optimizer.py`

**Issue:** Parsing formatted strings is fragile.

**Better approach:** Modify `bot.py` to return raw numbers, format only for display.

**Quick fix (if can't change bot.py immediately):**
```python
def _parse_stat_value(value: str, suffix: str = "%") -> float:
    """Parse a formatted stat value (e.g., "30.0%" -> 30.0)."""
    if isinstance(value, (int, float)):
        return float(value)
    value_str = str(value).rstrip(suffix).strip()
    try:
        return float(value_str)
    except ValueError as e:
        raise ValueError(f"Could not parse stat value: {value}") from e

# Then use:
win_rate = _parse_stat_value(stats["win_rate"])
total_return = _parse_stat_value(stats["total_return"])
profit_factor = 999.0 if str(stats["profit_factor"]).lower() == "inf" else _parse_stat_value(str(stats["profit_factor"]), suffix="")
max_dd = _parse_stat_value(stats["max_drawdown"])
```

## 7. Add Constants Module

**Create:** `src/tradingbot/constants.py`

```python
"""Constants used throughout the trading bot."""

from typing import Final

# Engine constants
MIN_BARS_REQUIRED: Final[int] = 50
MAX_BARS_HISTORY: Final[int] = 500

# Optimizer constants
DEFAULT_OPTIMIZATION_WORKERS: Final[int] = 4

# Risk constants
MIN_RISK_PCT: Final[float] = 0.001
MAX_RISK_PCT: Final[float] = 0.1
MIN_RR_RATIO: Final[float] = 0.5
MAX_RR_RATIO: Final[float] = 10.0
```

**Update imports in affected files.**

## 8. Add Logging Configuration

**Create:** `src/tradingbot/logging_config.py`

```python
"""Logging configuration for the trading bot."""

import logging
import sys
from pathlib import Path

def setup_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    """Configure logging for the trading bot.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path to write logs to
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    
    # File handler (if specified)
    handlers = [console_handler]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        handlers.append(file_handler)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        handlers=handlers,
        force=True,  # Override any existing configuration
    )
```

**Update CLI entry points to call `setup_logging()`.**

## Priority Order

1. **Critical (Do First):**
   - #2: Improve error handling
   - #3: Add input validation
   - #4: Add config validation

2. **High Priority:**
   - #1: Add logging
   - #5: API key security warning
   - #8: Logging configuration

3. **Medium Priority:**
   - #6: Fix string parsing
   - #7: Add constants module

## Testing After Fixes

After applying fixes, run:
```bash
task check  # Lint, typecheck, and test
task test   # Run tests
```

Make sure all tests still pass and add new tests for validation logic.


# Market Structure Trading Strategy

## Executive Summary
A systematic trend-following strategy that identifies market direction through price structure analysis (Higher Highs/Lows, Lower Highs/Lows) and generates signals at key swing points.

---

## 1. Core Concepts

### Swing Points
| Term | Definition | Visual |
|------|------------|--------|
| **Swing High** | A peak where price rises then falls | ∧ |
| **Swing Low** | A trough where price falls then rises | ∨ |

### Trend Identification

**UPTREND (Bullish Structure)**
```
       HH₂
      /    \
    HH₁     \     HH₃
   /    \    \   /
 HL₁    HL₂   HL₃

✓ Each High > Previous High (Higher Highs)
✓ Each Low > Previous Low (Higher Lows)
```

**DOWNTREND (Bearish Structure)**
```
LH₁
   \    LH₂
    \  /    \    LH₃
     \/      \  /
    LL₁      LL₂
    
✓ Each High < Previous High (Lower Highs)
✓ Each Low < Previous Low (Lower Lows)
```

---

## 2. Strategy Architecture

The trading system uses a pluggable architecture with separate **entry** and **exit** strategies that can be combined freely.

### Entry Strategies (Signal Generation)

| Strategy | Description | Win Rate | Best For |
|----------|-------------|----------|----------|
| `swing_break` | Market structure breaks (HH/HL/LH/LL) | 45-55% | Trending markets |
| `vwap_reversion` | Mean reversion to VWAP | 55-62% | Ranging/mean-reverting |
| `orb` | Opening Range Breakout (first 30min) | 55-60% | High volatility opens |
| `rsi_divergence` | RSI divergence detection | 52-58% | Trend exhaustion |
| `atr_breakout` | ATR band breakouts | 50-55% | Volatile markets |
| `gap_and_go` | Opening gap continuation | 55-65% | News-driven gaps |
| `order_blocks` | ICT institutional order zones | 50-60% | After liquidity sweeps |
| `fvg` | Fair Value Gaps (imbalance fill) | 55-65% | Trending markets |
| `liquidity_sweeps` | Stop hunts at swing points | 55-65% | Reversal setups |

### Exit Strategies (SL/TP Calculation)

| Strategy | Stop Loss | Take Profit |
|----------|-----------|-------------|
| `swing` | Below/above last swing point | Swing target or RR-capped (1.5%) |
| `atr` | ATR-based distance | ATR × RR ratio (capped) |
| `fixed` | Fixed % from entry (2%) | Fixed % from entry (1.5%) |

### Indicator Filters

Entry signals can be filtered through indicators:

| Indicator | Filter Logic |
|-----------|--------------|
| `rsi` | Block BUY if RSI > 70, block SELL if RSI < 30 |
| `macd` | Block signals against MACD histogram direction |
| `bollinger` | Block signals during squeeze (low bandwidth) |
| `ema_crossover` | Block signals against EMA trend direction |
| `stochastic` | Block BUY if %K > 80, block SELL if %K < 20 |
| `adx` | Require +DI/-DI alignment with signal direction |
| `keltner` | Filter based on channel position |
| `vwap_bands` | Block signals too close to VWAP |
| `volume_profile` | Confirm signals near POC/VAH/VAL levels |
| `pivot_points` | Confirm signals based on pivot position |
| `fibonacci` | Require signal alignment with Fib trend |

### Configuration

```toml
[tradingbot.strategy]
# Option 1: Use a preset (recommended for quick setup)
preset = "balanced"      # Configures everything at once

# Option 2: Configure individually
entry = "swing_break"    # Entry strategy
exit = "swing"           # Exit strategy

[tradingbot.indicators]
enabled = ["rsi", "macd"]  # Indicators for filtering
filter_mode = "all"        # "all" = all must pass, "any" = one must pass
signal_mode = "filter"     # "filter" or "none"
```

### Presets

| Preset | Entry | Exit | Risk | RR | Description |
|--------|-------|------|------|-----|-------------|
| `conservative` | swing_break | swing | 0.5% | 1.5:1 | Filtered signals, low risk |
| `balanced` | swing_break | swing | 1.0% | 1.5:1 | RSI filtering, moderate risk |
| `aggressive` | swing_break | atr | 2.0% | 2.0:1 | No filters, higher risk |
| `scalping` | orb | fixed | 0.5% | 1.0:1 | Quick ORB trades, 30min time exit |
| `mean_reversion` | vwap_reversion | fixed | 1.0% | 1.2:1 | VWAP mean reversion |
| `momentum` | atr_breakout | atr | 1.5% | 1.5:1 | ATR breakouts, trend following |
| `divergence` | rsi_divergence | swing | 1.0% | 1.5:1 | Counter-trend at exhaustion |

---

## 3. Market Hypothesis (Swing Break Strategy)

> **"Markets trend, and trends persist until structure breaks."**

**Key Assumptions:**
1. Price moves in waves, creating identifiable swing points
2. Trend continuation is more probable than reversal
3. Structure breaks signal potential reversals
4. Risk can be managed using swing points as stop levels

---

## 3. Entry Rules

### Long Entries (BUY)
| Condition | Description |
|-----------|-------------|
| **Trend Continuation** | Bullish structure + price pulls back to Higher Low zone |
| **Structure Break** | Bearish structure breaks when price exceeds last Lower High |

### Short Entries (SELL)
| Condition | Description |
|-----------|-------------|
| **Trend Continuation** | Bearish structure + price rallies to Lower High zone |
| **Structure Break** | Bullish structure breaks when price falls below last Higher Low |

### Entry Confirmation Filters
- Candle confirmation (bullish candle for longs, bearish for shorts)
- Volume above average (optional)
- RSI not overbought/oversold (optional)

---

## 4. Exit Rules

### Stop Loss Placement
| Direction | Stop Location |
|-----------|--------------|
| **LONG** | Below last swing low - 0.2% buffer |
| **SHORT** | Above last swing high + 0.2% buffer |

### Take Profit
- **Primary**: 2:1 Risk-Reward ratio
- **Alternative**: Next significant swing point
- **Trailing**: Move stop to break-even after 1R profit

### Exit Reasons
1. Stop loss hit → Close immediately
2. Take profit hit → Close immediately
3. Structure break against position → Close at market

---

## 5. Risk Management

### Position Sizing Formula
```
Position Size = (Account Risk) / (Entry Price - Stop Loss)

Where:
- Account Risk = Capital × Risk Per Trade (1-2%)
```

### Example Calculation
```
Capital:      $100,000
Risk:         1% = $1,000
Entry:        $50.00
Stop Loss:    $48.00
Risk/Unit:    $2.00

Position Size = $1,000 / $2.00 = 500 shares
```

### Risk Rules
| Rule | Value |
|------|-------|
| Max risk per trade | 1-2% of capital |
| Max open positions | 3 |
| Max daily loss | 5% of capital |
| Max drawdown limit | 15% |

---

## 6. Indicator Selection

### Primary (Required)
- **Swing Point Detection**: 5-bar lookback default
- **Market Structure Analysis**: HH/HL vs LH/LL counting

### Secondary (Optional Filters)
| Indicator | Purpose | Settings |
|-----------|---------|----------|
| Volume | Confirm breakouts | Above 20-period MA |
| RSI | Avoid extremes | 14-period, avoid <20 or >80 |
| ATR | Dynamic stops | 14-period, 1.5x for stop width |
| 200 EMA | Trend filter | Only long above, short below |
| Bollinger Bands | Volatility & mean reversion | 20-period, 2 std dev |
| EMA Crossover | Trend direction | 9/21 EMA cross |
| VWAP Bands | Dynamic S/R levels | 1σ, 2σ deviation bands |
| Volume Profile | Key price levels | POC, VAH, VAL |
| Stochastic | Overbought/oversold with momentum | 14-period %K, 3-period %D |
| Pivot Points | Pre-market S/R levels | Daily PP, R1-R3, S1-S3 |
| ADX | Trend strength filter | 14-period, >25 = trending |
| Fibonacci | Pullback entry levels | 38.2%, 50%, 61.8% retracements |
| Keltner Channels | Squeeze detection with BB | 20 EMA, 10 ATR, 2x multiplier |

---

## 7. Backtesting Methodology

> **Usage:** See [README.md](README.md) for CLI commands and options.

### Data Requirements
- Minimum 500 bars of historical data
- OHLCV format
- Clean data (adjusted for splits/dividends)

### Walk-Forward Testing
To avoid overfitting, split data into training and testing periods:

```
┌─────────────────────────────────────────────────┐
│ Total Data                                      │
├─────────────────────────────────────────────────┤
│ [Train: 70%]              [Test: 30%]           │
│  Optimize params           Validate performance │
└─────────────────────────────────────────────────┘
```

**Interpreting Results:**
- Large gap between train/test returns → likely overfitting
- High parameter sensitivity → unstable, avoid those params
- Consistent performance across periods → robust strategy

### Performance Targets
| Metric | Target | Why |
|--------|--------|-----|
| Win Rate | >45% | With 2:1 R:R, 45% wins is profitable |
| Profit Factor | >1.5 | Ensures wins outweigh losses |
| Max Drawdown | <15% | Preserves capital for recovery |
| Sharpe Ratio | >1.0 | Risk-adjusted returns matter |

---

## 8. Optimization Guide

### Running Optimization

```bash
task optimize -- SPY --heatmap --overfit
```

### Understanding "Best By" Results

The optimizer reports three "best" parameter sets, each optimizing for a different goal:

| Result | Optimizes For | Best When |
|--------|---------------|-----------|
| **Best by Total Return** | Maximum profit | You want aggressive growth and can tolerate drawdowns |
| **Best by Risk-Adjusted** | Return ÷ Drawdown | You want balanced risk/reward (recommended for most) |
| **Best by Profit Factor** | Win quality (gross profit ÷ gross loss) | You want consistent trade selection, regardless of size |

### Why Different "Best" Results Have Different Returns

Consider this example output:

```
Best by Total Return:     +14.92% (risk=2.0%, drawdown=4.92%)
Best by Risk-Adjusted:    +12.97% (risk=2.0%, drawdown=1.92%)
Best by Profit Factor:    +3.19%  (risk=0.5%, drawdown=0.48%)
```

**Key insight:** Profit Factor measures trade selection quality, not position sizing.

- Same strategy with 0.5% risk vs 2.0% risk will have identical Profit Factor
- But 2.0% risk produces 4x larger returns (and 4x larger drawdowns)
- "Best by Profit Factor" often uses conservative risk settings

### Applying Results to Configuration

After running optimization, update `tradingbot.toml` with the recommended parameters:

```toml
[tradingbot.strategy]
# From "Best by Risk-Adjusted Return" (balanced approach)
swing_lb = 6       # swing_lookback from optimization
risk_pct = 0.02    # risk_pct (2.0% = 0.02)
rr_ratio = 2.5     # rr_ratio from optimization
```

### Which Result to Use?

| Your Goal | Use This Result | Config Focus |
|-----------|-----------------|--------------|
| Maximum growth, accept volatility | Best by Total Return | Higher `risk_pct` (1.5-2%) |
| Steady growth, controlled risk | Best by Risk-Adjusted | Moderate `risk_pct` (1-1.5%) |
| Capital preservation first | Best by Profit Factor | Lower `risk_pct` (0.5-1%) |

### Red Flags in Optimization Results

⚠️ **Be cautious if:**
- Win rate is very high (>80%) with few trades → likely overfitting
- Large gap between training and test returns → parameters don't generalize
- High parameter sensitivity → small changes cause big performance swings
- Only 1-3 trades in the test period → insufficient data for validation

✅ **Good signs:**
- Consistent performance across training/test periods
- Multiple nearby parameter combinations perform similarly
- Reasonable win rate (40-60%) with good R:R ratio

---

## 9. Implementation Roadmap

> **Code Reference:** See [README.md](README.md) for project structure and file locations.

### Phase 1: Core Strategy ✅
- [x] Data feed connection (Yahoo Finance)
- [x] Swing point detection
- [x] Market structure analysis (HH/HL/LH/LL)
- [x] Entry signal generation
- [x] Position sizing
- [x] Backtesting engine

### Phase 2: Risk Management ✅
- [x] Stop loss — swing-based placement
- [x] Stop loss — ATR-based (volatility)
- [x] Take profit — fixed R:R ratio
- [x] Trailing stop — move to breakeven after 1R

### Phase 3: Optimization ✅
- [x] Grid search parameter optimization
- [x] Overfitting detection (walk-forward)
- [x] Parameter sensitivity analysis

### Phase 4: Production (Planned)
- [ ] Logging framework (file-based logs)
- [ ] Alerting system (webhook/email)
- [ ] Paper trading validation
- [ ] Live trading integration

---

## 10. Day Trading Specifics

### Time-Based Exits

Day trading requires closing positions before market close to avoid overnight risk.

| Setting | Default | Description |
|---------|---------|-------------|
| `eod_exit` | `true` | Close all positions before market close |
| `eod_exit_minutes_before` | `15` | Minutes before close to trigger EOD exit |
| `time_exit_minutes` | `0` | Close position after N minutes (0 = disabled) |

**Exit Priority:**
1. Stop Loss (highest priority)
2. Take Profit
3. Time Exit (if `time_exit_minutes > 0`)
4. EOD Exit (if `eod_exit = true`)

### Take Profit Cap

All exit strategies enforce a **1.5% take-profit cap** for realistic day trading targets.

**Why 1.5%?**
- Individual stocks on 5-15m bars rarely move >2% in a few bars
- Ensures positions are exited before momentum fades
- Matches the statistical basis of the strategies (1:1 to 1.5:1 RR)

---

## 11. Common Pitfalls to Avoid

1. **Over-optimization** → Use walk-forward testing
2. **Ignoring transaction costs** → Include in backtest
3. **Look-ahead bias** → Only use data available at signal time
4. **Curve fitting** → Keep rules simple and robust
5. **Emotional overrides** → Trust the system

---

## 12. Risk Warnings

1. **Past performance does not guarantee future results.** Win rates are statistical averages from backtesting and academic research.
2. **Market conditions change.** A strategy that works in trending markets may underperform in ranging markets.
3. **Slippage and commissions** are not included in win rate estimates. Actual performance will be lower.
4. **Position sizing is critical.** Always use proper risk management (1-2% per trade max).
5. **Backtest before live trading.** Use the optimizer to validate strategy parameters on your target symbols.

---

## 13. Quick Reference Card

```
┌────────────────────────────────────────────┐
│         MARKET STRUCTURE CHEATSHEET        │
├────────────────────────────────────────────┤
│ UPTREND = HH + HL → BUY pullbacks to HL   │
│ DOWNTREND = LH + LL → SELL rallies to LH  │
│                                            │
│ BULLISH BREAK = Price > Last LH (in down) │
│ BEARISH BREAK = Price < Last HL (in up)   │
│                                            │
│ STOP = Beyond last swing point + buffer   │
│ TARGET = 2x the risk distance             │
│ SIZE = 1% risk ÷ (Entry - Stop)           │
└────────────────────────────────────────────┘
```
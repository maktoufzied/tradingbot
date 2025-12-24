# Day Trading Strategies Guide

This guide documents the available entry strategies for day trading with their statistical backing, win rates, and configuration options.

## Strategy Overview

| Strategy | Win Rate | Best RR | Risk Profile | Best Conditions |
|----------|----------|---------|--------------|-----------------|
| Market Structure | 55-60% | 1.5:1 | Medium | Trending markets |
| VWAP Mean Reversion | 55-62% | 1:1-1.2:1 | Low-Medium | Ranging/consolidating |
| Opening Range Breakout | 55-60% | 1:1 | Medium | High volatility days |
| RSI Divergence | 52-58% | 1:1-1.5:1 | Medium | Trend exhaustion |

## Strategy Details

### Market Structure (Default)

**Statistical Basis:**
- Win rate: 55-60% in trending conditions
- Best RR: 1.5:1
- Source: Dow Theory, classical technical analysis

**Entry Logic:**
- Identifies swing highs and lows to detect market structure
- LONG: Structure break above previous swing high with higher lows forming
- SHORT: Structure break below previous swing low with lower highs forming

**Exit Logic:**
- Stop: Below/above recent swing point (capped at 5%)
- Take Profit: Swing-based or RR-based (capped at 1.5%)

**Best Used When:**
- Clear trending market conditions
- After consolidation breakouts
- Avoid during choppy/ranging markets

**Configuration:**
```toml
[tradingbot.strategy]
entry = "market_structure"

[tradingbot.bot]
swing_lb = 5      # Swing lookback period
rr_ratio = 1.5    # Risk/reward ratio
```

---

### VWAP Mean Reversion

**Statistical Basis:**
- Win rate: 55-62% in ranging markets
- Best RR: 1:1 to 1.2:1
- Source: Berkowitz et al. (1988) - VWAP as institutional benchmark
- 65-70% of institutional orders execute near VWAP

**Entry Logic:**
- Calculates Volume Weighted Average Price and standard deviation bands
- LONG: Price deviates >1.5 standard deviations below VWAP (oversold)
- SHORT: Price deviates >1.5 standard deviations above VWAP (overbought)

**Exit Logic:**
- Take Profit: Return to VWAP (the mean)
- Stop Loss: 2 standard deviations beyond entry

**Best Used When:**
- Ranging/consolidating markets
- High volume periods (more reliable VWAP)
- Avoid during major news events or strong trends

**Configuration:**
```toml
[tradingbot.strategy]
entry = "vwap"

[tradingbot.bot]
rr_ratio = 1.2    # Mean reversion typically targets 1:1 to 1.2:1
```

---

### Opening Range Breakout (ORB)

**Statistical Basis:**
- Win rate: 55-60%
- Best RR: 1:1 (natural from range-based exits)
- Source: Toby Crabel (1990s) - ORB documentation
- First 15-30 minutes contain ~35% of daily volume
- Breakouts from opening range predict daily direction with 55-60% accuracy

**Entry Logic:**
- Defines opening range from first N bars of the session
- LONG: Price breaks above opening range high with volume confirmation (>1.2x average)
- SHORT: Price breaks below opening range low with volume confirmation

**Exit Logic:**
- Take Profit: 1x opening range size from entry
- Stop Loss: Opposite side of opening range

**Best Used When:**
- High volatility days (gap opens, news)
- Clear directional bias from overnight/pre-market
- Avoid low-volatility consolidation days

**Configuration:**
```toml
[tradingbot.strategy]
entry = "orb"

[tradingbot.bot]
rr_ratio = 1.0    # ORB naturally targets 1:1
```

---

### RSI Divergence

**Statistical Basis:**
- Win rate: 52-58% in trend exhaustion conditions
- Best RR: 1:1 to 1.5:1
- Source: Wilder (1978) - RSI original documentation
- Divergence signals have higher reliability on 15m+ timeframes

**Entry Logic:**
- Detects divergences between price and RSI momentum
- Bullish Divergence: Price makes lower low, RSI makes higher low (momentum strengthening)
- Bearish Divergence: Price makes higher high, RSI makes lower high (momentum weakening)

**Exit Logic:**
- Take Profit: Previous swing high/low
- Stop Loss: Beyond the divergence extreme + buffer

**Best Used When:**
- End of trends (exhaustion moves)
- After extended moves (3+ swings)
- Avoid during strong momentum

**Configuration:**
```toml
[tradingbot.strategy]
entry = "rsi_divergence"

[tradingbot.bot]
rr_ratio = 1.5
```

---

## Time-Based Exits

Day trading requires closing positions before market close to avoid overnight risk.

**Available Options:**

| Setting | Default | Description |
|---------|---------|-------------|
| `eod_exit` | `true` | Close all positions before market close |
| `eod_exit_minutes_before` | `15` | Minutes before close to trigger EOD exit |
| `time_exit_minutes` | `0` | Close position after N minutes (0 = disabled) |

**Configuration:**
```toml
[tradingbot.strategy]
eod_exit = true              # Close positions before market close
eod_exit_minutes_before = 15 # Exit 15 minutes before close
time_exit_minutes = 60       # Optional: close after 60 minutes regardless
```

**Exit Priority:**
1. Stop Loss (highest priority)
2. Take Profit
3. Time Exit (if `time_exit_minutes > 0`)
4. EOD Exit (if `eod_exit = true`)

---

## Take Profit Cap

All strategies have a **1.5% take-profit cap** for realistic day trading targets. This prevents unrealistic TP targets like 3-6% moves on intraday data.

**Why 1.5%?**
- Individual stocks on 15m bars rarely move >2% in a few bars
- Ensures positions are exited before momentum fades
- Matches the statistical basis of the strategies (1:1 to 1.5:1 RR)

---

## Configuration Examples

### Conservative (Lower Risk)

```toml
[tradingbot.strategy]
entry = "vwap"               # Mean reversion (highest win rate)
eod_exit = true
eod_exit_minutes_before = 30 # Exit earlier

[tradingbot.bot]
risk_pct = 0.005             # 0.5% risk per trade
rr_ratio = 1.0               # 1:1 RR
allow_short = false          # Longs only
```

### Balanced

```toml
[tradingbot.strategy]
entry = "market_structure"
eod_exit = true
eod_exit_minutes_before = 15

[tradingbot.bot]
risk_pct = 0.01              # 1% risk per trade
rr_ratio = 1.5               # 1.5:1 RR
allow_short = false
```

### Aggressive

```toml
[tradingbot.strategy]
entry = "orb"                # Higher volatility strategy
eod_exit = true
time_exit_minutes = 120      # Exit after 2 hours if no SL/TP

[tradingbot.bot]
risk_pct = 0.02              # 2% risk per trade
rr_ratio = 1.0               # 1:1 RR (faster exits)
allow_short = true           # Both directions
```

---

## Risk Warnings

1. **Past performance does not guarantee future results.** Win rates are statistical averages from backtesting and academic research.

2. **Market conditions change.** A strategy that works in trending markets may underperform in ranging markets.

3. **Slippage and commissions** are not included in win rate estimates. Actual performance will be lower.

4. **Position sizing is critical.** Always use proper risk management (1-2% per trade max).

5. **Backtest before live trading.** Use the optimizer to validate strategy parameters on your target symbols.

---

## Glossary

| Term | Definition |
|------|------------|
| **VWAP** | Volume Weighted Average Price - average price weighted by volume |
| **Opening Range** | High/low of the first N bars of a trading session |
| **RSI Divergence** | Price and RSI moving in opposite directions |
| **Swing Point** | Local high or low in price action |
| **Structure Break** | Price moving beyond a previous swing point |
| **RR Ratio** | Risk-to-Reward ratio (1.5:1 means targeting $1.50 profit for $1 risk) |
| **EOD Exit** | End of Day exit - closing positions before market close |

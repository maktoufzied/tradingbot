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

## 2. Market Hypothesis

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

## 8. Implementation Roadmap

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

## 9. Common Pitfalls to Avoid

1. **Over-optimization** → Use walk-forward testing
2. **Ignoring transaction costs** → Include in backtest
3. **Look-ahead bias** → Only use data available at signal time
4. **Curve fitting** → Keep rules simple and robust
5. **Emotional overrides** → Trust the system

---

## 10. Quick Reference Card

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
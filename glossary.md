# Glossary

Quick reference for trading and technical terms used in this project.

---

## Trading Concepts

### Market Structure

| Term | Definition |
|------|------------|
| **Swing High** | A local price peak where price rises then falls. Used to identify resistance levels. |
| **Swing Low** | A local price trough where price falls then rises. Used to identify support levels. |
| **Higher High (HH)** | A swing high that is higher than the previous swing high. Indicates bullish momentum. |
| **Higher Low (HL)** | A swing low that is higher than the previous swing low. Confirms uptrend continuation. |
| **Lower High (LH)** | A swing high that is lower than the previous swing high. Indicates bearish momentum. |
| **Lower Low (LL)** | A swing low that is lower than the previous swing low. Confirms downtrend continuation. |
| **Structure Break** | When price breaks a key swing point, signaling potential trend reversal. Bullish break = price exceeds last Lower High. Bearish break = price falls below last Higher Low. |

### Smart Money Concepts (ICT)

| Term | Definition |
|------|------------|
| **Order Block (OB)** | The last opposing candle before a significant price move. Represents institutional entry zones. Bullish OB = last bearish candle before a big up move. Bearish OB = last bullish candle before a big down move. |
| **Fair Value Gap (FVG)** | An imbalance zone where price moved too fast, creating a gap between candle 1's high and candle 3's low (bullish) or candle 1's low and candle 3's high (bearish). Price tends to return to "fill" these gaps. |
| **Liquidity Sweep** | When price briefly breaks above swing highs or below swing lows to trigger stop losses (grabbing liquidity) before reversing. Also called "stop hunts." |
| **Point of Control (POC)** | The price level with the highest traded volume in a given period. Acts as a strong magnet for price. |
| **Value Area High (VAH)** | Upper boundary of the price range containing 70% of trading volume. Acts as resistance. |
| **Value Area Low (VAL)** | Lower boundary of the price range containing 70% of trading volume. Acts as support. |

### Position & Risk

| Term | Definition |
|------|------------|
| **Position Size** | Number of shares/units to buy or sell, calculated based on risk tolerance and stop distance. |
| **Stop Loss** | A predetermined price level where a losing position is automatically closed to limit losses. |
| **Take Profit** | A predetermined price level where a winning position is automatically closed to lock in gains. |
| **Risk per Trade** | The maximum amount (or percentage of capital) you're willing to lose on a single trade. Typically 1-2%. |
| **Reward/Risk Ratio (R:R)** | The ratio of potential profit to potential loss. A 2:1 R:R means you aim to make $2 for every $1 risked. |
| **Trailing Stop** | A stop loss that moves in the direction of profit, locking in gains as the trade moves favorably. |
| **ATR Trail** | A trailing stop based on ATR (Average True Range). Stop is set at `High_Water_Mark - (N × ATR)` where N is the multiplier (default 2.0). Adapts to market volatility. |
| **ATR Trail Activation** | Minimum profit level (in R-multiples) before ATR trailing begins. Default 0 = immediate trailing. Setting to 1.0 means trailing only starts after reaching 1R profit. |
| **High-Water Mark** | The highest price reached since position entry (for longs). Used as the reference point for ATR trailing stops. |

### Execution Costs

| Term | Definition |
|------|------------|
| **Slippage** | The difference between expected trade price and actual execution price. Caused by market movement during order transmission. Measured in basis points (bps). |
| **Bid-Ask Spread** | The difference between the highest buy price (bid) and lowest sell price (ask). Buyers pay the ask, sellers receive the bid. Measured in basis points. |
| **Commission** | Fee charged by the broker per share or per trade. Typically $0.005/share for discount brokers. |
| **Gross P&L** | Profit/loss calculated from signal prices (before execution costs). |
| **Net P&L** | Actual profit/loss after accounting for slippage, spread, and commission. Net = Gross - Costs. |
| **Basis Point (bps)** | One hundredth of a percent (0.01%). 100 bps = 1%. Used to express small price differences. |
| **Round-Trip Costs** | Total execution costs for both entry and exit of a trade. Includes entry slippage + exit slippage + entry spread + exit spread + commission × 2. |

### Trade Outcomes

| Term | Definition |
|------|------------|
| **Win Rate** | Percentage of trades that are profitable. Win Rate = Winners ÷ Total Trades × 100. |
| **P&L (Profit & Loss)** | The monetary gain or loss from a trade or series of trades (typically net of execution costs). |
| **Drawdown** | The decline from a peak equity value to a trough. Measures how much you "give back" before recovering. |
| **Max Drawdown** | The largest peak-to-trough decline in account value. Critical for understanding worst-case scenarios. |

---

## Strategy Parameters

### `swing_lb` (Swing Lookback)

**What it does:** Determines how many bars to look back when identifying swing points.

**How it works:**
- A swing high requires the high to be greater than the highs of `swing_lb` bars on each side
- Lower values (3-4) = more swing points detected, more signals, more noise
- Higher values (7-10) = fewer swing points, fewer signals, more significant levels

**Example:**
```
swing_lb = 5 means:
- To be a swing high, the bar's high must be higher than 5 bars before AND 5 bars after
- This creates a minimum 11-bar pattern (5 + 1 + 5)
```

**Tuning guidance:**
| Value | Effect | Best For |
|-------|--------|----------|
| 3-4 | Many signals, noisy | Short-term trading, active markets |
| 5-6 | Balanced (default) | Most situations |
| 7-10 | Few signals, significant | Long-term trading, avoiding false signals |

---

### `risk_pct` (Risk Percentage)

**What it does:** The percentage of your capital risked on each trade.

**How it works:**
```
Position Size = (Capital × risk_pct) ÷ (Entry Price - Stop Loss)

Example:
  Capital: $100,000
  risk_pct: 0.01 (1%)
  Risk Amount: $1,000
  Entry: $50.00
  Stop: $48.00
  Position Size: $1,000 ÷ $2.00 = 500 shares
```

**Tuning guidance:**
| Value | Risk Level | Typical Use |
|-------|------------|-------------|
| 0.005 (0.5%) | Conservative | Capital preservation, beginners |
| 0.01 (1%) | Moderate | Standard recommendation |
| 0.015-0.02 (1.5-2%) | Aggressive | Experienced traders, high conviction |

**Important:** Higher risk = higher returns AND higher drawdowns. A 2% risk strategy will have ~4x the returns and ~4x the drawdowns of a 0.5% risk strategy.

---

### `rr_ratio` (Reward/Risk Ratio)

**What it does:** Sets the take-profit distance as a multiple of the stop-loss distance.

**How it works:**
```
Take Profit = Entry + (Entry - Stop Loss) × rr_ratio

Example (Long trade):
  Entry: $50.00
  Stop: $48.00 (risk = $2.00)
  rr_ratio: 2.0
  Take Profit: $50.00 + ($2.00 × 2.0) = $54.00
```

**Tuning guidance:**
| Value | Win Rate Needed | Trade Style |
|-------|-----------------|-------------|
| 1.5 | 40%+ to profit | More winners, smaller wins |
| 2.0 | 34%+ to profit | Balanced (default) |
| 2.5 | 29%+ to profit | Fewer winners, larger wins |
| 3.0 | 25%+ to profit | Trend-following, patient |

**Math:** Minimum win rate for profitability = 1 ÷ (1 + rr_ratio)

---

## Performance Metrics

### Profit Factor

**Definition:** Gross profits divided by gross losses (absolute value).

```
Profit Factor = Total Winning Amount ÷ Total Losing Amount

Example:
  5 winning trades totaling $5,000
  5 losing trades totaling $3,000
  Profit Factor = $5,000 ÷ $3,000 = 1.67
```

**Interpretation:**
| Value | Meaning |
|-------|---------|
| < 1.0 | Losing strategy (losses exceed profits) |
| 1.0 - 1.5 | Marginal (barely profitable) |
| 1.5 - 2.0 | Good |
| 2.0+ | Excellent |
| 10+ | Suspicious (likely overfitting or few trades) |

**Note:** Profit Factor measures trade selection quality, not position sizing. A conservative 0.5% risk strategy and aggressive 2% risk strategy with identical trade entries will have the same Profit Factor.

---

### Max Drawdown

**Definition:** The largest percentage decline from a peak to a subsequent trough in account equity.

```
Example equity curve:
  $100,000 → $115,000 → $105,000 → $120,000 → $108,000 → $130,000

Drawdowns:
  Peak $115,000 → Trough $105,000 = -8.7%
  Peak $120,000 → Trough $108,000 = -10.0%

Max Drawdown = 10.0%
```

**Why it matters:**
- Shows worst-case historical loss
- Affects psychological tolerance (can you handle a 20% drop?)
- Recovery math is asymmetric: -50% drawdown requires +100% gain to recover

**Target:** Keep max drawdown under 15-20% for sustainable trading.

---

### Risk-Adjusted Return

**Definition:** Return divided by the risk taken to achieve it. In this project, calculated as Total Return ÷ Max Drawdown.

```
Example:
  Strategy A: +20% return, 20% drawdown → Risk-Adjusted = 1.0
  Strategy B: +15% return, 5% drawdown → Risk-Adjusted = 3.0

Strategy B is "better" despite lower absolute return
```

**Why it matters:** Raw returns don't tell the whole story. A 50% return with 40% drawdown is riskier than 20% return with 5% drawdown.

---

### Calmar Ratio

**Definition:** A risk-adjusted performance metric calculated as Annual Return ÷ Max Drawdown. Named after its creator (California Managed Accounts Reports).

```
Example:
  Strategy A: +20% return, 10% drawdown → Calmar = 2.0
  Strategy B: +30% return, 20% drawdown → Calmar = 1.5

Strategy A has better risk-adjusted performance
```

**Why it matters:** Used by the optimizer (`--objective calmar`) to find strategies that balance returns with risk. Higher is better. A Calmar > 1.0 means return exceeds max drawdown.

**Related:** Sharpe Ratio uses standard deviation instead of drawdown, but Calmar is more intuitive for traders who think in terms of "how much can I lose?"

---

## Optimization Concepts

### Overfitting

**Definition:** When a strategy performs exceptionally well on historical data but fails on new data because it has "memorized" past patterns rather than learning generalizable rules.

**Signs of overfitting:**
- Exceptional backtest results (>50% annual return, >80% win rate)
- Large gap between training and test period performance
- High sensitivity to small parameter changes
- Very few trades in the test period

**How to avoid:**
- Use walk-forward testing (train on 70%, test on 30%)
- Keep parameter count low
- Prefer stable parameter regions over peak performance
- Be skeptical of "too good" results

---

### Parameter Sensitivity

**Definition:** How much performance changes when a parameter value changes slightly.

**Example:**
```
swing_lb=5: +12% return
swing_lb=6: +11% return  → Low sensitivity (good)
swing_lb=7: +10% return

vs.

swing_lb=5: +5% return
swing_lb=6: +15% return  → High sensitivity (bad)
swing_lb=7: -3% return
```

**Why it matters:** High sensitivity suggests the "optimal" value is lucky rather than robust. Prefer parameters where nearby values perform similarly.

---

### Walk-Forward Validation

**Definition:** A robust validation method that uses multiple sequential train/test windows to detect overfitting. Unlike simple train/test splits, walk-forward uses rolling windows for more reliable estimates.

```
Full Walk-Forward Analysis (5 folds, 70% train):
┌──────────────────────────────────────────────────────┐
│ Fold 1: [====Train====][Test]                         │
│ Fold 2:    [====Train====][Test]                      │
│ Fold 3:       [====Train====][Test]                   │
│ Fold 4:          [====Train====][Test]                │
│ Fold 5:             [====Train====][Test]             │
└──────────────────────────────────────────────────────┘
```

**Process:**
1. Split data into N sequential folds
2. For each fold: optimize on training, test on out-of-sample
3. Aggregate out-of-sample results across all folds
4. Compare average in-sample vs out-of-sample performance

**Key Metrics:**
| Metric | Description |
|--------|-------------|
| `avg_train_return` | Average in-sample return across folds |
| `avg_test_return` | Average out-of-sample return across folds |
| `return_degradation` | Train - Test (lower is better) |
| `consistency` | % of folds with positive OOS returns |

**Risk Assessment:**
| Condition | Interpretation |
|-----------|----------------|
| Degradation > 50% | HIGH RISK - strategy is overfit |
| Degradation 25-50% | MODERATE RISK - needs more validation |
| Degradation < 25%, positive OOS | LOW RISK - appears robust |

**Usage:**
```bash
tradingbot-optimize AAPL --walk-forward
tradingbot-optimize AAPL --walk-forward --folds 7 --train-ratio 0.8
```

---

### Grid Search

**Definition:** An exhaustive optimization method that tests every combination of parameter values.

```
Example search space:
  swing_lb: [3, 4, 5, 6, 7]     → 5 values
  risk_pct: [0.01, 0.015, 0.02] → 3 values
  rr_ratio: [1.5, 2.0, 2.5]     → 3 values

Total combinations: 5 × 3 × 3 = 45 backtests
```

**Pros:** Guaranteed to find the best combination within the search space.
**Cons:** Slow for large parameter spaces. 10 values × 10 values × 10 values = 1,000 backtests.

**Usage:** `task optimize -- SPY --swing 3,4,5,6,7 --risk 0.01,0.015,0.02`

---

### Optuna

**Definition:** A smart optimization library that uses Bayesian optimization (TPE algorithm) to find good parameters faster than grid search.

**How it works:**
1. Starts with random samples
2. Learns which parameter regions perform well
3. Focuses exploration on promising areas
4. Avoids wasting time on bad regions

```
Example:
  Grid search: 1000 combinations → 1000 backtests
  Optuna: 100 trials → often finds similar or better results
```

**Objectives available:**
| Objective | Optimizes For |
|-----------|---------------|
| `return` | Maximize total return |
| `calmar` | Maximize return ÷ drawdown (default) |
| `profit_factor` | Maximize gross profit ÷ gross loss |
| `multi` | Pareto front (return vs drawdown trade-offs) |

**Usage:** `task optimize -- SPY --optuna --trials 100 --objective calmar`

---

### Preset

**Definition:** A saved configuration that bundles interval, period, entry strategy, exit strategy, risk parameters, and indicator filters into a single named profile.

**Built-in presets:** `scalping`, `day_momentum`, `mean_reversion`, `swing_balanced`, etc.

**Custom presets:** Saved to `tradingbot.toml` via `--save-preset`:
```bash
# Optimize and save best params as preset
task optimize -- AAPL --optuna --save-preset aapl_optimized

# Use the preset later
task backtest -- AAPL --preset aapl_optimized
```

---

### Per-Symbol Preset

**Definition:** Assigning different strategy presets to different symbols in a single trading session using `SYMBOL:preset` CLI syntax.

**Syntax:** `tradingbot-live SYMBOL:preset_name`

**Examples:**
```bash
# Each symbol uses a different preset
tradingbot-live SPY:day_momentum AAPL:mean_reversion QQQ:scalping

# Mix: some symbols specify preset, others use default
tradingbot-live SPY:aggressive AAPL QQQ --preset balanced
# → SPY uses aggressive, AAPL and QQQ use balanced
```

**Use case:** Run multiple strategies simultaneously on different instruments (e.g., momentum on trending stocks, mean-reversion on ranging stocks).

---

### SymbolStrategyConfig

**Definition:** A dataclass in `hub/types.py` that holds strategy configuration for a specific symbol. Sent to UI clients to display per-symbol strategy details.

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `preset_name` | str | Preset name (e.g., "day_momentum") |
| `entry_strategy` | str | Entry strategy (e.g., "swing_break") |
| `exit_strategy` | str | Exit strategy (e.g., "swing") |
| `risk_pct` | float | Risk per trade (0.01 = 1%) |
| `rr_ratio` | float | Risk:Reward ratio (e.g., 2.0) |
| `indicators` | list | Indicator filters (e.g., ["rsi", "adx"]) |
| `filter_mode` | str | How indicators combine: "all", "any", "none" |
| `eod_exit` | bool | Close at end of day? |
| `partial_exits` | str | Partial profit levels (e.g., "1R→50%") |

---

## Data Terms

### Period

**Definition:** The historical time range to fetch data for.

| Value | Meaning |
|-------|---------|
| `1mo` | 1 month |
| `6mo` | 6 months |
| `1y` | 1 year (default) |
| `2y` | 2 years |
| `5y` | 5 years |
| `max` | All available history |

---

### Interval

**Definition:** The timeframe of each price bar (candle).

| Value | Use Case |
|-------|----------|
| `1m` | Scalping (max 7 days history) |
| `5m`, `15m` | Day trading (max 60 days) |
| `1h` | Day/swing trading (default, max 730 days) |
| `1d` | Position trading (unlimited history) |

---

### OHLCV

**Definition:** Open, High, Low, Close, Volume — the five data points for each price bar.

| Field | Definition |
|-------|------------|
| **Open** | First traded price in the period |
| **High** | Highest traded price in the period |
| **Low** | Lowest traded price in the period |
| **Close** | Last traded price in the period |
| **Volume** | Number of shares/units traded |

---

## Live Trading Terms

### Paper Trading

**Definition:** Simulated trading with fake money to test strategies in real-time without financial risk.

### Dry Run

**Definition:** Running the bot to generate and log signals without executing any trades (real or paper).

### Circuit Breaker

**Definition:** An automatic safety mechanism that pauses trading when losses exceed a threshold (e.g., 3% daily loss triggers a pause).

### Position Limit

**Definition:** Maximum number of concurrent open positions allowed. Prevents over-concentration risk.

### Replay Mode

**Definition:** A simulation mode that replays historical data as if it were live, allowing you to test the live trading engine with past market conditions.

**Use cases:**
- Validate live trading logic before deploying to real markets
- Test how the bot handles specific market conditions
- Debug and observe signal generation in real-time

**Options:**
| Flag | Description |
|------|-------------|
| `--speed N` | Bars per second (0 = instant playback) |
| `--from DATE` | Start replay from specific date |
| `--to DATE` | End replay at specific date |
| `--period` | Historical period to replay (default: 2y) |

**Example:**
```bash
task replay -- SPY --speed 10 --from 2024-01-01
```

---

## Technical Indicators

### Momentum Indicators

| Indicator | Definition |
|-----------|------------|
| **RSI (Relative Strength Index)** | Measures momentum on a 0-100 scale. RSI > 70 = overbought, RSI < 30 = oversold. |
| **Stochastic Oscillator** | Compares closing price to price range. %K and %D lines cross in extreme zones to signal reversals. |
| **MACD** | Moving Average Convergence Divergence. MACD line crossing signal line indicates momentum shifts. |

### Trend Indicators

| Indicator | Definition |
|-----------|------------|
| **EMA Crossover** | Fast EMA (9) crossing slow EMA (21) signals trend direction changes. |
| **ADX (Average Directional Index)** | Measures trend strength (not direction). ADX > 25 = strong trend, < 20 = ranging. |

### Volatility Indicators

| Indicator | Definition |
|-----------|------------|
| **Bollinger Bands** | SMA ± 2 standard deviations. Squeeze (narrow bands) = low volatility, expansion = high volatility. |
| **Keltner Channels** | EMA ± ATR multiplier. Used with Bollinger Bands for squeeze detection. |
| **ATR (Average True Range)** | Measures volatility by averaging the true range over N periods. |

### Volume Indicators

| Indicator | Definition |
|-----------|------------|
| **VWAP (Volume Weighted Average Price)** | Average price weighted by volume. Institutional benchmark. Price above VWAP = bullish, below = bearish. |
| **VWAP Bands** | Standard deviation bands around VWAP (1σ, 2σ). Dynamic support/resistance levels. |
| **Volume Profile** | Distribution of volume across price levels. Shows POC, VAH, VAL. |

### Support/Resistance Indicators

| Indicator | Definition |
|-----------|------------|
| **Pivot Points** | Classic floor trader levels calculated from previous session. PP = (H + L + C) / 3, with R1-R3 above and S1-S3 below. |
| **Fibonacci Retracements** | Key retracement levels (23.6%, 38.2%, 50%, 61.8%, 78.6%) from swing high to swing low. Used for pullback entries. |

---

## UI Terms

### Flip Card

**Definition:** A UI pattern where a card displays different content on "front" and "back" sides, toggled by user interaction.

**In TUI (Terminal UI):**
- **Trigger:** Focus a symbol card and press Enter or Space
- **Front:** Price, change, sparkline chart, trend/signal badges, position info
- **Back:** Strategy details (entry, exit, risk, R:R, indicators, EOD/Swing badge)

**In Web UI:**
- **Trigger:** Click on a symbol card
- **Front:** Price, chart, position summary
- **Back:** Strategy configuration details

---

### Signal Badge

**Definition:** A visual indicator showing the current trading signal for a symbol.

| Signal | Badge Color | Meaning |
|--------|-------------|---------|
| `BUY` | Green | Strategy recommends entering long |
| `SELL` | Red | Strategy recommends entering short |
| `HOLD` | Gray | No action recommended |

---

### Trend Badge

**Definition:** A visual indicator showing the current market structure trend.

| Trend | Badge Color | Structure |
|-------|-------------|-----------|
| `BULLISH` | Green | HH + HL pattern |
| `BEARISH` | Red | LH + LL pattern |
| `NEUTRAL` | Gray | No clear structure |

---

## Cache System Terms

| Term | Definition |
|------|------------|
| **DuckDB Cache** | Local database storing historical OHLCV bars. Eliminates redundant API calls and survives restarts. |
| **Bar Aggregation** | Converting fine-grained bars to coarser intervals. Example: 1m bars → 5m/15m/1h/1d bars. |
| **Retention Policy** | Rules for how long to keep bars per interval. 1m=7d, 5m=30d, 15m=90d, 1h=365d, 1d=forever. |
| **Cache Maintenance** | Periodic process that aggregates 1m bars and purges data older than retention policy. |
| **Cache Hit** | When requested data is found in local DuckDB cache, avoiding API call. |
| **Cache Miss** | When requested data is not in cache and must be fetched from upstream API (Yahoo/Alpaca). |

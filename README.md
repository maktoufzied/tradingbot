# Trading Bot

A market structure trading bot with backtesting and live trading capabilities using Yahoo Finance data.

## Features

- **Market Structure Analysis**: Identifies swing highs/lows and trend direction
- **Signal Generation**: Generates BUY/SELL signals based on structure breaks and pullbacks
- **Risk Management**: Configurable position sizing, stop-loss strategies, and reward/risk ratios
- **Backtesting**: Test strategies on historical data with detailed performance metrics
- **Parameter Optimization**: Grid search optimization with overfitting detection
- **Live Trading**: Paper trading with real-time risk controls (circuit breakers, position limits)
- **Plugin Architecture**: Extensible data fetchers, brokers, and stop-loss strategies

## Installation

```bash
# Clone and install
git clone <repo-url>
cd tradingbot
uv sync
```

### Optional: Install Task Runner

[Task](https://taskfile.dev) provides convenient shortcuts for common commands:

```bash
# macOS
brew install go-task

# Linux
sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d -b ~/.local/bin

# Windows
choco install go-task
```

## Quick Start

### Run a Backtest

```bash
# Using task (recommended)
task backtest -- SPY
task backtest -- AAPL --period 5y

# Or using uv directly
uv run tradingbot-backtest SPY
uv run tradingbot-backtest AAPL TSLA GOOGL
```

### Run Parameter Optimization

```bash
# Using task - Optuna (recommended)
task optimize -- SPY --optuna
task optimize -- AAPL --optuna --trials 200 --save-preset aapl_best

# Grid search with analysis
task optimize -- AAPL --heatmap --overfit

# Or using uv directly
uv run tradingbot-optimize SPY --optuna
uv run tradingbot-optimize TSLA --optuna --interval 15m,1h --period 3mo,1y
```

## CLI Commands

### `tradingbot-backtest`

Run backtests on one or more symbols.

```bash
task backtest -- <SYMBOLS> [OPTIONS]

# Or using uv directly
uv run tradingbot-backtest <SYMBOLS> [OPTIONS]
```

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--period` | Data period | `1y` |
| `--interval` | Data interval | `1h` |
| `--capital` | Starting capital | config value |
| `--risk` | Risk per trade (e.g., 0.01 for 1%) | config value |
| `--rr` | Reward/risk ratio | config value |
| `--swing-lb` | Swing lookback period | config value |
| `--strategy`, `-s` | Entry strategy to use | config value |
| `--preset`, `-p` | Use a preset (overrides strategy, risk, etc.) | - |
| `--list-strategies` | List available entry/exit strategies | - |
| `--list-presets` | List available trading presets | - |
| `--refresh` | Force re-fetch data from API | - |
| `--verbose`, `-v` | Print each bar as it processes | - |
| `--speed` | Simulate real-time (bars/sec, 0=instant) | `0` |
| `--no-costs` | Disable execution costs for comparison | - |
| `--slippage BPS` | Slippage in basis points | `5` |
| `--spread BPS` | Bid-ask spread in basis points | `2` |
| `--commission USD` | Commission per share | `0.005` |

**Examples:**

```bash
task backtest -- SPY
task backtest -- AAPL TSLA GOOGL
task backtest -- SPY --period 2y --interval 1d
task backtest -- AAPL --capital 50000 --risk 0.02
task backtest -- SPY -p scalping                 # Use scalping preset
task backtest -- SPY --preset conservative       # Use conservative preset
task backtest -- SPY -s vwap_reversion           # Use VWAP strategy
task backtest -- SPY --list-presets              # Show available presets
task backtest -- SPY --list-strategies           # Show available strategies
task backtest -- SPY --verbose                   # See each bar
task backtest -- SPY --speed 10                  # Simulate 10 bars/sec
```

### `tradingbot-optimize`

Optimize trading parameters with grid search or Optuna.

```bash
task optimize -- <SYMBOL> [OPTIONS]

# Or using uv directly
uv run tradingbot-optimize <SYMBOL> [OPTIONS]
```

**General Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--period` | Data period(s), comma-separated | `1y` |
| `--interval` | Data interval(s), comma-separated | `1h` |
| `--capital` | Starting capital | `100000` |
| `--save-preset NAME` | Save best params as preset to tradingbot.toml | - |

**Optuna Options** (smart sampling - recommended):

| Flag | Description | Default |
|------|-------------|---------|
| `--optuna` | Use Optuna instead of grid search | - |
| `--trials` | Number of Optuna trials | `100` |
| `--objective` | Optimization target: `return`, `calmar`, `profit_factor`, `multi` | `calmar` |
| `--seed` | Random seed for reproducible results | - |

**Grid Search Options** (exhaustive):

| Flag | Description | Default |
|------|-------------|---------|
| `--heatmap` | Show parameter heatmaps | - |
| `--overfit` | Run overfitting analysis | - |
| `--plot` | Show parameter impact charts | - |
| `--swing` | Swing lookback values (comma-separated) | `3,4,5,6,7,8,9,10` |
| `--risk` | Risk percentages (comma-separated) | `0.005,0.01,0.015,0.02` |
| `--rr` | Reward/risk ratios (comma-separated) | `1.5,2.0,2.5,3.0` |

**Walk-Forward Validation** (prevents overfitting):

| Flag | Description | Default |
|------|-------------|---------|
| `--walk-forward` | Run walk-forward validation | - |
| `--folds` | Number of walk-forward folds | `5` |
| `--train-ratio` | Training data ratio per fold | `0.7` |

### `tradingbot-live`

Run live trading (paper trading by default).

```bash
task live -- <SYMBOLS> [OPTIONS]

# Or using uv directly
uv run tradingbot-live <SYMBOLS> [OPTIONS]
```

**Examples:**

```bash
# Dry run (log signals without trading)
task live -- SPY --dry-run

# Paper trading with multiple symbols
task live -- SPY QQQ AAPL

# TUI mode (interactive terminal dashboard)
task live -- SPY --tui
```

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--dry-run` | Log signals without executing trades | - |
| `--tui` | Interactive terminal UI dashboard | - |

**Risk Controls (configured in `tradingbot.toml`):**

| Control | Description | Default |
|---------|-------------|---------|
| Circuit breaker | Pause trading after X% daily loss | 3% |
| Max daily loss | Stop trading after X% daily loss | 5% |
| Max positions | Maximum concurrent positions | 5 |
| Max position size | Maximum % of equity per position | 10% |
| Trading hours | Only trade 9:30 AM - 4:00 PM ET | Yes |

### `tradingbot-cache`

Manage the local market data cache.

```bash
task cache -- <COMMAND> [OPTIONS]

# Or using uv directly
uv run tradingbot-cache <COMMAND> [OPTIONS]
```

**Commands:**

| Command | Description |
|---------|-------------|
| `stats` | Show cache statistics (symbols, bar counts, date ranges) |
| `fetch <SYMBOLS>` | Fetch and cache data for symbols |
| `clear <SYMBOLS>` | Clear cached data for symbols |
| `aggregate [SYMBOLS]` | Aggregate 1m bars to coarser intervals (5m, 15m, 1h, 1d) |
| `maintain` | Run maintenance: aggregate + purge old data per retention policy |

**Retention Policy:**

| Interval | Keep For |
|----------|----------|
| 1m | 7 days |
| 5m | 30 days |
| 15m | 90 days |
| 1h | 365 days |
| 1d | Forever |

**Examples:**

```bash
# View cache statistics
task cache -- stats

# Pre-fetch data for symbols
task cache -- fetch SPY QQQ AAPL
task cache -- fetch SPY --period 5y

# Force re-fetch (clear and fetch)
task cache -- fetch SPY --refresh

# Clear cached data
task cache -- clear SPY
task cache -- clear SPY --interval 1d

# Aggregate 1m bars to coarser intervals
task cache -- aggregate              # All symbols
task cache -- aggregate SPY          # Specific symbol

# Run maintenance (aggregate + purge old data)
task cache -- maintain               # Full maintenance
task cache -- maintain --dry-run     # Preview what would be purged
task cache -- maintain --show-policy # Show retention policy
```

## Presets

Presets provide complete trading configurations optimized for different styles. Use `--list-presets` to see available options.

**Day Trading** (intraday, closes positions at EOD):

| Preset | Interval | Entry | Exit | Risk | RR | Indicator |
|--------|----------|-------|------|------|-----|-----------|
| `scalping` | 5m | orb | fixed | 0.5% | 1.5:1 | stochastic |
| `day_momentum` | 15m | atr_breakout | atr | 1.0% | 1.5:1 | adx |
| `mean_reversion` | 15m | vwap_reversion | fixed | 1.0% | 1.2:1 | bollinger |
| `day_breakout` | 15m | atr_breakout | atr | 1.0% | 1.5:1 | keltner, ema_crossover |

**Swing Trading** (multi-day, holds overnight):

| Preset | Interval | Entry | Exit | Risk | RR | Indicator |
|--------|----------|-------|------|------|-----|-----------|
| `swing_conservative` | 1h | swing_break | swing | 0.5% | 2.0:1 | ema_crossover |
| `swing_balanced` | 1h | swing_break | swing | 1.0% | 2.0:1 | adx |
| `swing_aggressive` | 1h | swing_break | atr | 2.0% | 2.5:1 | none |
| `divergence` | 1h | rsi_divergence | swing | 1.0% | 2.0:1 | macd |

```bash
# Use a preset
task backtest -- SPY --preset scalping
task backtest -- AAPL -p swing_balanced

# CLI args override preset values
task backtest -- SPY -p scalping --risk 0.02  # Override risk to 2%
```

## Configuration

Create `tradingbot.toml` in your project root:

```toml
[tradingbot.strategy]
# Use a preset (overrides entry, exit, risk, indicators)
# preset = "scalping"

# Or configure individually:
# Entry strategies: swing_break, vwap_reversion, orb, rsi_divergence, atr_breakout,
#                   gap_and_go, order_blocks, fvg, liquidity_sweeps
entry = "swing_break"
# Exit strategy: swing, atr, fixed
exit = "swing"
# Risk parameters - tune these via optimizer
swing_lb = 5       # Swing lookback period (in bars)
risk_pct = 0.01    # Risk per trade (1% = 0.01)
rr_ratio = 1.5     # Reward/risk ratio (1.5:1 for day trading)
allow_short = false
# Time-based exits (day trading)
eod_exit = true              # Close all positions before market close
eod_exit_minutes_before = 15 # Minutes before close
time_exit_minutes = 0        # Close after N minutes (0 = disabled)

[tradingbot.bot]
capital = 100000   # Starting capital

[tradingbot.strategy.indicators]
# Indicator filtering for entry signals
# Available: rsi, macd, bollinger, ema_crossover, stochastic, adx, keltner,
#            vwap_bands, volume_profile, pivot_points, fibonacci
enabled = ["rsi", "macd"]  # Indicators to enable
filter_mode = "all"        # "all" (all must pass), "any" (one must pass)
signal_mode = "filter"     # "filter" or "none" (disabled)

[tradingbot.strategy.indicators.rsi]
period = 14
overbought = 70.0
oversold = 30.0

[tradingbot.strategy.indicators.macd]
fast_period = 12
slow_period = 26
signal_period = 9

[tradingbot.strategy.indicators.bollinger]
period = 20
std_dev = 2.0

[tradingbot.strategy.indicators.stochastic]
k_period = 14
d_period = 3
overbought = 80.0
oversold = 20.0

[tradingbot.strategy.indicators.adx]
period = 14
trend_threshold = 25.0

[tradingbot.engine]
# Live trading configuration
broker = "paper"   # Options: "paper", "alpaca"
feed = "yahoo"     # Options: "yahoo", "alpaca"
bar_interval = "5m"

[tradingbot.engine.risk]
# Risk controls
max_daily_loss_pct = 0.05        # Stop trading after 5% daily loss
circuit_breaker_loss_pct = 0.03  # Pause after 3% loss
max_open_positions = 5           # Max concurrent positions
max_position_size_pct = 0.10     # Max 10% of equity per position
trading_hours_only = true        # Only trade 9:30 AM - 4:00 PM ET

[tradingbot.engine.alpaca]
# Use environment variables for API keys:
#   ALPACA_API_KEY, ALPACA_SECRET_KEY
paper = true                     # Use paper trading endpoint

[tradingbot.cache]
source = "yahoo"                 # Default data source for caching
```

### Entry Strategies

| Strategy | Description |
|----------|-------------|
| `swing_break` | Market structure breaks (HH/HL/LH/LL) |
| `vwap_reversion` | Mean reversion to VWAP |
| `orb` | Opening Range Breakout |
| `rsi_divergence` | RSI divergence detection |
| `atr_breakout` | ATR band breakouts |
| `gap_and_go` | Opening gap continuation with momentum |
| `order_blocks` | ICT institutional order zones |
| `fvg` | Fair Value Gaps (imbalance zones) |
| `liquidity_sweeps` | ICT stop hunts at swing points |

### Exit Strategies

| Strategy | Description |
|----------|-------------|
| `swing` | SL at swing point, TP at nearest swing target (≥1R) or R:R fallback |
| `atr` | ATR-based volatility stops |
| `fixed` | Fixed percentage stops |

## Supported Symbols

### Symbol Examples
```python
# US Stocks
"AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"

# ETFs (good for testing)
"SPY", "QQQ", "IWM", "GLD", "TLT"

# Crypto
"BTC-USD", "ETH-USD", "SOL-USD"

# Forex
"EURUSD=X", "GBPUSD=X", "USDJPY=X"
```

### Timeframe Limits
| Interval | Max Period | Use Case |
|----------|------------|----------|
| `1m` | 7 days | Scalping |
| `5m`, `15m` | 60 days | Day trading |
| `1h` | 730 days | Day/swing trading (default) |
| `1d` | Unlimited | Position trading |

## Example Output

### Backtest Results

```
============================================================
BACKTEST: SPY
============================================================
Fetching SPY from Yahoo Finance...
Loaded 502 bars from 2023-11-29 to 2025-11-28

PERFORMANCE SUMMARY
----------------------------------------
  symbol              : SPY
  total_trades        : 10
  winners             : 3
  losers              : 7
  win_rate            : 30.0%
  total_pnl           : $-4,753.09
  total_return        : -4.75%
  profit_factor       : 0.55
  avg_win             : $1,918.00
  avg_loss            : $-1,501.01
  max_drawdown        : 9.17%
  final_capital       : $95,246.91
  avg_holding_period  : 15.1 bars

RECENT TRADES
----------------------------------------
  [LOSS] LONG  | Entry: $604.45 -> Exit: $571.85 | P&L: $-865.94 | STOP_LOSS
  [WIN] SHORT | Entry: $571.85 -> Exit: $501.50 | P&L: $+1,750.32 | TAKE_PROFIT
  [WIN] LONG  | Entry: $638.50 -> Exit: $655.81 | P&L: $+1,910.38 | TAKE_PROFIT
```

**Metrics Explained:**

| Metric | Description |
|--------|-------------|
| `win_rate` | Percentage of profitable trades |
| `total_pnl` | Total profit/loss in dollars |
| `total_return` | Percentage return on starting capital |
| `profit_factor` | Gross profits / Gross losses (>1 is profitable) |
| `max_drawdown` | Largest peak-to-trough decline |
| `avg_holding_period` | Average trade duration in bars |

### Optimization Results

```
======================================================================
OPTIMIZATION REPORT
======================================================================

Tested 128 valid parameter combinations
Symbol: SPY
Data: 502 bars

----------------------------------------
BEST BY TOTAL RETURN:
----------------------------------------
  swing_lookback: 6
  risk_pct:       2.0%
  rr_ratio:       3.0
  ---
  Total Trades:   5
  Win Rate:       100.0%
  Total Return:   +32.61%
  Profit Factor:  999.00
  Max Drawdown:   0.00%

----------------------------------------
TOP 5 PARAMETER SETS:
----------------------------------------
 swing_lookback risk_pct  rr_ratio  total_trades win_rate total_return
              6     2.0%       3.0             5   100.0%      +32.61%
              7     2.0%       3.0             4   100.0%      +25.82%
              6     1.5%       3.0             5   100.0%      +23.76%
```

### Parameter Heatmaps

Shows which parameter combinations perform best:

```
Swing Lookback vs R:R Ratio
R:R
                 1.5       2.0       2.5       3.0
         3     -0.3%     +1.1%     +1.5%    -10.1%
         4     +6.9%     +8.1%     -2.2%     -2.3%
         5     -6.4%     -6.0%     -8.7%     -7.0%
         6     +8.1%    +11.2%    +13.9%    +19.8%  <- Best zone
         7     +6.3%     +8.6%    +10.9%    +15.8%
    Swing LB
```

- **Green**: Above-average performance
- **Yellow**: Near-average performance
- **Red**: Below-average performance

### Overfitting Analysis

```
OVERFITTING ANALYSIS
--------------------------------------------------
Training period: 351 bars
Testing period:  151 bars

Best training params:
  swing_lookback=7, risk=2.0%, rr=3.0
  Training return: +25.82%
  Test return:     +11.00%

Overfitting Assessment:
HIGH RISK: Performance dropped 14.8% on test data
  The optimized parameters may be overfit to historical data
  Recommendation: Use more conservative parameters

Parameter Sensitivity:
  swing_lookback: HIGH sensitivity (+/-7.0%)
  rr_ratio: HIGH sensitivity (+/-6.7%)
```

**Interpretation:**
- Large gaps between training and test returns suggest overfitting
- High sensitivity means small parameter changes cause big performance swings
- Prefer parameters that are stable across different values

## Python API

```python
from tradingbot import (
    run_single_backtest,
    run_multi_backtest,
    optimize,
    MarketStructureBot,
    ParameterRanges,
)

# Run backtest
bot, results = run_single_backtest("AAPL", period="1y", capital=50000)

# Access trades
for trade in bot.trades:
    print(f"{trade.direction} {trade.pnl:+.2f}")

# Multi-symbol comparison
run_multi_backtest(["AAPL", "MSFT", "GOOGL"])

# Optimization
opt = optimize("SPY", period="5y")
opt.plot_heatmap()
opt.check_overfitting()

# Custom bot
bot = MarketStructureBot(
    capital=100000,
    risk_pct=0.02,       # 2% risk per trade
    rr_ratio=2.5,        # 2.5:1 reward/risk
    swing_lb=6,          # 6-bar swing lookback
    trailing_stop=True,  # Move stop to breakeven after 1R profit
)
```

### Live Trading API

```python
import asyncio
from tradingbot import (
    TradingEngine,
    SignalGenerator,
    PositionSizer,
    LiveRiskManager,
    get_broker_registry,
    get_feed_registry,
)
from tradingbot.config import get_bot_config, get_engine_config, get_strategy_config

async def run_trading():
    bot_cfg = get_bot_config()
    strategy_cfg = get_strategy_config()
    engine_cfg = get_engine_config()

    # Get broker and feed from registry
    broker = get_broker_registry().get(engine_cfg.broker)
    feed = get_feed_registry().get(engine_cfg.feed)

    # Create components
    signal_generator = SignalGenerator(strategy_cfg.swing_lb)
    position_sizer = PositionSizer(bot_cfg.capital, strategy_cfg.risk_pct)
    live_risk_manager = LiveRiskManager(engine_cfg.risk, bot_cfg.capital)

    # Create and run engine
    engine = TradingEngine(
        symbols=["SPY", "QQQ"],
        broker=broker,
        feed=feed,
        signal_generator=signal_generator,
        position_sizer=position_sizer,
        live_risk_manager=live_risk_manager,
        rr_ratio=strategy_cfg.rr_ratio,
        allow_short=strategy_cfg.allow_short,
        dry_run=True,  # Set to False for actual paper trading
    )

    await engine.start()
    # Engine runs until stopped

asyncio.run(run_trading())
```

## Adding Custom Strategies

### Custom Entry Strategy

Create a new file in `strategies/entry/`:

```python
# src/tradingbot/_components/strategies/entry/my_strategy.py
import polars as pl
from tradingbot.types import Signal
from ..interfaces import Entry
from ..registry import register_entry

class MyStrategy:
    @property
    def name(self) -> str:
        return "my_strategy"

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add any computed columns (indicators)."""
        return df

    def signal(self, df: pl.DataFrame, idx: int, has_position: bool) -> Entry:
        """Generate BUY/SELL/HOLD signal."""
        if has_position:
            return Entry(Signal.HOLD, "Position open", {})
        # Your signal logic here
        return Entry(Signal.HOLD, "", {})

# Register on import
register_entry(MyStrategy())
```

Then import it in `strategies/registry.py` and update config:

```toml
[tradingbot.strategy]
entry = "my_strategy"
```

### Custom Exit Strategy

Create a new file in `strategies/exit/`:

```python
# src/tradingbot/_components/strategies/exit/my_exit.py
import polars as pl
from tradingbot.types import Direction, SwingPoint
from ..interfaces import Exit
from ..registry import register_exit

class MyExitStrategy:
    @property
    def name(self) -> str:
        return "my_exit"

    def calc(
        self,
        direction: Direction,
        entry: float,
        df: pl.DataFrame,
        swings: list[SwingPoint],
        rr_ratio: float,
    ) -> Exit:
        """Calculate stop-loss and take-profit."""
        if direction == "LONG":
            return Exit(stop_loss=entry * 0.98, take_profit=entry * 1.015)
        return Exit(stop_loss=entry * 1.02, take_profit=entry * 0.985)

# Register on import
register_exit(MyExitStrategy())
```

## Running Tests

```bash
# Using task
task test
task check    # Run lint, typecheck, and tests

# Or using uv directly
uv run pytest -v
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "No data found" | Check symbol spelling (e.g., `BTC-USD` not `BTC`) |
| "Rate limit exceeded" | Wait a few seconds between requests |
| "Not enough swing points" | Increase `--period` or decrease `--swing` value |
| No trades generated | Try different symbols or longer time periods |

## License

MIT

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
uv run tradingbot SPY
uv run tradingbot AAPL TSLA GOOGL
```

### Run Parameter Optimization

```bash
# Using task
task optimize -- SPY
task optimize -- AAPL --heatmap --overfit

# Or using uv directly
uv run tradingbot-optimize SPY
uv run tradingbot-optimize TSLA --swing 5,6,7,8 --rr 2.0,2.5,3.0
```

## CLI Commands

### `tradingbot`

Run backtests on one or more symbols.

```bash
task backtest -- <SYMBOLS> [OPTIONS]

# Or using uv directly
uv run tradingbot <SYMBOLS> [OPTIONS]
```

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--period` | Data period | `2y` |
| `--interval` | Data interval | `1d` |
| `--capital` | Starting capital | config value |
| `--risk` | Risk per trade (e.g., 0.01 for 1%) | config value |
| `--rr` | Reward/risk ratio | config value |
| `--swing-lb` | Swing lookback period | config value |

**Examples:**

```bash
task backtest -- SPY
task backtest -- AAPL TSLA GOOGL
task backtest -- SPY --period 5y --interval 1d
task backtest -- AAPL --capital 50000 --risk 0.02
```

### `tradingbot-optimize`

Optimize trading parameters with grid search.

```bash
task optimize -- <SYMBOL> [OPTIONS]

# Or using uv directly
uv run tradingbot-optimize <SYMBOL> [OPTIONS]
```

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--period` | Data period | `2y` |
| `--interval` | Data interval | `1d` |
| `--capital` | Starting capital | `100000` |
| `--heatmap` | Show parameter heatmaps | - |
| `--overfit` | Run overfitting analysis | - |
| `--plot` | Show parameter impact charts | - |
| `--swing` | Swing lookback values (comma-separated) | `3,4,5,6,7,8,9,10` |
| `--risk` | Risk percentages (comma-separated) | `0.005,0.01,0.015,0.02` |
| `--rr` | Reward/risk ratios (comma-separated) | `1.5,2.0,2.5,3.0` |

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

# Replay mode (simulate live trading with historical data)
task replay -- SPY
task replay -- SPY --speed 10
task replay -- SPY --speed 0 --from 2024-01-01 --to 2024-06-30

# TUI mode (interactive terminal dashboard)
task replay -- SPY --tui --dry-run
```

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--dry-run` | Log signals without executing trades | - |
| `--replay` | Replay historical data as live | - |
| `--speed` | Replay speed (bars/sec, 0=instant) | `1.0` |
| `--from` | Replay start date (YYYY-MM-DD) | - |
| `--to` | Replay end date (YYYY-MM-DD) | - |
| `--period` | Historical period for replay | `1d` |
| `--interval` | Bar interval for replay | `15m` |
| `--tui` | Interactive terminal UI dashboard | - |

**Risk Controls (configured in `tradingbot.toml`):**

| Control | Description | Default |
|---------|-------------|---------|
| Circuit breaker | Pause trading after X% daily loss | 3% |
| Max daily loss | Stop trading after X% daily loss | 5% |
| Max positions | Maximum concurrent positions | 5 |
| Max position size | Maximum % of equity per position | 10% |
| Trading hours | Only trade 9:30 AM - 4:00 PM ET | Yes |

## Configuration

Create `tradingbot.toml` in your project root:

```toml
[tradingbot]
fetcher = "yahoo"

[tradingbot.strategy]
# Options: "swing", "atr"
stop = "swing"

[tradingbot.bot]
# Bot parameters - tune these via optimizer
swing_lb = 5       # Swing lookback period (in bars)
risk_pct = 0.01    # Risk per trade (1% = 0.01)
rr_ratio = 2.0     # Reward/risk ratio
capital = 100000   # Starting capital

[tradingbot.engine]
# Engine configuration
broker = "paper"   # Options: "paper", "alpaca"
feed = "yahoo"     # Options: "yahoo", "alpaca"
symbols = ["SPY"]  # Default symbols to trade

[tradingbot.engine.risk]
# Risk controls
max_daily_loss_pct = 0.05        # Stop trading after 5% daily loss
circuit_breaker_loss_pct = 0.03  # Pause after 3% loss
max_open_positions = 5           # Max concurrent positions
max_position_size_pct = 0.10     # Max 10% of equity per position
trading_hours_only = true        # Only trade 9:30 AM - 4:00 PM ET

[tradingbot.engine.alpaca]
# Alpaca API credentials (for live/paper trading with Alpaca)
api_key = "your-api-key"
secret_key = "your-secret-key"
paper = true                     # Use paper trading endpoint
```

### Stop-Loss Strategies

- **swing**: Places stops below/above recent swing points (default)
- **atr**: Uses Average True Range for volatility-based stops

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
| `1h` | 730 days | Swing trading |
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
bot, results = run_single_backtest("AAPL", period="2y", capital=50000)

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
    RiskManager,
    LiveRiskManager,
    get_broker_registry,
    get_feed_registry,
)
from tradingbot.config import get_bot_config, get_engine_config

async def run_trading():
    cfg = get_bot_config()
    engine_cfg = get_engine_config()

    # Get broker and feed from registry
    broker = get_broker_registry().get(engine_cfg.broker)
    feed = get_feed_registry().get(engine_cfg.feed)

    # Create components
    signal_generator = SignalGenerator(cfg.swing_lb)
    risk_manager = RiskManager(cfg.capital, cfg.risk_pct, cfg.rr_ratio)
    live_risk_manager = LiveRiskManager(engine_cfg.risk, cfg.capital)

    # Create and run engine
    engine = TradingEngine(
        symbols=["SPY", "QQQ"],
        broker=broker,
        feed=feed,
        signal_generator=signal_generator,
        risk_manager=risk_manager,
        live_risk_manager=live_risk_manager,
        dry_run=True,  # Set to False for actual paper trading
    )

    await engine.start()
    # Engine runs until stopped

asyncio.run(run_trading())
```

## Adding Custom Strategies

### Custom Stop-Loss Strategy

Create a new file in `_strategies/plugins/`:

```python
# src/tradingbot/_components/_strategies/plugins/custom.py
import pandas as pd
from ...models import Direction, SwingPoint

class CustomStopStrategy:
    @property
    def name(self) -> str:
        return "custom"

    def calc_stop(
        self,
        direction: Direction,
        entry: float,
        df: pd.DataFrame,
        idx: int,
        swings: list[SwingPoint],
    ) -> float:
        # Your stop-loss logic here
        return entry * 0.95 if direction == "LONG" else entry * 1.05
```

Then update `tradingbot.toml`:

```toml
[tradingbot.strategy]
stop = "custom"
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

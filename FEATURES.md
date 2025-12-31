# Trading Bot Features

A comprehensive market structure trading bot with backtesting, live trading, and parameter optimization capabilities.

---

## Implemented Features

### Entry Strategies

Entry strategies generate BUY/SELL signals based on various market conditions.

| Strategy | Description | File |
|----------|-------------|------|
| [x] `swing_break` | Market structure breaks (HH/HL/LH/LL) with pullback confirmation | `strategies/entry/swing_break.py` |
| [x] `vwap_reversion` | Mean reversion to VWAP with z-score thresholds | `strategies/entry/vwap_reversion.py` |
| [x] `orb` | Opening Range Breakout (first 30min high/low) | `strategies/entry/orb.py` |
| [x] `rsi_divergence` | RSI divergence detection at swing points | `strategies/entry/rsi_divergence.py` |
| [x] `atr_breakout` | ATR band breakouts with volatility confirmation | `strategies/entry/atr_breakout.py` |
| [x] `gap_and_go` | Opening gap continuation with momentum | `strategies/entry/gap_and_go.py` |
| [x] `order_blocks` | ICT institutional order zones | `strategies/entry/order_blocks.py` |
| [x] `fvg` | Fair Value Gaps (price imbalance zones) | `strategies/entry/fair_value_gaps.py` |
| [x] `liquidity_sweeps` | ICT stop hunts at swing points | `strategies/entry/liquidity_sweeps.py` |
| [x] `orb_fvg` | ORB combined with Fair Value Gap confirmation | `strategies/entry/orb_fvg.py` |
| [x] `orb_fvg_simple` | ORB+FVG retest without engulfing confirmation | `strategies/entry/orb_fvg.py` |

### Exit Strategies

Exit strategies calculate stop-loss and take-profit levels.

| Strategy | Description | File |
|----------|-------------|------|
| [x] `swing` | SL at swing point, TP at nearest swing target or R:R fallback | `strategies/exit/swing.py` |
| [x] `atr` | ATR-based volatility stops and targets | `strategies/exit/atr.py` |
| [x] `fixed` | Fixed percentage from entry price | `strategies/exit/fixed.py` |

### Indicators

Technical indicators for signal filtering and confirmation.

| Indicator | Purpose | Filter Logic |
|-----------|---------|--------------|
| [x] RSI | Overbought/oversold detection | Block BUY if RSI > 70, SELL if RSI < 30 |
| [x] MACD | Trend direction | Block signals against MACD histogram |
| [x] Bollinger Bands | Volatility & mean reversion | Block during squeeze (low bandwidth) |
| [x] EMA Crossover | Trend direction (9/21 EMA) | Block signals against EMA trend |
| [x] Stochastic | Momentum extremes | Block BUY if %K > 80, SELL if %K < 20 |
| [x] ADX | Trend strength | Require +DI/-DI alignment with signal |
| [x] Keltner Channels | Squeeze detection with BB | Filter based on channel position |
| [x] VWAP Bands | Dynamic S/R levels | Block signals too close to VWAP |
| [x] Volume Profile | Key price levels (POC/VAH/VAL) | Confirm signals near key levels |
| [x] Pivot Points | Pre-market S/R levels | Confirm signals based on pivot position |
| [x] Fibonacci | Pullback levels | Require signal alignment with Fib trend |

### Risk Management

| Feature | Description | File |
|---------|-------------|------|
| [x] Fixed percentage risk | Risk X% of capital per trade | `risk.py` |
| [x] ATR-based position sizing | Scale position size inversely with volatility | `risk.py` |
| [x] Partial profit taking | Exit portions at R-multiples (e.g., 50% at 1R) | `bot.py` |
| [x] Trailing stop to breakeven | Move stop to entry after 1R profit | `bot.py` |
| [x] ATR-based trailing stop | Trail stop at high_water - (N x ATR) | `bot.py` |
| [x] ATR trail activation threshold | Start trailing only after X R-multiple profit | `bot.py` |
| [x] EOD exit | Close all positions before market close | `bot.py` |
| [x] Time-based exit | Close position after N minutes | `bot.py` |

### Live Trading Risk Controls

| Feature | Description | File |
|---------|-------------|------|
| [x] Circuit breaker | Pause trading after X% daily loss | `live_risk.py` |
| [x] Max daily loss | Stop trading after X% daily loss | `live_risk.py` |
| [x] Max open positions | Limit concurrent positions | `live_risk.py` |
| [x] Max position size | Limit % of equity per position | `live_risk.py` |
| [x] Trading hours filter | Only trade 9:30 AM - 4:00 PM ET | `live_risk.py` |

### Backtesting

| Feature | Description | File |
|---------|-------------|------|
| [x] Historical data from Yahoo Finance | Fetch OHLCV data for any symbol | `feeds/plugins/yahoo.py` |
| [x] Execution cost modeling | Slippage, spread, and commission | `execution.py` |
| [x] Performance metrics | Win rate, profit factor, Sharpe, Calmar, max drawdown | `bot.py` |
| [x] Trade logging | Detailed trade history with P&L | `runner.py` |
| [x] Verbose mode | Bar-by-bar signal visualization | `runner.py` |
| [x] Speed simulation | Simulate real-time bar processing | `runner.py` |
| [x] Multi-symbol comparison | Run backtests on multiple symbols | `runner.py` |
| [x] Replay mode | Replay historical data as live stream | `feeds/plugins/replay.py` |

### Parameter Optimization

| Feature | Description | File |
|---------|-------------|------|
| [x] Grid search optimization | Exhaustive parameter combination testing | `optimize.py` |
| [x] Optuna smart sampling | TPE sampler for efficient search | `tuner.py` |
| [x] Walk-forward validation | Train/test split to detect overfitting | `walk_forward.py` |
| [x] Multiple objectives | Return, Calmar ratio, profit factor, multi-objective | `tuner.py` |
| [x] Pareto front analysis | Find optimal risk/return trade-offs | `tuner.py` |
| [x] Parameter sensitivity analysis | Identify stable vs sensitive parameters | `optimize.py` |
| [x] Heatmap visualization | Visualize parameter performance | `optimize.py` |
| [x] Preset saving | Save best parameters as reusable presets | `presets.py` |

### Presets

Pre-configured trading setups for different styles.

**Day Trading Presets:**
| Preset | Interval | Entry | Exit | Risk | R:R |
|--------|----------|-------|------|------|-----|
| [x] `scalping` | 5m | orb | fixed | 0.5% | 1.5:1 |
| [x] `orb_fvg` | 1m | orb_fvg | fixed | 0.5% | 3.0:1 |
| [x] `orb_fvg_simple` | 1m | orb_fvg_simple | fixed | 0.5% | 2.0:1 |
| [x] `day_momentum` | 15m | atr_breakout | atr | 1.0% | 1.5:1 |
| [x] `mean_reversion` | 15m | vwap_reversion | fixed | 1.0% | 1.2:1 |
| [x] `day_breakout` | 15m | atr_breakout | atr | 1.0% | 1.5:1 |

**Swing Trading Presets:**
| Preset | Interval | Entry | Exit | Risk | R:R |
|--------|----------|-------|------|------|-----|
| [x] `swing_conservative` | 1h | swing_break | swing | 0.5% | 2.0:1 |
| [x] `swing_balanced` | 1h | swing_break | swing | 1.0% | 2.0:1 |
| [x] `swing_aggressive` | 1h | swing_break | atr | 2.0% | 2.5:1 |
| [x] `divergence` | 1h | rsi_divergence | swing | 1.0% | 2.0:1 |

### Live Trading

| Feature | Description | File |
|---------|-------------|------|
| [x] Paper trading broker | Simulated order execution | `brokers/plugins/paper.py` |
| [x] Alpaca broker integration | Real paper/live trading via Alpaca API | `brokers/plugins/alpaca.py` |
| [x] Real-time data feed (Alpaca) | Live market data streaming | `feeds/plugins/alpaca.py` |
| [x] Event-driven engine | Async event processing for live trading | `engine/engine.py` |
| [x] Signal generator | Real-time signal generation | `signals.py` |
| [x] Position tracker | Track open positions and P&L | `engine/engine.py` |

### Data Management

| Feature | Description | File |
|---------|-------------|------|
| [x] Local DuckDB cache | Cache market data locally | `cache/` |
| [x] 1-minute bar storage | Store granular intraday data | `cache.py` |
| [x] Time-based aggregation | Aggregate 1m bars to 5m, 15m, 1h, 1d | `cache.py` |
| [x] Retention policy | Auto-purge old data (1m: 7d, 5m: 30d, etc.) | `cache.py` |
| [x] Cache statistics | View symbol counts, bar counts, date ranges | `cache_cli.py` |
| [x] Cache maintenance | Run aggregation and purge in one command | `cache_cli.py` |

### UI/TUI (Terminal User Interface)

| Feature | Description | File |
|---------|-------------|------|
| [x] Interactive dashboard | Textual-based TUI for live trading | `tui/app.py` |
| [x] Symbol cards | Real-time price and signal display per symbol | `tui/widgets/symbol_card.py` |
| [x] Position panel | Open positions with unrealized P&L | `tui/widgets/position_panel.py` |
| [x] Stats bar | Session statistics (trades, win rate, P&L) | `tui/widgets/stats_bar.py` |
| [x] Signal log | Recent signal history with details | `tui/widgets/signal_log.py` |
| [x] Status bar | Connection status, trading mode | `tui/widgets/status_bar.py` |
| [x] Sparkline charts | Mini price charts in terminal | `tui/widgets/sparkline.py` |
| [x] Log panel | Real-time log output | `tui/widgets/log_panel.py` |

### Web UI

| Feature | Description | File |
|---------|-------------|------|
| [x] React dashboard | Web-based trading dashboard | `web/src/App.tsx` |
| [x] Price charts | Interactive price charts with TradingView | `web/src/components/charts/PriceChart.tsx` |
| [x] Symbol grid | Multi-symbol price display | `web/src/components/cards/SymbolGrid.tsx` |
| [x] Stats panel | Session performance metrics | `web/src/components/panels/StatsPanel.tsx` |
| [x] Risk meter | Visual risk status display | `web/src/components/panels/RiskMeter.tsx` |
| [x] Account panel | Account balance and equity | `web/src/components/panels/AccountPanel.tsx` |
| [x] Trade log | Trade history with details | `web/src/components/trade-log/TradeLog.tsx` |
| [x] WebSocket updates | Real-time data via WebSocket | `web/src/hooks/useWebSocket.ts` |

### Event Hub

| Feature | Description | File |
|---------|-------------|------|
| [x] Central event dispatcher | Broadcast updates to TUI/Web clients | `hub/hub.py` |
| [x] State management | Global state for tickers, positions, stats | `hub/hub.py` |
| [x] WebSocket broadcasting | Push updates to web clients | `hub/hub.py` |
| [x] Callback system | Subscribe/unsubscribe to specific channels | `hub/hub.py` |
| [x] WebSocket server | WebSocket server for real-time web updates | `hub/server.py` |

### System Components

| Feature | Description | File |
|---------|-------------|------|
| [x] Callback manager | Event-driven callbacks for async operations | `engine/callbacks.py` |
| [x] Event types | Typed events for bar, signal, order, trade | `engine/events.py` |
| [x] Cached feed wrapper | Transparent caching layer for data feeds | `cache/cached_feed.py` |
| [x] Sound notifications | Audio alerts for trades and signals | `sounds.py` |

### CLI Commands

| Command | Description | File |
|---------|-------------|------|
| [x] `tradingbot-backtest` | Run backtests on symbols | `backtest_cli.py` |
| [x] `tradingbot-optimize` | Grid search parameter optimization | `optimize_cli.py` |
| [x] `tradingbot-optuna` | Optuna smart optimization | `optuna_cli.py` |
| [x] `tradingbot-live` | Live/paper trading | `cli.py` |
| [x] `tradingbot-cache` | Cache management (stats, fetch, maintain) | `cache_cli.py` |

---

## Planned Features

### High Priority

| Feature | Description | Status |
|---------|-------------|--------|
| [ ] ML signal filter | Random Forest classifier to filter low-probability signals | `roadmap/plan-rf-signal-filter.md` |
| [ ] Strategy parameter cleanup | Replace magic numbers with configurable parameters | `roadmap/plan-business-logic-improvements.md` |
| [ ] MCP server | Model Context Protocol server for AI integration | `roadmap/plan-mcp-server.md` |

### Medium Priority

| Feature | Description | Status |
|---------|-------------|--------|
| [ ] TA-Lib dynamic indicators | Config-driven indicators using TA-Lib | `roadmap/plan-talib-dynamic-indicators.md` |
| [ ] Candlestick pattern recognition | 61 TA-Lib patterns for entry/filter | `roadmap/plan-talib-dynamic-indicators.md` |
| [ ] Volume confirmation | OBV, MFI, AD indicators for volume-based filtering | `roadmap/plan-talib-dynamic-indicators.md` |
| [ ] Regime detection | Switch strategies based on trending/ranging market | `roadmap/plan-talib-dynamic-indicators.md` |
| [ ] AI trade explanations | LLM-powered signal explanations via Ollama | `roadmap/plan-ai-explanations.md` |

### Ideas

| Feature | Description |
|---------|-------------|
| [ ] Ensemble ML models | Combine RF with XGBoost, LightGBM |
| [ ] Symbol-specific models | Train separate ML models per symbol/sector |
| [ ] A/B testing | Compare filter vs no-filter in paper trading |
| [ ] Monte Carlo simulation | Statistical validation of strategy robustness |
| [ ] Multi-timeframe analysis | Combine signals from multiple timeframes |
| [ ] News sentiment filter | Filter signals based on news sentiment |
| [ ] Options integration | Support options trading strategies |
| [ ] Portfolio-level risk | Cross-position correlation and risk management |
| [ ] Alerting system | Webhook/email notifications for signals |
| [ ] Logging framework | File-based structured logging |

---

## Configuration Reference

All features are configurable via `tradingbot.toml`:

```toml
[tradingbot.strategy]
entry = "swing_break"           # Entry strategy
exit = "swing"                  # Exit strategy
swing_lb = 5                    # Swing lookback period
risk_pct = 0.01                 # Risk per trade (1%)
rr_ratio = 1.5                  # Reward/risk ratio
allow_short = false             # Allow short positions
atr_sizing = false              # Volatility-adjusted sizing
atr_trail = false               # ATR-based trailing stop
atr_trail_multiplier = 2.0      # ATR trail distance multiplier
atr_trail_activation_r = 0.0    # Start trailing after X R profit
eod_exit = true                 # Close positions at EOD
# partial_exit_levels = [{r_multiple = 1.0, exit_pct = 0.5}]

[tradingbot.strategy.indicators]
enabled = ["rsi", "macd"]       # Active indicators
filter_mode = "all"             # "all" or "any"
signal_mode = "filter"          # "filter" or "none"

[tradingbot.engine.risk]
max_daily_loss_pct = 0.05       # Max daily loss (5%)
circuit_breaker_loss_pct = 0.03 # Circuit breaker (3%)
max_open_positions = 5          # Max concurrent positions
max_position_size_pct = 0.10    # Max position size (10%)
trading_hours_only = true       # Trading hours filter
```

---

## File Structure

```
src/tradingbot/
|-- _components/
|   |-- strategies/
|   |   |-- entry/              # Entry strategies (11 strategies)
|   |   |-- exit/               # Exit strategies (3 strategies)
|   |   |-- interfaces.py       # Strategy protocols
|   |   |-- registry.py         # Strategy registration
|   |-- indicators/
|   |   |-- plugins/            # 11 indicator plugins
|   |   |-- registry.py         # Indicator registration
|   |-- brokers/plugins/        # Paper, Alpaca brokers
|   |-- feeds/plugins/          # Yahoo, Alpaca, Replay feeds
|   |-- engine/                 # Live trading engine
|   |-- hub/                    # Event hub for UI updates
|   |-- tui/                    # Terminal UI widgets
|   |-- bot.py                  # Backtest bot core
|   |-- execution.py            # Execution cost modeling
|   |-- live_risk.py            # Live risk management
|   |-- presets.py              # Trading presets
|   |-- runner.py               # Backtest runner
|   |-- signals.py              # Signal generation
|   |-- tuner.py                # Optuna optimization
|-- backtest_cli.py             # Backtest CLI
|-- optuna_cli.py               # Optuna CLI
|-- optimize_cli.py             # Grid search CLI
|-- cli.py                      # Live trading CLI
|-- cache_cli.py                # Cache management CLI
|-- config.py                   # Configuration loading
web/                            # React web dashboard
roadmap/                        # Planned feature specs
```

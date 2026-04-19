---
name: backtest
description: Run a backtest for a symbol. Usage: /backtest SPY or /backtest AAPL --preset orb_fvg
user_invocable: true
---

Run a backtest using the backtester agent. Parse the user's arguments to extract:

1. **Symbol(s)**: Required - stock ticker(s) to backtest (e.g., SPY, AAPL, TSLA)
2. **Options**: Any CLI flags passed (--preset, --strategy, --period, etc.)

Use the Task tool to launch the `backtest` agent with the full command.

Example inputs:
- `/backtest SPY` → backtest SPY with defaults
- `/backtest AAPL --preset scalping` → backtest AAPL with scalping preset
- `/backtest TSLA --strategy orb --period 3mo` → backtest TSLA with ORB strategy for 3 months

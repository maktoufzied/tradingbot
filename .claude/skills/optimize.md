---
name: optimize
description: Run parameter optimization for a symbol. Usage: /optimize SPY or /optimize AAPL --trials 100
user_invocable: true
---

Run Optuna-based parameter optimization using the optimizer agent. Parse the user's arguments:

1. **Symbol**: Required - stock ticker to optimize
2. **Options**: Any CLI flags (--trials, --strategy, --period, etc.)

Use the Task tool to launch the `optimize` agent with the full command.

Example inputs:
- `/optimize SPY` → find optimal parameters for SPY
- `/optimize AAPL --trials 100` → run 100 optimization trials for AAPL

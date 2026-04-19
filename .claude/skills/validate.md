---
name: validate
description: Validate recent trading code changes for correctness and day trading best practices
user_invocable: true
---

Validate trading code changes using the day-trader-validator agent.

1. First, run `git diff --name-only` to identify changed files
2. Filter for functional trading code:
   - `strategies/entry/` or `strategies/exit/`
   - `signals.py`, `bot.py`, `runner.py`
   - `sizing.py`, `live_risk.py`, `risk_manager.py`
   - `indicators/`
   - `execution.py`, `brokers/`
3. Use the Task tool to launch `day-trader-validator` with the relevant file contents

This skill should be called proactively after modifying any trading logic.

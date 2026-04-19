---
name: live
description: Start live trading or paper trading. Usage: /live SPY or /live AAPL --paper
user_invocable: true
---

Start live or paper trading session.

Parse the user's arguments:
1. **Symbol(s)**: Stock ticker(s) to trade
2. **Mode**: `--paper` for paper trading (default), `--live` for real money
3. **Options**: Other CLI flags

IMPORTANT: Always confirm with the user before starting live (non-paper) trading.

Commands:
```bash
# Paper trading (safe)
source .env && uv run tradingbot-live SYMBOL --paper

# Live trading (REQUIRES CONFIRMATION)
source .env && uv run tradingbot-live SYMBOL
```

Example inputs:
- `/live SPY` → paper trade SPY
- `/live AAPL --paper --preset scalping` → paper trade with preset
- `/live TSLA --live` → REQUIRES EXPLICIT USER CONFIRMATION

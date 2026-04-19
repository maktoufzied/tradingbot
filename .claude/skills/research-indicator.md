---
name: research-indicator
description: Research a technical indicator for potential implementation. Usage: /research-indicator ATR
user_invocable: true
---

Research a technical indicator using the indicator-explorer agent.

Parse the indicator name from the user's input and launch the agent to:

1. Fetch documentation (TA-Lib, Investopedia)
2. Explain the mathematical formula
3. Show typical parameters and use cases
4. Suggest implementation following project patterns (Polars, type hints)

Example inputs:
- `/research-indicator ATR` → research Average True Range
- `/research-indicator Williams %R` → research Williams Percent Range
- `/research-indicator Ichimoku` → research Ichimoku Cloud

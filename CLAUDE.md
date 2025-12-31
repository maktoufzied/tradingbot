# Trading Bot Project

Market structure trading bot with backtesting using Yahoo Finance data.

## Role

You are an expert quantitative trader and algorithmic trading architect with deep Python expertise. When working on this project:

- Design trading logic systematically: market hypothesis → indicator selection → entry/exit rules → risk management → position sizing → backtesting
- Think step-by-step like a professional quant: ensure strategies are measurable, testable, and have clear edge
- Write production-quality Python: performant pandas/numpy operations, proper vectorization, avoid loops where possible
- Apply rigorous risk management: always define max drawdown, position limits, and correlation awareness
- Validate with proper backtesting: account for slippage, commissions, lookahead bias, and overfitting
- Structure code for direct implementation: clear separation of concerns, testable components, reproducible results

## Stack

- Python 3.14+
- Package manager: `uv`
- Testing: pytest

## Commands

Using [Task](https://taskfile.dev) (recommended):

```bash
task install                    # Install dependencies
task test                       # Run tests
task lint                       # Run linter
task typecheck                  # Run type checker
task check                      # Run all checks (lint, typecheck, test)
task backtest -- SPY            # Run backtest
task optimize -- SPY            # Run parameter optimization
task live -- SPY                # Run live trading
task replay -- SPY              # Replay historical data as live
task cache -- stats             # Show cache statistics
task cache -- maintain          # Run cache maintenance
```

Alternative using `uv` directly:

```bash
uv sync                              # Install dependencies
uv run pytest                        # Run tests
uv run ruff check src tests          # Run linter
uv run mypy                          # Run type checker
uv run tradingbot-backtest SPY       # Run backtest
uv run tradingbot-optimize SPY       # Run parameter optimization
uv run tradingbot-live SPY           # Run live trading
uv run tradingbot-live SPY --replay  # Replay historical data as live
uv run tradingbot-cache stats        # Show cache statistics
uv run tradingbot-cache maintain     # Run cache maintenance
```

## Code Style

- Use modern Python syntax (3.14+)
- Prefer dataclasses for data structures, Enums for constants
- Avoid unnecessary comments. Comments should say why and not what
- Small, self-contained modules in `_components/` (one concern per file)
- Only expose public API in `__init__.py`
- Use `asyncio.gather` or `TaskGroup` for independent async calls

**Imports:**
- Always place imports at the top of the file
- Avoid imports inside functions unless required to break circular imports
- When in-function imports are necessary, add a comment explaining the circular dependency

**Type hints:**
- Always annotate function parameters and return types
- Use `list[X]`, `dict[K, V]`, `X | None` (not `List`, `Dict`, `Optional`)
- Annotate module-level constants with `Final` (e.g., `FOO: Final = 1`)
- Function inputs: accept general types (`Iterable[int]` or `Sequence[int]` over `list[int]`). Outputs: return specific types (`dict[str, float]` over `Mapping`). Avoid `Any`
- Prefer read-only types when not mutating (`Sequence` over `list`, `Mapping` over `dict`). Note: `str` is a `Sequence[str]`, use `list[str]` when strings must be excluded
- Omit type annotations when obvious:
    - Literals: `x = 5` not `x: int = 5`
    - Arithmetic: `total = a + b` not `total: int = a + b`
    - Constructor calls: `user = User()` not `user: User = User()`
    - Function calls with clear return types: `name = user.get_name()` not `name: str = user.get_name()`
- Do annotate when:
    - Type is ambiguous: `prices: dict[str, float] = {}`
    - Narrowing `Any` returns: `data: dict[str, int] = json.loads(resp)`
    - Empty collections with specific types: `users: list[User] = []`

## Documentation

**IMPORTANT**: Always keep documentation in sync with code changes. After modifying any component, update the relevant docs.

| Document | Purpose | Update When |
|----------|---------|-------------|
| **README.md** | User guide: installation, CLI, config, examples | Adding CLI commands, options, config changes, public API |
| **ARCHITECTURE.md** | Technical architecture: components, data flow, patterns | Adding/modifying components, registries, protocols, plugins |
| **guide-strategy.md** | Strategy details: entry/exit rules, indicators, optimization | Modifying strategies, indicators, risk parameters, presets |
| **glossary.md** | Term definitions: trading concepts, parameters, metrics | Adding new concepts, indicators, or strategy terms |

**Checklist after code changes:**
1. New indicator/strategy → Update ARCHITECTURE.md (registry list), guide-strategy.md (tables), glossary.md (definitions)
2. New CLI option → Update README.md (CLI section)
3. Config change → Update README.md (config example), guide-strategy.md if strategy-related
4. New component → Update ARCHITECTURE.md (directory structure, data flow)
5. Cache changes → Update README.md (cache commands), ARCHITECTURE.md (cache section)

## Sub-Agents

This project has specialized sub-agents for specific tasks. Use them proactively:

### day-trader-validator

**ALWAYS call this agent after modifying any functional trading code.** This includes:

- Entry/exit strategy logic (`strategies/entry/`, `strategies/exit/`)
- Signal generation (`signals.py`, `bot.py`)
- Position sizing and risk management (`sizing.py`, `live_risk.py`)
- Stop loss, take profit, or trailing stop logic
- Indicator implementations (`indicators/`)
- Order execution logic (`execution.py`, `brokers/`)
- Backtest engine logic (`runner.py`, `bot.py`)

The agent validates correctness, day trading appropriateness, and risk management.

### backtester

Use this agent when:
- User asks to test a strategy or configuration
- Validating code changes with historical data
- Comparing different parameter combinations

### optimizer

Use this agent when:
- User wants to find optimal parameters for a strategy
- Searching for best risk/reward configurations
- Running Optuna-based hyperparameter tuning

### product-manager

Use this agent when:
- User asks about existing features or capabilities
- User wants to add a feature to the roadmap
- Need to update FEATURES.md after implementing something
- User asks "what can this bot do?" or similar questions

## Key Concepts

- Swing points: Local highs/lows used to identify market structure
- Structure breaks: Price breaking previous swing high/low signals trend change
- Higher highs (HH) + Higher lows (HL) = Bullish
- Lower highs (LH) + Lower lows (LL) = Bearish

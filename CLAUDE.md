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
```

Alternative using `uv` directly:

```bash
uv sync                              # Install dependencies
uv run pytest                        # Run tests
uv run ruff check src tests          # Run linter
uv run mypy                          # Run type checker
uv run tradingbot SPY                # Run backtest
uv run tradingbot-optimize SPY       # Run parameter optimization
uv run tradingbot-live SPY           # Run live trading
uv run tradingbot-live SPY --replay  # Replay historical data as live
```

## Code Style

- Use modern Python syntax (3.14+)
- Prefer dataclasses for data structures, Enums for constants
- Avoid unnecessary comments. Comments should say why and not what
- Small, self-contained modules in `_components/` (one concern per file)
- Only expose public API in `__init__.py`
- Use `asyncio.gather` or `TaskGroup` for independent async calls

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

- **README.md**: User-facing documentation. Update when adding CLI commands, options, or changing the public API
- **guide-strategy.md**: Trading strategy specification. Update when modifying entry/exit rules or risk parameters
- **glossary.md**: Definitions for trading terms, parameters, and metrics (swing_lb, rr_ratio, profit factor, etc.)

## Key Concepts

- Swing points: Local highs/lows used to identify market structure
- Structure breaks: Price breaking previous swing high/low signals trend change
- Higher highs (HH) + Higher lows (HL) = Bullish
- Lower highs (LH) + Lower lows (LL) = Bearish

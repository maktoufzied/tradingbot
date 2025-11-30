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
```

Alternative using `uv` directly:

```bash
uv sync                         # Install dependencies
uv run pytest                   # Run tests
uv run ruff check src tests     # Run linter
uv run mypy                     # Run type checker
uv run tradingbot SPY           # Run backtest
uv run tradingbot-optimize SPY  # Run parameter optimization
uv run tradingbot-live SPY      # Run live trading
```

## Code Style

- Use modern Python syntax (3.14+)
- Type hints: `list[X]`, `dict[K, V]`, `X | None` (not `List`, `Dict`, `Optional`)
- Omit type annotations when the type is obvious from context:
    - Literals: `x = 5` not `x: int = 5`
    - Arithmetic with typed operands: `total = a + b` not `total: int = a + b`
    - Constructor calls: `items = []` not `items: list = []`
    - Function calls with clear return types: `name = user.get_name()` not `name: str = user.get_name()`
    Do annotate when:
    - Type is ambiguous: `data: dict[str, Any] = {}`
    - Return type narrowing: `result: User | None = cache.get(id)`
    - Empty collections with specific types: `users: list[User] = []`
    - Dataclasses for data structures, Enums for constants
- Small, self-contained modules in `_components/` (one concern per file)
- Only expose public API in `__init__.py`
- Avoid unecessary comments. Comments should say why and not what
- Annotate module-level constants with `Final[T]` (e.g., `FOO: Final[int] = 1`)
- When designing functions or APIs, apply contravariance to function inputs by accepting reasonably general types (e.g., Iterable[str]) rather than overly specific ones, and apply covariance to outputs by returning the most specific structured types possible (e.g., dict[str, float] rather than dict). Avoid using Any unless absolutely necessary, as it weakens type safety and clarity

## Documentation

- **README.md**: User-facing documentation. Update when adding CLI commands, options, or changing the public API
- **guide-strategy.md**: Trading strategy specification. Update when modifying entry/exit rules or risk parameters

## Key Concepts

- Swing points: Local highs/lows used to identify market structure
- Structure breaks: Price breaking previous swing high/low signals trend change
- Higher highs (HH) + Higher lows (HL) = Bullish
- Lower highs (LH) + Lower lows (LL) = Bearish

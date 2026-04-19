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

## Slash Commands (Skills)

Quick actions available via `/command`:

| Command | Description |
|---------|-------------|
| `/backtest SPY` | Run backtest for a symbol |
| `/optimize SPY` | Run parameter optimization |
| `/validate` | Validate recent trading code changes |
| `/sync-docs` | Check which docs need updating |
| `/research-indicator ATR` | Research a technical indicator |
| `/design-ui risk meter` | Design a UI component |
| `/live SPY` | Start paper trading |
| `/check` | Run all code quality checks |

## Sub-Agents

This project has specialized sub-agents for specific tasks. Use them proactively:

### cto

Use this agent for high-level architectural decisions:

- Evaluating different technical approaches (e.g., single engine vs. multi-engine)
- Designing new system components
- Making trade-offs between complexity, maintainability, and extensibility
- Planning implementation phases for large features

The agent provides structured analysis with options, trade-offs, and recommendations.

### code-reviewer

**ALWAYS call this agent at the end of any significant code change.** This includes:

- New modules or files
- Modified functions or classes
- Bug fixes
- Refactoring

The agent checks for:
- Code quality issues and potential bugs
- Adherence to project conventions (type hints, imports, style)
- Error handling and edge cases
- Security concerns

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

### docs-sync

**Call this agent after completing significant code changes.** It analyzes modified files and reports which documentation needs updating:

- README.md (CLI, config, user-facing changes)
- ARCHITECTURE.md (components, data flow, patterns)
- guide-strategy.md (strategies, indicators, parameters)
- glossary.md (new terms, concepts)

The agent provides specific recommendations for what to update in each file.

### indicator-explorer

Use this agent when:
- Researching a new technical indicator for potential implementation
- Need to understand how an indicator works mathematically
- Want TA-Lib function signatures and parameters
- Planning how to integrate an indicator into the codebase

The agent provides implementation suggestions following project patterns (Polars, type hints, naming conventions).

### ux-designer

Use this agent when:
- Adding new UI components to TUI or Web dashboard
- Redesigning existing interface layouts
- Reviewing usability of trading workflows
- Ensuring consistency between TUI and Web interfaces

The agent provides mockups, design rationale, and implementation notes for both Textual (TUI) and React/Tailwind (Web).

### frontend-dev

Use this agent when:
- Implementing React/Tailwind UI components from mockups
- Building new dashboard features following the design system
- Ensuring code adheres to `web/DESIGN_SYSTEM.md` patterns
- Converting ux-designer output into working React code

The agent follows the established Bloomberg Terminal aesthetic and ensures pixel-perfect consistency with existing components.

### strategy-researcher

Use this agent when:
- Exploring new trading strategy concepts before implementation
- Researching academic papers or market methodologies
- Designing entry/exit rules with clear edge definitions
- Evaluating strategy viability for day trading

The agent provides structured strategy proposals with hypothesis, rules, parameters, and testing plans.

### risk-auditor

**Call this agent periodically or before going live.** It audits:
- Position sizing limits and risk per trade
- Stop loss integrity across all code paths
- Market condition handling (gaps, holidays, data issues)
- System failure scenarios (connection loss, state persistence)
- Code safety (infinite loops, division by zero, order quantities)

The agent outputs a risk score and prioritized issue list.

### performance-analyst

Use this agent when:
- Analyzing backtest or live trading results
- Identifying patterns in wins/losses
- Looking for time-of-day or market condition correlations
- Getting data-driven improvement suggestions

The agent provides statistical analysis and actionable recommendations.

## Key Concepts

- Swing points: Local highs/lows used to identify market structure
- Structure breaks: Price breaking previous swing high/low signals trend change
- Higher highs (HH) + Higher lows (HL) = Bullish
- Lower highs (LH) + Lower lows (LL) = Bearish

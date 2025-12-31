# MCP Server Integration - Implementation Plan

## Overview

Create an MCP (Model Context Protocol) server that exposes the trading bot functionality as tools for Claude Code. This enables conversational control of the trading bot through natural language.

**Benefits:**
- Natural language control - no need to remember CLI flags
- Exploratory analysis - ask follow-up questions naturally
- AI reasoning - Claude can suggest optimizations, spot issues
- Unified interface - backtest, optimize, and live trading in one conversation

## Architecture

```
┌─────────────────┐     MCP Protocol      ┌──────────────────────────┐
│   Claude Code   │ ◄──────────────────► │   TradingBot MCP Server  │
│                 │                       │                          │
│  Natural        │     stdio transport   │  ┌────────────────────┐  │
│  language       │  ◄─────────────────►  │  │ Tools:             │  │
│  requests       │                       │  │  - get_signals     │  │
│                 │     Tool calls &      │  │  - run_backtest    │  │
│                 │     responses         │  │  - optimize        │  │
│                 │                       │  │  - get_positions   │  │
└─────────────────┘                       │  │  - explain_trade   │  │
                                          │  └────────────────────┘  │
                                          │           │              │
                                          │           ▼              │
                                          │  ┌────────────────────┐  │
                                          │  │ Existing Bot Code  │  │
                                          │  │  - MarketStructure │  │
                                          │  │  - DataFeed        │  │
                                          │  │  - Optimizer       │  │
                                          │  └────────────────────┘  │
                                          └──────────────────────────┘
```

## Prerequisites

```bash
# Install MCP SDK
uv add mcp

# Verify installation
uv run python -c "import mcp; print(mcp.__version__)"
```

## Tools to Expose

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_signals` | Current trading signals for a symbol | symbol, preset?, interval? |
| `run_backtest` | Backtest a strategy with stats | symbol, preset?, period?, interval? |
| `optimize` | Run Optuna optimization | symbol, trials?, objective? |
| `list_presets` | List available presets | none |
| `get_preset` | Get preset configuration | name |
| `get_positions` | Current open positions (live) | none |
| `get_stats` | Performance statistics | symbol? |
| `explain_signal` | Explain why a signal fired | symbol, signal_type |
| `cache_stats` | Show cache statistics | none |

## Example Conversations

### Signal Analysis
```
User: "What signals do we have for AAPL right now?"
Claude: [calls get_signals(symbol="AAPL")]
        "AAPL has a bullish swing break signal:
         - Entry: $198.75 (break above $198.50 swing high)
         - Stop: $196.20 (below recent swing low)
         - Target: $203.85 (2:1 R:R)
         - ADX: 32 (trending market)"
```

### Backtesting
```
User: "Backtest swing_balanced on MSFT for the last year"
Claude: [calls run_backtest(symbol="MSFT", preset="swing_balanced", period="1y")]
        "MSFT swing_balanced backtest (1y):
         - 45 trades, 58% win rate
         - Return: +12.4%
         - Max Drawdown: 4.2%
         - Calmar Ratio: 2.95
         - Profit Factor: 1.85"

User: "What about with a tighter stop?"
Claude: [calls run_backtest(symbol="MSFT", preset="swing_conservative", period="1y")]
        "With swing_conservative (0.5% risk vs 1%):
         - 45 trades, 62% win rate
         - Return: +8.1% (lower due to smaller position size)
         - Max Drawdown: 2.1%
         - Calmar Ratio: 3.86 (better risk-adjusted)"
```

### Optimization
```
User: "Find optimal parameters for NVDA"
Claude: [calls optimize(symbol="NVDA", trials=100)]
        "Optuna optimization complete (100 trials):
         Best parameters:
         - Interval: 1h, Period: 1y
         - Swing lookback: 5
         - Risk: 1.2%, R:R: 2.0

         Expected performance:
         - Return: +18.5%, Max DD: 5.2%
         - Calmar: 3.56"

User: "Save that as a preset called nvda_optimized"
Claude: [calls save_preset(name="nvda_optimized", ...)]
        "Saved preset 'nvda_optimized' to tradingbot.toml"
```

## Files to Create

### 1. `src/tradingbot/mcp_server.py`

Main MCP server implementation:

```python
"""MCP server for trading bot - conversational control via Claude Code."""

import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from tradingbot import backtest, optimize, tune
from tradingbot._components.bot import MarketStructureBot
from tradingbot._components.feeds import DataFeed
from tradingbot._components.presets import (
    PRESETS,
    get_preset,
    list_presets as _list_presets,
    save_preset,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tradingbot-mcp")

server = Server("tradingbot")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available trading bot tools."""
    return [
        Tool(
            name="get_signals",
            description="Get current trading signals for a symbol. Returns entry, stop, target prices if a signal is active.",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Stock symbol (e.g., AAPL, MSFT)",
                    },
                    "preset": {
                        "type": "string",
                        "description": "Preset name (default: swing_balanced)",
                        "default": "swing_balanced",
                    },
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="run_backtest",
            description="Run a backtest for a symbol with a strategy preset. Returns performance statistics.",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Stock symbol (e.g., AAPL, MSFT)",
                    },
                    "preset": {
                        "type": "string",
                        "description": "Preset name (default: swing_balanced)",
                        "default": "swing_balanced",
                    },
                    "period": {
                        "type": "string",
                        "description": "History period (e.g., 1y, 6mo, 3mo)",
                        "default": "1y",
                    },
                    "interval": {
                        "type": "string",
                        "description": "Bar interval (e.g., 1h, 15m, 1d)",
                        "default": "1h",
                    },
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="optimize",
            description="Run Optuna optimization to find best parameters for a symbol.",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Stock symbol to optimize",
                    },
                    "trials": {
                        "type": "integer",
                        "description": "Number of optimization trials (default: 50)",
                        "default": 50,
                    },
                    "objective": {
                        "type": "string",
                        "enum": ["return", "calmar", "profit_factor"],
                        "description": "Optimization objective (default: calmar)",
                        "default": "calmar",
                    },
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="list_presets",
            description="List all available strategy presets with descriptions.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_preset",
            description="Get detailed configuration for a specific preset.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Preset name",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="save_preset",
            description="Save optimization results as a custom preset.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Preset name to save",
                    },
                    "symbol": {
                        "type": "string",
                        "description": "Symbol that was optimized",
                    },
                    "interval": {"type": "string"},
                    "period": {"type": "string"},
                    "swing_lb": {"type": "integer"},
                    "risk_pct": {"type": "number"},
                    "rr_ratio": {"type": "number"},
                    "total_return": {"type": "number"},
                    "max_drawdown": {"type": "number"},
                },
                "required": ["name", "symbol", "interval", "period", "swing_lb", "risk_pct", "rr_ratio"],
            },
        ),
        Tool(
            name="cache_stats",
            description="Show cache statistics (size, entries, age).",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    try:
        result = await _execute_tool(name, arguments)
        return [TextContent(type="text", text=result)]
    except Exception as e:
        logger.exception(f"Tool {name} failed")
        return [TextContent(type="text", text=f"Error: {e}")]


async def _execute_tool(name: str, args: dict[str, Any]) -> str:
    """Execute a tool and return formatted result."""

    if name == "get_signals":
        return await _get_signals(args["symbol"], args.get("preset", "swing_balanced"))

    elif name == "run_backtest":
        return await _run_backtest(
            args["symbol"],
            args.get("preset", "swing_balanced"),
            args.get("period", "1y"),
            args.get("interval", "1h"),
        )

    elif name == "optimize":
        return await _optimize(
            args["symbol"],
            args.get("trials", 50),
            args.get("objective", "calmar"),
        )

    elif name == "list_presets":
        return _format_presets()

    elif name == "get_preset":
        return _format_preset(args["name"])

    elif name == "save_preset":
        save_preset(
            args["name"],
            symbol=args["symbol"],
            interval=args["interval"],
            period=args["period"],
            swing_lb=args["swing_lb"],
            risk_pct=args["risk_pct"],
            rr_ratio=args["rr_ratio"],
            total_return=args.get("total_return"),
            max_drawdown=args.get("max_drawdown"),
        )
        return f"Saved preset '{args['name']}' to tradingbot.toml"

    elif name == "cache_stats":
        return await _cache_stats()

    else:
        return f"Unknown tool: {name}"


async def _get_signals(symbol: str, preset_name: str) -> str:
    """Get current trading signals for a symbol."""
    preset = get_preset(preset_name)

    # Fetch recent data
    df = DataFeed.history(symbol, period="5d", interval=preset.interval)
    if df.is_empty():
        return f"No data available for {symbol}"

    # Run analysis
    bot = MarketStructureBot(
        capital=100000,
        risk_pct=preset.risk_pct,
        rr_ratio=preset.rr_ratio,
    )

    # Get current bar analysis
    bot.backtest(df, symbol)

    # Check for recent signals
    if not bot.trades:
        return f"No active signals for {symbol} with {preset_name} preset.\nLast analyzed: {df['timestamp'].max()}"

    # Return latest signal info
    last_trade = bot.trades[-1]
    return f"""Signal for {symbol}:
Direction: {last_trade.direction}
Entry: ${last_trade.entry:.2f}
Stop: ${last_trade.stop:.2f}
Target: ${last_trade.tp:.2f}
Status: {last_trade.status}
Preset: {preset_name}"""


async def _run_backtest(symbol: str, preset_name: str, period: str, interval: str) -> str:
    """Run backtest and return statistics."""
    preset = get_preset(preset_name)

    # Override period/interval if specified
    actual_period = period or preset.period
    actual_interval = interval or preset.interval

    # Run backtest
    result = backtest(
        symbol,
        period=actual_period,
        interval=actual_interval,
        preset=preset_name,
    )

    stats = result.get_stats()

    if "error" in stats:
        return f"Backtest failed: {stats['error']}"

    return f"""Backtest Results for {symbol}
Preset: {preset_name}
Period: {actual_period}, Interval: {actual_interval}

Performance:
- Total Trades: {stats['total_trades']}
- Win Rate: {stats['win_rate']}
- Total Return: {stats['total_return']}
- Max Drawdown: {stats['max_drawdown']}
- Profit Factor: {stats['profit_factor']}
- Avg Win: {stats.get('avg_win', 'N/A')}
- Avg Loss: {stats.get('avg_loss', 'N/A')}"""


async def _optimize(symbol: str, trials: int, objective: str) -> str:
    """Run Optuna optimization."""
    # Run in thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    tuner = await loop.run_in_executor(
        None,
        lambda: tune(
            symbol=symbol,
            n_trials=trials,
            objective=objective,
        ),
    )

    if not tuner.study or not tuner.study.best_trial:
        return "Optimization failed - no valid trials"

    best = tuner.study.best_trial

    return f"""Optimization Results for {symbol}
Trials: {len(tuner.study.trials)}
Objective: {objective}

Best Parameters:
- Interval: {best.params['interval']}
- Period: {best.params['period']}
- Swing Lookback: {best.params['swing_lb']}
- Risk: {best.params['risk_pct'] * 100:.2f}%
- R:R Ratio: {best.params['rr_ratio']:.1f}

Expected Performance:
- Total Return: {best.user_attrs.get('total_return', 'N/A')}%
- Max Drawdown: {best.user_attrs.get('max_drawdown', 'N/A')}%
- Win Rate: {best.user_attrs.get('win_rate', 'N/A')}%
- Profit Factor: {best.user_attrs.get('profit_factor', 'N/A')}"""


def _format_presets() -> str:
    """Format all presets for display."""
    lines = ["Available Presets:\n"]

    # Group by trading style
    day_presets = []
    swing_presets = []

    for name, preset in PRESETS.items():
        if preset.eod_exit:
            day_presets.append((name, preset))
        else:
            swing_presets.append((name, preset))

    lines.append("Day Trading (intraday):")
    for name, preset in day_presets:
        lines.append(f"  - {name}: {preset.description}")

    lines.append("\nSwing Trading (multi-day):")
    for name, preset in swing_presets:
        lines.append(f"  - {name}: {preset.description}")

    return "\n".join(lines)


def _format_preset(name: str) -> str:
    """Format a single preset for display."""
    try:
        preset = get_preset(name)
    except KeyError as e:
        return str(e)

    return f"""Preset: {preset.name}
Description: {preset.description}

Timeframe:
- Interval: {preset.interval}
- Period: {preset.period}

Strategy:
- Entry: {preset.entry}
- Exit: {preset.exit}

Risk Management:
- Risk per trade: {preset.risk_pct * 100:.1f}%
- Reward/Risk ratio: {preset.rr_ratio}

Filters:
- Indicators: {', '.join(preset.indicators) or 'None'}
- Filter mode: {preset.filter_mode}

Execution:
- EOD Exit: {preset.eod_exit}
- Time Exit: {preset.time_exit_minutes} minutes"""


async def _cache_stats() -> str:
    """Get cache statistics."""
    from tradingbot._components.cache import BarCache

    cache = BarCache()
    stats = cache.get_stats()

    return f"""Cache Statistics:
- Total entries: {stats.get('total_entries', 0)}
- Total size: {stats.get('total_size_mb', 0):.1f} MB
- Oldest entry: {stats.get('oldest_entry', 'N/A')}
- Newest entry: {stats.get('newest_entry', 'N/A')}"""


async def main() -> None:
    """Run the MCP server."""
    logger.info("Starting TradingBot MCP server")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
```

### 2. `src/tradingbot/mcp_server_config.json`

MCP server configuration for Claude Code:

```json
{
  "mcpServers": {
    "tradingbot": {
      "command": "uv",
      "args": ["run", "python", "-m", "tradingbot.mcp_server"],
      "cwd": "/path/to/tradingbot"
    }
  }
}
```

## Files to Modify

### 1. `pyproject.toml`

Add MCP dependency:

```toml
dependencies = [
    # ... existing ...
    "mcp>=1.0.0",
]

[project.scripts]
# ... existing ...
tradingbot-mcp = "tradingbot.mcp_server:main"
```

### 2. `src/tradingbot/__init__.py`

Expose MCP server in package (optional):

```python
# ... existing exports ...
from .mcp_server import server as mcp_server
```

## Installation & Configuration

### 1. Install the package

```bash
cd /path/to/tradingbot
uv add mcp
uv sync
```

### 2. Configure Claude Code

Add to `~/.claude/claude_desktop_config.json` or project's `.claude/settings.json`:

```json
{
  "mcpServers": {
    "tradingbot": {
      "command": "uv",
      "args": ["run", "python", "-m", "tradingbot.mcp_server"],
      "cwd": "/Volumes/work/perso/tradingbot"
    }
  }
}
```

### 3. Restart Claude Code

After configuration, restart Claude Code to load the MCP server.

## Testing

### Manual Testing

```bash
# Test server starts
uv run python -m tradingbot.mcp_server

# In another terminal, test with MCP inspector
npx @modelcontextprotocol/inspector uv run python -m tradingbot.mcp_server
```

### Unit Tests

```python
# tests/test_mcp_server.py

import pytest
from tradingbot.mcp_server import _format_presets, _format_preset, _execute_tool


def test_format_presets():
    """Test preset listing."""
    result = _format_presets()
    assert "Day Trading" in result
    assert "Swing Trading" in result
    assert "swing_balanced" in result


def test_format_preset_valid():
    """Test single preset formatting."""
    result = _format_preset("swing_balanced")
    assert "swing_balanced" in result
    assert "Interval: 1h" in result


def test_format_preset_invalid():
    """Test invalid preset handling."""
    result = _format_preset("nonexistent")
    assert "Unknown preset" in result


@pytest.mark.asyncio
async def test_run_backtest():
    """Test backtest tool."""
    result = await _execute_tool("run_backtest", {
        "symbol": "SPY",
        "preset": "swing_balanced",
        "period": "3mo",
    })
    assert "Backtest Results" in result or "error" in result.lower()


@pytest.mark.asyncio
async def test_list_presets():
    """Test list presets tool."""
    result = await _execute_tool("list_presets", {})
    assert "Available Presets" in result
```

## Security Considerations

1. **Read-only by default**: Most tools only read data, no trading execution
2. **Paper trading only**: If adding live trading tools, default to paper account
3. **No API keys in MCP**: Use environment variables or config files
4. **Audit logging**: Log all tool calls for review

## Error Handling

1. **Data not available**: Return helpful message with suggestions
2. **Invalid symbol**: Validate symbol format before fetching
3. **Optimization timeout**: Set reasonable timeout, return partial results
4. **Cache miss**: Fetch data and cache, don't fail

## Future Enhancements

### Phase 2: Live Trading Tools

```python
Tool(
    name="start_paper_trading",
    description="Start paper trading for a symbol",
    ...
),
Tool(
    name="stop_trading",
    description="Stop trading and close positions",
    ...
),
Tool(
    name="get_positions",
    description="Get current open positions",
    ...
),
```

### Phase 3: Analysis Tools

```python
Tool(
    name="compare_symbols",
    description="Compare backtest results across multiple symbols",
    ...
),
Tool(
    name="correlation_analysis",
    description="Analyze correlation between symbols",
    ...
),
Tool(
    name="market_regime",
    description="Detect current market regime (trending/ranging)",
    ...
),
```

### Phase 4: AI Integration

Combine with the AI explanations feature:

```python
Tool(
    name="explain_signal",
    description="Get AI-powered explanation for a trading signal",
    ...
),
Tool(
    name="analyze_trade",
    description="AI analysis of why a trade won or lost",
    ...
),
```

## Taskfile Integration

Add to `Taskfile.yml`:

```yaml
mcp:
  desc: Start MCP server
  cmds:
    - uv run python -m tradingbot.mcp_server

mcp:test:
  desc: Test MCP server with inspector
  cmds:
    - npx @modelcontextprotocol/inspector uv run python -m tradingbot.mcp_server
```

## Summary

This implementation provides:
- ✅ Conversational control of backtest/optimize/signals
- ✅ Natural language interface via Claude Code
- ✅ All existing functionality exposed as tools
- ✅ Clean integration with existing codebase
- ✅ Extensible for future live trading features

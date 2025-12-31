"""CLI entry point for backtest."""

import argparse

from tradingbot import run_multi_backtest, run_single_backtest
from tradingbot.types import PartialExitLevel

# Default partial exit levels when --partial-exits is enabled
DEFAULT_PARTIAL_EXITS = (PartialExitLevel(r_multiple=1.0, exit_pct=0.5),)  # 50% at 1R


def main() -> None:
    """CLI entry point for backtest."""
    from tradingbot._components.logging import configure_logging
    from tradingbot.config import get_logging_config

    # Initialize logging from config
    log_cfg = get_logging_config()
    configure_logging(level=log_cfg.level, log_file=log_cfg.log_file)

    parser = argparse.ArgumentParser(
        description="Run trading bot backtest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  tradingbot AAPL
  tradingbot AAPL TSLA GOOGL
  tradingbot AAPL --period 2y --interval 1d
  tradingbot AAPL --capital 50000 --risk 0.02
  tradingbot AAPL --preset scalping
  tradingbot AAPL --strategy vwap
  tradingbot AAPL -s orb --verbose
  tradingbot AAPL --speed 10
  tradingbot AAPL --atr-sizing         # Volatility-adjusted position sizing
  tradingbot AAPL --atr-trail          # ATR-based trailing stop (2x ATR)
  tradingbot AAPL --atr-trail --atr-trail-mult 3  # ATR trail with 3x multiplier
  tradingbot AAPL --atr-trail --atr-trail-start 1  # Start trailing after 1R profit
  tradingbot AAPL --partial-exits      # Exit 50%% at 1R, move stop to breakeven
        """,
    )

    parser.add_argument("symbols", nargs="*", help="Stock symbol(s) to backtest (e.g., MSFT, AAPL)")
    parser.add_argument("--list-strategies", action="store_true", help="List available entry strategies")
    parser.add_argument("--list-presets", action="store_true", help="List available trading presets")
    parser.add_argument("--preset", "-p", help="Use a preset (overrides strategy, risk, indicators, interval, period)")
    parser.add_argument("--period", help="Data period (default: from config or 1y)")
    parser.add_argument("--interval", help="Data interval (default: from config or 1h)")
    parser.add_argument("--capital", type=float, help="Starting capital (uses config default)")
    parser.add_argument("--risk", type=float, help="Risk per trade as decimal (e.g., 0.01 for 1%%)")
    parser.add_argument("--rr", type=float, help="Reward/risk ratio (e.g., 2.0)")
    parser.add_argument("--swing-lb", type=int, help="Swing lookback period")
    parser.add_argument(
        "--strategy", "-s", help="Entry strategy: swing_break, vwap_reversion, orb, rsi_divergence, atr_breakout"
    )
    parser.add_argument("--refresh", action="store_true", help="Force re-fetch data from API")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print each bar as it processes")
    parser.add_argument("--speed", type=float, default=0, help="Simulate real-time: bars per second (0 = instant)")

    # Execution cost options
    parser.add_argument(
        "--no-costs",
        action="store_true",
        help="Disable execution costs (slippage, spread, commission) for comparison",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        metavar="BPS",
        help="Slippage in basis points (default: 5)",
    )
    parser.add_argument(
        "--spread",
        type=float,
        metavar="BPS",
        help="Bid-ask spread in basis points (default: 2)",
    )
    parser.add_argument(
        "--commission",
        type=float,
        metavar="USD",
        help="Commission per share in USD (default: 0.005)",
    )

    # Position sizing options
    parser.add_argument(
        "--atr-sizing",
        action="store_true",
        help="Enable ATR-based volatility-adjusted position sizing (reduces size in high volatility)",
    )

    # Trailing stop options
    parser.add_argument(
        "--atr-trail",
        action="store_true",
        help="Enable ATR-based trailing stop (trails at high_water - N×ATR, default 2×)",
    )
    parser.add_argument(
        "--atr-trail-mult",
        type=float,
        metavar="N",
        help="ATR trail multiplier (default: 2.0, requires --atr-trail)",
    )
    parser.add_argument(
        "--atr-trail-start",
        type=float,
        metavar="R",
        help="Start ATR trailing after this R-multiple profit (default: 0 = immediate)",
    )

    # Partial exit options
    parser.add_argument(
        "--partial-exits",
        action="store_true",
        help="Enable partial profit taking: exit 50%% at 1R, move stop to breakeven",
    )

    args = parser.parse_args()

    if args.list_presets:
        from tradingbot._components.presets import PRESETS, _load_custom_presets

        custom = _load_custom_presets()

        print("Built-in presets:\n")
        for name, preset in PRESETS.items():
            print(f"  {name}")
            print(f"    {preset.description}")
            print(f"    Interval: {preset.interval}, Period: {preset.period}")
            print(f"    Entry: {preset.entry}, Exit: {preset.exit}")
            print(f"    Risk: {preset.risk_pct * 100:.1f}%, RR: {preset.rr_ratio}:1")
            if preset.indicators:
                print(f"    Indicators: {', '.join(preset.indicators)} ({preset.filter_mode})")
            print()

        if custom:
            print("Custom presets (from tradingbot.toml):\n")
            for name, preset in custom.items():
                print(f"  {name}")
                print(f"    {preset.description}")
                print(f"    Interval: {preset.interval}, Period: {preset.period}")
                print(f"    Entry: {preset.entry}, Exit: {preset.exit}")
                print(f"    Risk: {preset.risk_pct * 100:.1f}%, RR: {preset.rr_ratio}:1")
                if preset.indicators:
                    print(f"    Indicators: {', '.join(preset.indicators)} ({preset.filter_mode})")
                print()
        return

    if args.list_strategies:
        from tradingbot._components.strategies import get_entry_registry, get_exit_registry

        entry_registry = get_entry_registry()
        exit_registry = get_exit_registry()

        print("Entry strategies (generate BUY/SELL signals):")
        for name in entry_registry.list():
            print(f"  - {name}")

        print("\nExit strategies (calculate SL/TP):")
        for name in exit_registry.list():
            print(f"  - {name}")
        return

    if not args.symbols:
        parser.error("symbols are required (or use --list-strategies, --list-presets)")

    # Resolve interval/period: CLI > preset > config > hardcoded defaults
    from tradingbot._components.presets import get_preset, get_strategy_defaults

    defaults = get_strategy_defaults()
    interval = defaults["interval"]
    period = defaults["period"]

    # Preset overrides config defaults
    if args.preset:
        preset = get_preset(args.preset)
        interval = preset.interval
        period = preset.period

    # CLI args override everything
    if args.interval:
        interval = args.interval
    if args.period:
        period = args.period

    # Resolve partial exit levels
    partial_levels = DEFAULT_PARTIAL_EXITS if args.partial_exits else None

    try:
        if len(args.symbols) == 1:
            run_single_backtest(
                args.symbols[0],
                period=period,
                interval=interval,
                capital=args.capital,
                risk=args.risk,
                rr=args.rr,
                swing_lb=args.swing_lb,
                strategy=args.strategy,
                preset=args.preset,
                refresh=args.refresh,
                verbose=args.verbose,
                speed=args.speed,
                no_costs=args.no_costs,
                slippage_bps=args.slippage,
                spread_bps=args.spread,
                commission=args.commission,
                use_atr_sizing=args.atr_sizing,
                atr_trail=args.atr_trail,
                atr_trail_multiplier=args.atr_trail_mult,
                atr_trail_activation_r=args.atr_trail_start,
                partial_exit_levels=partial_levels,
            )
        else:
            run_multi_backtest(
                args.symbols,
                period=period,
                interval=interval,
                capital=args.capital,
                risk=args.risk,
                rr=args.rr,
                swing_lb=args.swing_lb,
                strategy=args.strategy,
                preset=args.preset,
                refresh=args.refresh,
                verbose=args.verbose,
                speed=args.speed,
                no_costs=args.no_costs,
                slippage_bps=args.slippage,
                spread_bps=args.spread,
                commission=args.commission,
                use_atr_sizing=args.atr_sizing,
                atr_trail=args.atr_trail,
                atr_trail_multiplier=args.atr_trail_mult,
                atr_trail_activation_r=args.atr_trail_start,
                partial_exit_levels=partial_levels,
            )
    except ValueError as e:
        import sys

        print(f"\n  Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyError as e:
        import sys

        print(f"\n  Error: {e}", file=sys.stderr)
        sys.exit(1)

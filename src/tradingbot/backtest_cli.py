"""CLI entry point for backtest."""

import argparse

from tradingbot import run_multi_backtest, run_single_backtest


def main() -> None:
    """CLI entry point for backtest."""
    parser = argparse.ArgumentParser(
        description="Run trading bot backtest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  tradingbot AAPL
  tradingbot AAPL TSLA GOOGL
  tradingbot AAPL --period 5y --interval 1d
  tradingbot AAPL --capital 50000 --risk 0.02
  tradingbot AAPL --preset scalping
  tradingbot AAPL --strategy vwap
  tradingbot AAPL -s orb --verbose
  tradingbot AAPL --speed 10
        """,
    )

    parser.add_argument("symbols", nargs="*", help="Stock symbol(s) to backtest (e.g., MSFT, AAPL)")
    parser.add_argument("--list-strategies", action="store_true", help="List available entry strategies")
    parser.add_argument("--list-presets", action="store_true", help="List available trading presets")
    parser.add_argument("--preset", "-p", help="Use a preset (overrides strategy, risk, indicators)")
    parser.add_argument("--period", default="2y", help="Data period (default: 2y)")
    parser.add_argument("--interval", default="1d", help="Data interval (default: 1d)")
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

    args = parser.parse_args()

    if args.list_presets:
        from tradingbot._components.presets import PRESETS, _load_custom_presets

        custom = _load_custom_presets()

        print("Built-in presets:\n")
        for name, preset in PRESETS.items():
            print(f"  {name}")
            print(f"    {preset.description}")
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

    try:
        if len(args.symbols) == 1:
            run_single_backtest(
                args.symbols[0],
                period=args.period,
                interval=args.interval,
                capital=args.capital,
                risk=args.risk,
                rr=args.rr,
                swing_lb=args.swing_lb,
                strategy=args.strategy,
                preset=args.preset,
                refresh=args.refresh,
                verbose=args.verbose,
                speed=args.speed,
            )
        else:
            run_multi_backtest(
                args.symbols,
                period=args.period,
                interval=args.interval,
                capital=args.capital,
                risk=args.risk,
                rr=args.rr,
                swing_lb=args.swing_lb,
                strategy=args.strategy,
                preset=args.preset,
                refresh=args.refresh,
                verbose=args.verbose,
                speed=args.speed,
            )
    except ValueError as e:
        import sys

        print(f"\n  Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyError as e:
        import sys

        print(f"\n  Error: {e}", file=sys.stderr)
        sys.exit(1)

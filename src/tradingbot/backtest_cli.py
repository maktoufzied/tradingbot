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
  tradingbot SPY
  tradingbot AAPL TSLA GOOGL
  tradingbot SPY --period 5y --interval 1d
  tradingbot AAPL --capital 50000 --risk 0.02
  tradingbot SPY --verbose
  tradingbot SPY --speed 10
        """,
    )

    parser.add_argument("symbols", nargs="+", help="Stock symbol(s) to backtest (e.g., SPY, AAPL)")
    parser.add_argument("--period", default="2y", help="Data period (default: 2y)")
    parser.add_argument("--interval", default="1d", help="Data interval (default: 1d)")
    parser.add_argument("--capital", type=float, help="Starting capital (uses config default)")
    parser.add_argument("--risk", type=float, help="Risk per trade as decimal (e.g., 0.01 for 1%%)")
    parser.add_argument("--rr", type=float, help="Reward/risk ratio (e.g., 2.0)")
    parser.add_argument("--swing-lb", type=int, help="Swing lookback period")
    parser.add_argument("--refresh", action="store_true", help="Force re-fetch data from API")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print each bar as it processes")
    parser.add_argument("--speed", type=float, default=0, help="Simulate real-time: bars per second (0 = instant)")

    args = parser.parse_args()

    if len(args.symbols) == 1:
        run_single_backtest(
            args.symbols[0],
            period=args.period,
            interval=args.interval,
            capital=args.capital,
            risk=args.risk,
            rr=args.rr,
            swing_lb=args.swing_lb,
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
            refresh=args.refresh,
            verbose=args.verbose,
            speed=args.speed,
        )

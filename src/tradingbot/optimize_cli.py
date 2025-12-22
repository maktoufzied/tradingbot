"""CLI entry point for optimizer."""

import argparse

from tradingbot import ParameterRanges, optimize


def main() -> None:
    """CLI entry point for optimizer."""
    parser = argparse.ArgumentParser(
        description="Optimize trading bot parameters",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  tradingbot-optimize SPY
  tradingbot-optimize AAPL --period 5y
  tradingbot-optimize TSLA --heatmap --overfit
  tradingbot-optimize SPY --swing 5,6,7,8 --rr 2.0,2.5,3.0
        """,
    )

    parser.add_argument("symbol", help="Stock symbol to optimize (e.g., SPY, AAPL)")
    parser.add_argument("--period", default="2y", help="Data period (default: 2y)")
    parser.add_argument("--interval", default="1d", help="Data interval (default: 1d)")
    parser.add_argument("--capital", type=float, default=100000, help="Starting capital (default: 100000)")
    parser.add_argument("--heatmap", action="store_true", help="Show parameter heatmaps")
    parser.add_argument("--overfit", action="store_true", help="Run overfitting analysis")
    parser.add_argument("--plot", action="store_true", help="Show parameter impact plots")

    # Custom parameter ranges
    parser.add_argument(
        "--swing",
        help="Swing lookback values (comma-separated, e.g., 3,4,5,6,7)",
    )
    parser.add_argument(
        "--risk",
        help="Risk percentages (comma-separated, e.g., 0.01,0.015,0.02)",
    )
    parser.add_argument(
        "--rr",
        help="Reward/risk ratios (comma-separated, e.g., 1.5,2.0,2.5,3.0)",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Run backtests sequentially (disable parallel execution)",
    )

    args = parser.parse_args()

    # Build custom parameter ranges if provided
    params: ParameterRanges | None = None
    if args.swing or args.risk or args.rr:
        default = ParameterRanges.default()
        params = ParameterRanges(
            swing_lookback=[int(x) for x in args.swing.split(",")] if args.swing else default.swing_lookback,
            risk_pct=[float(x) for x in args.risk.split(",")] if args.risk else default.risk_pct,
            rr_ratio=[float(x) for x in args.rr.split(",")] if args.rr else default.rr_ratio,
        )

    opt = optimize(
        symbol=args.symbol,
        period=args.period,
        interval=args.interval,
        capital=args.capital,
        params=params,
        parallel=not args.sequential,
    )

    if args.heatmap:
        opt.plot_heatmap()

    if args.overfit:
        opt.check_overfitting()

    if args.plot:
        opt.plot_parameter_impact()

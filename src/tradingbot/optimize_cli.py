"""CLI entry point for grid search optimization."""

import argparse

from tradingbot import ParameterRanges, optimize, walk_forward
from tradingbot._components.feeds import DataFeed
from tradingbot._components.presets import save_preset


def main() -> None:
    """CLI entry point for grid search optimizer."""
    parser = argparse.ArgumentParser(
        description="Optimize trading bot parameters using grid search (exhaustive)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic grid search
  tradingbot-optimize AAPL
  tradingbot-optimize AAPL --period 6mo,1y --interval 15m,1h

  # Custom parameter ranges
  tradingbot-optimize AAPL --swing 3,4,5,6,7 --risk 0.01,0.02 --rr 1.5,2.0,2.5

  # Analysis options
  tradingbot-optimize TSLA --heatmap --overfit --plot

  # Save best parameters as preset
  tradingbot-optimize AAPL --save-preset aapl_optimized

  # Walk-forward validation (prevents overfitting)
  tradingbot-optimize AAPL --walk-forward
  tradingbot-optimize AAPL --walk-forward --folds 7 --train-ratio 0.8

For faster smart sampling optimization, use: tradingbot-optuna
        """,
    )

    parser.add_argument("symbol", help="Stock symbol to optimize (e.g., MSFT, AAPL)")
    parser.add_argument("--period", help="Data period(s), comma-separated (e.g., 6mo,1y,2y)")
    parser.add_argument("--interval", help="Data interval(s), comma-separated (e.g., 15m,1h,1d)")
    parser.add_argument("--capital", type=float, default=100000, help="Starting capital (default: 100000)")
    parser.add_argument(
        "--save-preset", metavar="NAME", help="Save best parameters as custom preset to tradingbot.toml"
    )

    # Grid search options
    parser.add_argument("--heatmap", action="store_true", help="Show parameter heatmaps")
    parser.add_argument("--overfit", action="store_true", help="Run overfitting analysis")
    parser.add_argument("--plot", action="store_true", help="Show parameter impact plots")
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
        help="Run backtests sequentially (default: parallel)",
    )

    # Walk-forward options
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help="Run walk-forward validation to detect overfitting",
    )
    parser.add_argument(
        "--folds",
        type=int,
        default=5,
        help="Number of walk-forward folds (default: 5)",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.7,
        help="Training data ratio per fold (default: 0.7)",
    )

    args = parser.parse_args()

    # Resolve interval/period: CLI > config > defaults
    from tradingbot._components.presets import get_strategy_defaults

    defaults = get_strategy_defaults()

    # Parse comma-separated values or use defaults
    intervals = [x.strip() for x in args.interval.split(",")] if args.interval else [defaults["interval"]]
    periods = [x.strip() for x in args.period.split(",")] if args.period else [defaults["period"]]

    # Walk-forward validation
    if args.walk_forward:
        interval = intervals[0]
        period = periods[0]

        df = DataFeed.history(args.symbol, period=period, interval=interval)

        walk_forward(
            symbol=args.symbol,
            df=df,
            interval=interval,
            period=period,
            n_folds=args.folds,
            train_ratio=args.train_ratio,
            capital=args.capital,
        )
        return

    # Grid search optimization
    default = ParameterRanges.default()
    params = ParameterRanges(
        interval=intervals,
        period=periods,
        swing_lookback=[int(x) for x in args.swing.split(",")] if args.swing else default.swing_lookback,
        risk_pct=[float(x) for x in args.risk.split(",")] if args.risk else default.risk_pct,
        rr_ratio=[float(x) for x in args.rr.split(",")] if args.rr else default.rr_ratio,
    )

    opt = optimize(
        symbol=args.symbol,
        period=periods,
        interval=intervals,
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

    # Save preset if requested
    best_result = opt.best_by_return()
    if args.save_preset and best_result:
        save_preset(
            args.save_preset,
            symbol=args.symbol,
            interval=best_result["interval"],
            period=best_result["period"],
            swing_lb=best_result["swing_lookback"],
            risk_pct=best_result["risk_pct"],
            rr_ratio=best_result["rr_ratio"],
            total_return=best_result["total_return"],
            max_drawdown=best_result["max_drawdown"],
        )
        print(f"\n✓ Saved preset '{args.save_preset}' to tradingbot.toml")

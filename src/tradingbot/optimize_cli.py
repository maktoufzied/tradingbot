"""CLI entry point for optimizer."""

import argparse

from tradingbot import ParameterRanges, optimize, tune
from tradingbot._components.presets import save_preset


def main() -> None:
    """CLI entry point for optimizer."""
    parser = argparse.ArgumentParser(
        description="Optimize trading bot parameters",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Grid search (exhaustive)
  tradingbot-optimize AAPL
  tradingbot-optimize AAPL --period 6mo,1y --interval 15m,1h
  tradingbot-optimize TSLA --heatmap --overfit

  # Optuna (smart sampling - faster)
  tradingbot-optimize AAPL --optuna
  tradingbot-optimize AAPL --optuna --trials 200
  tradingbot-optimize AAPL --optuna --objective multi  # Pareto optimization
  tradingbot-optimize AAPL --optuna --seed 42         # Reproducible results

  # Save best parameters as preset
  tradingbot-optimize AAPL --optuna --save-preset aapl_optimized
        """,
    )

    parser.add_argument("symbol", help="Stock symbol to optimize (e.g., MSFT, AAPL)")
    parser.add_argument("--period", help="Data period(s), comma-separated (e.g., 6mo,1y,2y)")
    parser.add_argument("--interval", help="Data interval(s), comma-separated (e.g., 15m,1h,1d)")
    parser.add_argument("--capital", type=float, default=100000, help="Starting capital (default: 100000)")
    parser.add_argument(
        "--save-preset", metavar="NAME", help="Save best parameters as custom preset to tradingbot.toml"
    )

    # Optuna options
    parser.add_argument("--optuna", action="store_true", help="Use Optuna instead of grid search")
    parser.add_argument("--trials", type=int, default=100, help="Number of Optuna trials (default: 100)")
    parser.add_argument(
        "--objective",
        choices=["return", "calmar", "profit_factor", "multi"],
        default="calmar",
        help="Optuna objective: return, calmar (default, return/drawdown), profit_factor, or multi (Pareto)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible Optuna results",
    )

    # Grid search options
    parser.add_argument("--heatmap", action="store_true", help="Show parameter heatmaps (grid search only)")
    parser.add_argument("--overfit", action="store_true", help="Run overfitting analysis (grid search only)")
    parser.add_argument("--plot", action="store_true", help="Show parameter impact plots (grid search only)")
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
        help="Run backtests sequentially (grid search only)",
    )

    args = parser.parse_args()

    # Resolve interval/period: CLI > config > defaults
    from tradingbot._components.presets import get_strategy_defaults

    defaults = get_strategy_defaults()

    # Parse comma-separated values or use defaults
    intervals = [x.strip() for x in args.interval.split(",")] if args.interval else [defaults["interval"]]
    periods = [x.strip() for x in args.period.split(",")] if args.period else [defaults["period"]]

    if args.optuna:
        # Use Optuna-based optimization
        tuner = tune(
            symbol=args.symbol,
            intervals=intervals,
            periods=periods,
            n_trials=args.trials,
            objective=args.objective,
            capital=args.capital,
            seed=args.seed,
        )

        # Save preset if requested
        if args.save_preset and tuner.study:
            if args.objective == "multi":
                # For multi-objective, use the highest return solution
                best_trial = max(tuner.study.best_trials, key=lambda t: t.values[0])
            else:
                best_trial = tuner.study.best_trial

            save_preset(
                args.save_preset,
                symbol=args.symbol,
                interval=best_trial.params["interval"],
                period=best_trial.params["period"],
                swing_lb=best_trial.params["swing_lb"],
                risk_pct=best_trial.params["risk_pct"],
                rr_ratio=best_trial.params["rr_ratio"],
                total_return=best_trial.user_attrs.get("total_return"),
                max_drawdown=best_trial.user_attrs.get("max_drawdown"),
            )
            print(f"\n✓ Saved preset '{args.save_preset}' to tradingbot.toml")
    else:
        # Use grid search
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

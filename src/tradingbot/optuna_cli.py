"""CLI entry point for Optuna-based optimization."""

import argparse

from tradingbot import tune, walk_forward
from tradingbot._components.feeds import DataFeed
from tradingbot._components.presets import save_preset


def main() -> None:
    """CLI entry point for Optuna optimization."""
    parser = argparse.ArgumentParser(
        description="Optimize trading bot parameters using Optuna (smart sampling)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic Optuna optimization
  tradingbot-optuna AAPL
  tradingbot-optuna AAPL --trials 200

  # Different strategies (default: from config)
  tradingbot-optuna AAPL -s vwap_reversion      # Use VWAP reversion strategy
  tradingbot-optuna AAPL -s rsi_divergence      # Use RSI divergence strategy

  # Different objectives
  tradingbot-optuna AAPL --objective return     # Maximize total return
  tradingbot-optuna AAPL --objective calmar     # Maximize return/drawdown (default)
  tradingbot-optuna AAPL --objective multi      # Pareto optimization (multi-objective)

  # Reproducible results
  tradingbot-optuna AAPL --seed 42

  # Save best parameters as preset
  tradingbot-optuna AAPL --save-preset aapl_optimized

  # Walk-forward validation (prevents overfitting)
  tradingbot-optuna AAPL --walk-forward
  tradingbot-optuna AAPL --walk-forward --folds 7 --train-ratio 0.8
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
    parser.add_argument("--trials", type=int, default=100, help="Number of Optuna trials (default: 100)")
    parser.add_argument(
        "--objective",
        choices=["return", "calmar", "profit_factor", "multi"],
        default="calmar",
        help="Optimization objective: return, calmar (default), profit_factor, or multi (Pareto)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible results",
    )

    # Strategy options
    parser.add_argument(
        "--strategy",
        "-s",
        help="Entry strategy to use (default: from config)",
    )
    parser.add_argument(
        "--exit-strategy",
        help="Exit strategy to use (default: from config)",
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

    # Run Optuna optimization
    tuner = tune(
        symbol=args.symbol,
        intervals=intervals,
        periods=periods,
        n_trials=args.trials,
        objective=args.objective,
        capital=args.capital,
        seed=args.seed,
        entry_strategy=args.strategy,
        exit_strategy=args.exit_strategy,
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

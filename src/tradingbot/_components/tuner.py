"""Optuna-based hyperparameter tuning for trading strategies."""

import logging
from dataclasses import dataclass
from typing import Literal

import optuna
import polars as pl
from optuna.trial import Trial
from rich.console import Console
from rich.table import Table

from .bot import MarketStructureBot
from .feeds import DataFeed

console = Console()

# Suppress optuna's verbose logging
optuna.logging.set_verbosity(optuna.logging.WARNING)
logging.getLogger("optuna").setLevel(logging.WARNING)


@dataclass
class TunerConfig:
    """Configuration for Optuna tuner."""

    # Intervals and periods to search
    intervals: list[str]
    periods: list[str]

    # Parameter ranges (continuous)
    swing_lb_min: int = 3
    swing_lb_max: int = 10
    risk_pct_min: float = 0.005
    risk_pct_max: float = 0.02
    rr_ratio_min: float = 1.0
    rr_ratio_max: float = 3.0

    # Strategy settings (from config if not specified)
    entry_strategy: str | None = None
    exit_strategy: str | None = None

    # Optimization settings
    n_trials: int = 100
    timeout: int | None = None  # seconds
    objective: Literal["return", "calmar", "profit_factor", "multi"] = "calmar"
    seed: int | None = None  # Random seed for reproducibility

    @classmethod
    def default(cls) -> TunerConfig:
        from .presets import get_strategy_defaults

        defaults = get_strategy_defaults()
        return cls(
            intervals=["1h"],
            periods=["1y"],
            entry_strategy=defaults.get("entry_strategy"),
            exit_strategy=defaults.get("exit_strategy"),
        )


class OptunaTuner:
    """Optuna-based hyperparameter tuner for trading strategies."""

    def __init__(
        self,
        symbol: str,
        capital: float = 100000,
        config: TunerConfig | None = None,
    ):
        self.symbol = symbol
        self.capital = capital
        self.config = config or TunerConfig.default()
        self._data_cache: dict[tuple[str, str], pl.DataFrame] = {}
        self.study: optuna.Study | None = None

    def _get_data(self, interval: str, period: str) -> pl.DataFrame:
        """Get data for interval/period, caching to avoid re-fetching."""
        key = (interval, period)
        if key not in self._data_cache:
            self._data_cache[key] = DataFeed.history(self.symbol, period=period, interval=interval)
        return self._data_cache[key]

    def _prefetch_data(self) -> None:
        """Pre-fetch all data combinations."""
        console.print("[dim]Fetching data for all interval/period combinations...[/dim]")
        for interval in self.config.intervals:
            for period in self.config.periods:
                self._get_data(interval, period)

    def _objective(self, trial: Trial) -> float | tuple[float, float]:
        """Optuna objective function."""
        # Sample parameters
        interval = trial.suggest_categorical("interval", self.config.intervals)
        period = trial.suggest_categorical("period", self.config.periods)
        swing_lb = trial.suggest_int("swing_lb", self.config.swing_lb_min, self.config.swing_lb_max)
        risk_pct = trial.suggest_float("risk_pct", self.config.risk_pct_min, self.config.risk_pct_max, step=0.001)
        rr_ratio = trial.suggest_float("rr_ratio", self.config.rr_ratio_min, self.config.rr_ratio_max, step=0.1)

        # Get data and run backtest
        df = self._get_data(interval, period)

        bot = MarketStructureBot(
            capital=self.capital,
            risk_pct=risk_pct,
            rr_ratio=rr_ratio,
            swing_lb=swing_lb,
            entry_strategy=self.config.entry_strategy,
            exit_strategy=self.config.exit_strategy,
        )
        bot.backtest(df, self.symbol)

        if not bot.trades:
            # No trades - return bad values
            if self.config.objective == "multi":
                return float("-inf"), float("inf")
            return float("-inf")

        stats = bot.get_stats()
        if "error" in stats:
            if self.config.objective == "multi":
                return float("-inf"), float("inf")
            return float("-inf")

        # Parse stats
        total_return = float(str(stats["total_return"]).rstrip("%"))
        max_dd = float(str(stats["max_drawdown"]).rstrip("%"))
        pf_str = str(stats["profit_factor"])
        profit_factor = float(pf_str) if pf_str != "inf" else 10.0

        # Store additional info
        trial.set_user_attr("total_trades", int(stats["total_trades"]))
        trial.set_user_attr("win_rate", float(str(stats["win_rate"]).rstrip("%")))
        trial.set_user_attr("total_return", total_return)
        trial.set_user_attr("max_drawdown", max_dd)
        trial.set_user_attr("profit_factor", profit_factor)

        # Return objective value based on config
        if self.config.objective == "return":
            return total_return
        elif self.config.objective == "calmar":
            # Calmar ratio: return / max drawdown (risk-adjusted)
            return total_return / max(max_dd, 0.1)
        elif self.config.objective == "profit_factor":
            return profit_factor
        elif self.config.objective == "multi":
            # Multi-objective: maximize return, minimize drawdown
            return total_return, max_dd
        else:
            return total_return

    def tune(self) -> optuna.Study:
        """Run Optuna optimization."""
        self._prefetch_data()

        # Create sampler with optional seed for reproducibility
        sampler = optuna.samplers.TPESampler(seed=self.config.seed)

        # Create study based on objective type
        if self.config.objective == "multi":
            self.study = optuna.create_study(
                directions=["maximize", "minimize"],
                study_name=f"{self.symbol}_multi",
                sampler=sampler,
            )
        else:
            self.study = optuna.create_study(
                direction="maximize",
                study_name=f"{self.symbol}_{self.config.objective}",
                sampler=sampler,
            )

        console.print(f"[cyan]Running {self.config.n_trials} trials...[/cyan]")

        self.study.optimize(
            self._objective,
            n_trials=self.config.n_trials,
            timeout=self.config.timeout,
            n_jobs=-1,
            show_progress_bar=True,
        )

        return self.study

    def print_report(self) -> None:
        """Print optimization report."""
        if not self.study:
            console.print("[yellow]No study results to report[/yellow]")
            return

        console.print()
        console.rule("[bold]OPTUNA OPTIMIZATION REPORT[/bold]")

        console.print(f"\nSymbol: [yellow]{self.symbol}[/yellow]")
        console.print(f"Trials: [cyan]{len(self.study.trials)}[/cyan]")
        console.print(f"Objective: [cyan]{self.config.objective}[/cyan]")

        # Data summary
        data_summary = ", ".join(
            f"{interval}/{period}: {len(df)} bars" for (interval, period), df in self._data_cache.items()
        )
        console.print(f"Data: [cyan]{data_summary}[/cyan]")

        if self.config.objective == "multi":
            self._print_pareto_report()
        else:
            self._print_single_objective_report()

    def _print_single_objective_report(self) -> None:
        """Print report for single-objective optimization."""
        if not self.study:
            return

        best = self.study.best_trial

        console.print()
        console.rule("[bold cyan]Best Parameters[/bold cyan]", style="dim")

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Param", style="cyan")
        table.add_column("Value")

        table.add_row("interval", best.params["interval"])
        table.add_row("period", best.params["period"])
        table.add_row("swing_lb", str(best.params["swing_lb"]))
        table.add_row("risk_pct", f"{best.params['risk_pct'] * 100:.2f}%")
        table.add_row("rr_ratio", f"{best.params['rr_ratio']:.1f}")
        table.add_row("", "")
        table.add_row("Total Trades", str(best.user_attrs.get("total_trades", "N/A")))
        table.add_row("Win Rate", f"{best.user_attrs.get('win_rate', 0):.1f}%")

        ret = best.user_attrs.get("total_return", 0)
        ret_style = "green" if ret > 0 else "red"
        table.add_row("Total Return", f"[{ret_style}]{ret:+.2f}%[/{ret_style}]")
        table.add_row("Profit Factor", f"{best.user_attrs.get('profit_factor', 0):.2f}")
        table.add_row("Max Drawdown", f"{best.user_attrs.get('max_drawdown', 0):.2f}%")

        console.print(table)

        # Top 5 trials
        console.print()
        console.rule("[bold cyan]Top 5 Trials[/bold cyan]", style="dim")

        sorted_trials = sorted(
            [t for t in self.study.trials if t.value is not None and t.value != float("-inf")],
            key=lambda t: t.value,  # type: ignore[arg-type,return-value]
            reverse=True,
        )[:5]

        if sorted_trials:
            table = Table()
            table.add_column("#", justify="center")
            table.add_column("Interval", justify="center")
            table.add_column("Period", justify="center")
            table.add_column("Swing", justify="center")
            table.add_column("Risk", justify="center")
            table.add_column("R:R", justify="center")
            table.add_column("Return", justify="right")
            table.add_column("DD", justify="center")
            table.add_column("PF", justify="center")

            for i, t in enumerate(sorted_trials, 1):
                ret = t.user_attrs.get("total_return", 0)
                ret_style = "green" if ret > 0 else "red"
                table.add_row(
                    str(i),
                    t.params["interval"],
                    t.params["period"],
                    str(t.params["swing_lb"]),
                    f"{t.params['risk_pct'] * 100:.1f}%",
                    f"{t.params['rr_ratio']:.1f}",
                    f"[{ret_style}]{ret:+.2f}%[/{ret_style}]",
                    f"{t.user_attrs.get('max_drawdown', 0):.2f}%",
                    f"{t.user_attrs.get('profit_factor', 0):.2f}",
                )

            console.print(table)

    def _print_pareto_report(self) -> None:
        """Print report for multi-objective optimization (Pareto front)."""
        if not self.study:
            return

        pareto_trials = self.study.best_trials

        console.print()
        console.rule("[bold cyan]Pareto Front (Best Trade-offs)[/bold cyan]", style="dim")
        console.print("[dim]These configs represent optimal trade-offs between return and drawdown[/dim]\n")

        if not pareto_trials:
            console.print("[yellow]No Pareto-optimal solutions found[/yellow]")
            return

        table = Table()
        table.add_column("#", justify="center")
        table.add_column("Interval", justify="center")
        table.add_column("Period", justify="center")
        table.add_column("Swing", justify="center")
        table.add_column("Risk", justify="center")
        table.add_column("R:R", justify="center")
        table.add_column("Return", justify="right")
        table.add_column("Drawdown", justify="center")
        table.add_column("Trades", justify="center")

        # Sort by return descending
        sorted_pareto = sorted(pareto_trials, key=lambda t: t.values[0], reverse=True)

        for i, t in enumerate(sorted_pareto[:10], 1):
            ret = t.values[0]
            dd = t.values[1]
            ret_style = "green" if ret > 0 else "red"
            table.add_row(
                str(i),
                t.params["interval"],
                t.params["period"],
                str(t.params["swing_lb"]),
                f"{t.params['risk_pct'] * 100:.1f}%",
                f"{t.params['rr_ratio']:.1f}",
                f"[{ret_style}]{ret:+.2f}%[/{ret_style}]",
                f"{dd:.2f}%",
                str(t.user_attrs.get("total_trades", "N/A")),
            )

        console.print(table)

        # Recommendations
        console.print()
        console.rule("[bold cyan]Recommendations[/bold cyan]", style="dim")

        if sorted_pareto:
            # Best return
            best_return = sorted_pareto[0]
            console.print(
                f"\n[bold]Highest Return:[/bold] {best_return.values[0]:+.2f}% (DD: {best_return.values[1]:.2f}%)"
            )
            console.print(
                f"  interval={best_return.params['interval']}, period={best_return.params['period']}, "
                f"swing_lb={best_return.params['swing_lb']}, "
                f"risk={best_return.params['risk_pct'] * 100:.2f}%, rr={best_return.params['rr_ratio']:.1f}"
            )

            # Best risk-adjusted (lowest dd among positive returns)
            positive_returns = [t for t in sorted_pareto if t.values[0] > 0]
            if positive_returns:
                best_risk_adj = min(positive_returns, key=lambda t: t.values[1])
                console.print(
                    f"\n[bold]Best Risk-Adjusted:[/bold] {best_risk_adj.values[0]:+.2f}% (DD: {best_risk_adj.values[1]:.2f}%)"
                )
                console.print(
                    f"  interval={best_risk_adj.params['interval']}, period={best_risk_adj.params['period']}, "
                    f"swing_lb={best_risk_adj.params['swing_lb']}, "
                    f"risk={best_risk_adj.params['risk_pct'] * 100:.2f}%, rr={best_risk_adj.params['rr_ratio']:.1f}"
                )


def tune(
    symbol: str,
    intervals: list[str] | None = None,
    periods: list[str] | None = None,
    n_trials: int = 100,
    objective: Literal["return", "calmar", "profit_factor", "multi"] = "calmar",
    capital: float = 100000,
    seed: int | None = None,
    entry_strategy: str | None = None,
    exit_strategy: str | None = None,
) -> OptunaTuner:
    """Convenience function to run Optuna tuning.

    Args:
        symbol: Stock symbol to optimize
        intervals: List of intervals to search (default: ["1h"])
        periods: List of periods to search (default: ["1y"])
        n_trials: Number of optimization trials
        objective: Optimization objective
            - "return": Maximize total return
            - "calmar": Maximize Calmar ratio (return/max_drawdown)
            - "profit_factor": Maximize profit factor
            - "multi": Multi-objective (maximize return, minimize drawdown)
        capital: Starting capital
        seed: Random seed for reproducibility (None = random each run)
        entry_strategy: Entry strategy to use (default: from config)
        exit_strategy: Exit strategy to use (default: from config)
    """
    # Get defaults from config if not specified
    from .presets import get_strategy_defaults

    defaults = get_strategy_defaults()

    config = TunerConfig(
        intervals=intervals or ["1h"],
        periods=periods or ["1y"],
        n_trials=n_trials,
        objective=objective,
        seed=seed,
        entry_strategy=entry_strategy or defaults.get("entry_strategy"),
        exit_strategy=exit_strategy or defaults.get("exit_strategy"),
    )

    tuner = OptunaTuner(symbol, capital, config)
    tuner.tune()
    tuner.print_report()

    return tuner

"""Walk-forward optimization to prevent overfitting.

Walk-forward analysis splits data into multiple train/test windows,
optimizing on training data and validating on out-of-sample test data.
This provides a more realistic estimate of future performance.
"""

from dataclasses import dataclass

import polars as pl
from rich.console import Console
from rich.table import Table

from .bot import MarketStructureBot
from .execution import ExecutionModel

console = Console()


@dataclass
class FoldResult:
    """Result from a single walk-forward fold."""

    fold: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_bars: int
    test_bars: int
    # Best params found on training data
    best_swing_lb: int
    best_risk_pct: float
    best_rr_ratio: float
    # In-sample (training) performance
    train_return: float
    train_trades: int
    train_win_rate: float
    train_max_dd: float
    # Out-of-sample (test) performance
    test_return: float
    test_trades: int
    test_win_rate: float
    test_max_dd: float


@dataclass
class WalkForwardResult:
    """Aggregated walk-forward analysis results."""

    symbol: str
    interval: str
    period: str
    n_folds: int
    train_ratio: float
    folds: list[FoldResult]
    # Aggregated metrics
    avg_train_return: float
    avg_test_return: float
    total_train_trades: int
    total_test_trades: int
    avg_train_win_rate: float
    avg_test_win_rate: float
    avg_train_dd: float
    avg_test_dd: float
    # Degradation analysis
    return_degradation: float  # train - test
    degradation_pct: float  # (train - test) / train * 100
    consistency: float  # % of folds where test > 0


class WalkForwardValidator:
    """Walk-forward validation for trading strategies.

    Splits historical data into multiple sequential train/test windows,
    finds optimal parameters on each training window, then tests on the
    following out-of-sample period.

    Example with 5 folds and 70/30 train/test ratio:
    ```
    Fold 1: [====TRAIN====][TEST]
    Fold 2:    [====TRAIN====][TEST]
    Fold 3:       [====TRAIN====][TEST]
    Fold 4:          [====TRAIN====][TEST]
    Fold 5:             [====TRAIN====][TEST]
    ```
    """

    def __init__(
        self,
        symbol: str,
        capital: float = 100000,
        n_folds: int = 5,
        train_ratio: float = 0.7,
        execution_model: ExecutionModel | None = None,
        swing_lb_range: list[int] | None = None,
        risk_pct_range: list[float] | None = None,
        rr_ratio_range: list[float] | None = None,
    ):
        """Initialize walk-forward validator.

        Args:
            symbol: Stock symbol
            capital: Starting capital per fold
            n_folds: Number of walk-forward folds (default: 5)
            train_ratio: Ratio of data for training in each fold (default: 0.7)
            execution_model: Execution cost model (default: standard costs)
            swing_lb_range: Swing lookback values to test (default: [3,4,5,6,7])
            risk_pct_range: Risk percent values to test (default: [0.01,0.015,0.02])
            rr_ratio_range: Risk/reward ratios to test (default: [1.5,2.0,2.5])
        """
        self.symbol = symbol
        self.capital = capital
        self.n_folds = n_folds
        self.train_ratio = train_ratio
        self.execution_model = execution_model or ExecutionModel()

        # Parameter search space (configurable, defaults cover more market conditions)
        self.swing_lb_range = swing_lb_range or [3, 4, 5, 6, 7]
        self.risk_pct_range = risk_pct_range or [0.01, 0.015, 0.02]
        self.rr_ratio_range = rr_ratio_range or [1.5, 2.0, 2.5]

    def validate(
        self,
        df: pl.DataFrame,
        interval: str = "1h",
        period: str = "1y",
        verbose: bool = True,
    ) -> WalkForwardResult:
        """Run walk-forward validation.

        Args:
            df: Historical price data
            interval: Data interval (for reporting)
            period: Data period (for reporting)
            verbose: Print progress and results
        """
        n_bars = len(df)

        # Calculate fold size based on overlapping windows
        # Each fold uses train_ratio of total data for training
        fold_size = int(n_bars / (self.n_folds + (1 - self.train_ratio) * self.n_folds))
        train_size = int(fold_size * self.train_ratio / (1 - self.train_ratio + self.train_ratio))

        # Recalculate to ensure proper coverage
        test_size = int(n_bars * (1 - self.train_ratio) / self.n_folds)
        train_size = int(test_size * self.train_ratio / (1 - self.train_ratio))

        if train_size < 50 or test_size < 10:
            raise ValueError(
                f"Insufficient data for {self.n_folds} folds. Need at least {50 * self.n_folds} bars, got {n_bars}"
            )

        if verbose:
            console.print()
            console.rule(f"[bold]Walk-Forward Analysis: {self.symbol}[/bold]")
            console.print(f"  Data: [cyan]{interval}[/cyan] / [cyan]{period}[/cyan] ({n_bars} bars)")
            console.print(f"  Folds: [cyan]{self.n_folds}[/cyan], Train ratio: [cyan]{self.train_ratio:.0%}[/cyan]")
            console.print(f"  Train size: ~{train_size} bars, Test size: ~{test_size} bars per fold")
            console.print()

        folds: list[FoldResult] = []

        for fold_idx in range(self.n_folds):
            # Calculate window positions
            test_end = n_bars - (self.n_folds - fold_idx - 1) * test_size
            test_start = test_end - test_size
            train_end = test_start
            train_start = max(0, train_end - train_size)

            train_df = df.slice(train_start, train_end - train_start)
            test_df = df.slice(test_start, test_end - test_start)

            if verbose:
                console.print(
                    f"[dim]Fold {fold_idx + 1}/{self.n_folds}: "
                    f"Train [{train_start}:{train_end}] ({len(train_df)} bars), "
                    f"Test [{test_start}:{test_end}] ({len(test_df)} bars)[/dim]"
                )

            # Find best params on training data
            best_params = self._optimize_fold(train_df)

            if best_params is None:
                if verbose:
                    console.print("  [yellow]No valid trades in training period[/yellow]")
                continue

            swing_lb, risk_pct, rr_ratio, train_stats = best_params

            # Test on out-of-sample data
            test_stats = self._run_backtest(test_df, swing_lb, risk_pct, rr_ratio)

            # Get date range for reporting
            train_start_date = str(train_df.row(0, named=True)["datetime"])[:10]
            train_end_date = str(train_df.row(-1, named=True)["datetime"])[:10]
            test_start_date = str(test_df.row(0, named=True)["datetime"])[:10]
            test_end_date = str(test_df.row(-1, named=True)["datetime"])[:10]

            fold_result = FoldResult(
                fold=fold_idx + 1,
                train_start=train_start_date,
                train_end=train_end_date,
                test_start=test_start_date,
                test_end=test_end_date,
                train_bars=len(train_df),
                test_bars=len(test_df),
                best_swing_lb=swing_lb,
                best_risk_pct=risk_pct,
                best_rr_ratio=rr_ratio,
                train_return=float(train_stats["return"]),
                train_trades=int(train_stats["trades"]),
                train_win_rate=float(train_stats["win_rate"]),
                train_max_dd=float(train_stats["max_dd"]),
                test_return=float(test_stats["return"]),
                test_trades=int(test_stats["trades"]),
                test_win_rate=float(test_stats["win_rate"]),
                test_max_dd=float(test_stats["max_dd"]),
            )
            folds.append(fold_result)

            if verbose:
                train_color = "green" if train_stats["return"] > 0 else "red"
                test_color = "green" if test_stats["return"] > 0 else "red"
                console.print(
                    f"  Best: swing={swing_lb}, risk={risk_pct * 100:.1f}%, rr={rr_ratio} | "
                    f"Train: [{train_color}]{train_stats['return']:+.1f}%[/{train_color}] | "
                    f"Test: [{test_color}]{test_stats['return']:+.1f}%[/{test_color}]"
                )

        if not folds:
            raise ValueError("No valid folds completed - check data quality")

        # Aggregate results
        result = self._aggregate_results(folds, interval, period)

        if verbose:
            self._print_report(result)

        return result

    def _optimize_fold(
        self,
        train_df: pl.DataFrame,
    ) -> tuple[int, float, float, dict[str, float]] | None:
        """Find best parameters on training data using simple grid search."""
        best_return = float("-inf")
        best_params: tuple[int, float, float, dict[str, float]] | None = None

        for swing_lb in self.swing_lb_range:
            for risk_pct in self.risk_pct_range:
                for rr_ratio in self.rr_ratio_range:
                    stats = self._run_backtest(train_df, swing_lb, risk_pct, rr_ratio)

                    if stats["trades"] >= 2 and stats["return"] > best_return:
                        best_return = stats["return"]
                        best_params = (swing_lb, risk_pct, rr_ratio, stats)

        return best_params

    def _run_backtest(
        self,
        df: pl.DataFrame,
        swing_lb: int,
        risk_pct: float,
        rr_ratio: float,
    ) -> dict[str, float | int]:
        """Run a single backtest and return key metrics."""
        bot = MarketStructureBot(
            capital=self.capital,
            risk_pct=risk_pct,
            rr_ratio=rr_ratio,
            swing_lb=swing_lb,
            execution_model=self.execution_model,
        )

        bot.backtest(df, self.symbol)

        if not bot.trades:
            return {"return": 0.0, "trades": 0, "win_rate": 0.0, "max_dd": 0.0}

        stats = bot.get_stats()

        return {
            "return": float(str(stats.get("total_return", "0")).rstrip("%")),
            "trades": int(str(stats.get("total_trades", "0"))),
            "win_rate": float(str(stats.get("win_rate", "0")).rstrip("%")),
            "max_dd": float(str(stats.get("max_drawdown", "0")).rstrip("%")),
        }

    def _aggregate_results(
        self,
        folds: list[FoldResult],
        interval: str,
        period: str,
    ) -> WalkForwardResult:
        """Aggregate results across all folds."""
        n = len(folds)

        avg_train_return = sum(f.train_return for f in folds) / n
        avg_test_return = sum(f.test_return for f in folds) / n
        total_train_trades = sum(f.train_trades for f in folds)
        total_test_trades = sum(f.test_trades for f in folds)
        avg_train_win_rate = sum(f.train_win_rate for f in folds) / n
        avg_test_win_rate = sum(f.test_win_rate for f in folds) / n
        avg_train_dd = sum(f.train_max_dd for f in folds) / n
        avg_test_dd = sum(f.test_max_dd for f in folds) / n

        return_degradation = avg_train_return - avg_test_return
        degradation_pct = (return_degradation / avg_train_return * 100) if avg_train_return != 0 else 0
        consistency = sum(1 for f in folds if f.test_return > 0) / n * 100

        return WalkForwardResult(
            symbol=self.symbol,
            interval=interval,
            period=period,
            n_folds=self.n_folds,
            train_ratio=self.train_ratio,
            folds=folds,
            avg_train_return=avg_train_return,
            avg_test_return=avg_test_return,
            total_train_trades=total_train_trades,
            total_test_trades=total_test_trades,
            avg_train_win_rate=avg_train_win_rate,
            avg_test_win_rate=avg_test_win_rate,
            avg_train_dd=avg_train_dd,
            avg_test_dd=avg_test_dd,
            return_degradation=return_degradation,
            degradation_pct=degradation_pct,
            consistency=consistency,
        )

    def _print_report(self, result: WalkForwardResult) -> None:
        """Print walk-forward analysis report."""
        console.print()
        console.rule("[bold cyan]Walk-Forward Results[/bold cyan]")

        # Fold details table
        table = Table(title="Fold Details")
        table.add_column("Fold", justify="center")
        table.add_column("Train Period", justify="center")
        table.add_column("Test Period", justify="center")
        table.add_column("Best Params", justify="center")
        table.add_column("Train Return", justify="right")
        table.add_column("Test Return", justify="right")
        table.add_column("Test Trades", justify="center")

        for f in result.folds:
            train_color = "green" if f.train_return > 0 else "red"
            test_color = "green" if f.test_return > 0 else "red"
            table.add_row(
                str(f.fold),
                f"{f.train_start} → {f.train_end}",
                f"{f.test_start} → {f.test_end}",
                f"sw={f.best_swing_lb} r={f.best_risk_pct * 100:.1f}% rr={f.best_rr_ratio}",
                f"[{train_color}]{f.train_return:+.1f}%[/{train_color}]",
                f"[{test_color}]{f.test_return:+.1f}%[/{test_color}]",
                str(f.test_trades),
            )

        console.print(table)

        # Summary
        console.print()
        console.rule("[bold cyan]Summary[/bold cyan]", style="dim")

        summary = Table(show_header=False, box=None, padding=(0, 2))
        summary.add_column("Metric", style="cyan")
        summary.add_column("Train (In-Sample)")
        summary.add_column("Test (Out-of-Sample)")

        train_ret_color = "green" if result.avg_train_return > 0 else "red"
        test_ret_color = "green" if result.avg_test_return > 0 else "red"

        summary.add_row(
            "Avg Return",
            f"[{train_ret_color}]{result.avg_train_return:+.2f}%[/{train_ret_color}]",
            f"[{test_ret_color}]{result.avg_test_return:+.2f}%[/{test_ret_color}]",
        )
        summary.add_row(
            "Total Trades",
            str(result.total_train_trades),
            str(result.total_test_trades),
        )
        summary.add_row(
            "Avg Win Rate",
            f"{result.avg_train_win_rate:.1f}%",
            f"{result.avg_test_win_rate:.1f}%",
        )
        summary.add_row(
            "Avg Max DD",
            f"{result.avg_train_dd:.1f}%",
            f"{result.avg_test_dd:.1f}%",
        )

        console.print(summary)

        # Overfitting assessment
        console.print()
        console.rule("[bold cyan]Overfitting Assessment[/bold cyan]", style="dim")

        console.print(
            f"  Return Degradation: [yellow]{result.return_degradation:+.2f}%[/yellow] "
            f"({result.degradation_pct:.0f}% drop from train to test)"
        )
        console.print(f"  Consistency: [cyan]{result.consistency:.0f}%[/cyan] of folds profitable OOS")

        # Risk assessment
        if result.degradation_pct > 50 or result.consistency < 40:
            console.print()
            console.print("[red bold]⚠ HIGH OVERFITTING RISK[/red bold]")
            console.print("[red]  Strategy shows significant performance degradation out-of-sample.[/red]")
            console.print("[yellow]  Recommendations:[/yellow]")
            console.print("[yellow]    - Use simpler parameters (fewer variables)[/yellow]")
            console.print("[yellow]    - Test on longer time periods[/yellow]")
            console.print("[yellow]    - Consider the strategy may not have a real edge[/yellow]")
        elif result.degradation_pct > 25 or result.consistency < 60:
            console.print()
            console.print("[yellow bold]⚠ MODERATE OVERFITTING RISK[/yellow bold]")
            console.print("[yellow]  Some performance degradation observed.[/yellow]")
            console.print("[dim]  Consider additional validation before live trading.[/dim]")
        elif result.avg_test_return > 0:
            console.print()
            console.print("[green bold]✓ LOW OVERFITTING RISK[/green bold]")
            console.print("[green]  Strategy maintains positive returns out-of-sample.[/green]")
            console.print(
                f"[dim]  Expected real-world return: ~{result.avg_test_return:.1f}% (based on OOS performance)[/dim]"
            )
        else:
            console.print()
            console.print("[red bold]⚠ STRATEGY NOT PROFITABLE[/red bold]")
            console.print("[red]  Out-of-sample returns are negative.[/red]")
            console.print("[red]  This strategy likely has no real edge.[/red]")


def walk_forward(
    symbol: str,
    df: pl.DataFrame,
    interval: str = "1h",
    period: str = "1y",
    n_folds: int = 5,
    train_ratio: float = 0.7,
    capital: float = 100000,
    execution_model: ExecutionModel | None = None,
    verbose: bool = True,
    swing_lb_range: list[int] | None = None,
    risk_pct_range: list[float] | None = None,
    rr_ratio_range: list[float] | None = None,
) -> WalkForwardResult:
    """Convenience function to run walk-forward validation.

    Args:
        symbol: Stock symbol
        df: Historical price data
        interval: Data interval (for reporting)
        period: Data period (for reporting)
        n_folds: Number of walk-forward folds
        train_ratio: Ratio of data for training in each fold
        capital: Starting capital
        execution_model: Execution cost model
        verbose: Print progress and results
        swing_lb_range: Swing lookback values to test
        risk_pct_range: Risk percent values to test
        rr_ratio_range: Risk/reward ratios to test
    """
    validator = WalkForwardValidator(
        symbol=symbol,
        capital=capital,
        n_folds=n_folds,
        train_ratio=train_ratio,
        execution_model=execution_model,
        swing_lb_range=swing_lb_range,
        risk_pct_range=risk_pct_range,
        rr_ratio_range=rr_ratio_range,
    )
    return validator.validate(df, interval, period, verbose)

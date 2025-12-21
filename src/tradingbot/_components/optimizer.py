import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from itertools import product
from typing import TypedDict

import plotext as plt
import polars as pl
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from .bot import MarketStructureBot

console = Console()

# Number of parallel workers (default to CPU count)
MAX_WORKERS = os.cpu_count() or 4


def _run_backtest_worker(
    args: tuple[pl.DataFrame, str, float, int, float, float],
) -> OptimizationResult | None:
    """Worker function for parallel backtest execution."""
    df, symbol, capital, swing_lb, risk, rr = args

    bot = MarketStructureBot(
        capital=capital,
        risk_pct=risk,
        rr_ratio=rr,
        swing_lb=swing_lb,
    )

    bot.backtest(df, symbol)

    if not bot.trades:
        return None

    stats = bot.get_stats()
    if "error" in stats:
        return None

    # Parse stats (they're formatted strings)
    win_rate = float(str(stats["win_rate"]).rstrip("%"))
    total_return = float(str(stats["total_return"]).rstrip("%"))
    pf_str = str(stats["profit_factor"])
    profit_factor = 999.0 if pf_str == "inf" else float(pf_str)
    max_dd = float(str(stats["max_drawdown"]).rstrip("%"))

    return OptimizationResult(
        swing_lookback=swing_lb,
        risk_pct=risk,
        rr_ratio=rr,
        total_trades=int(stats["total_trades"]),
        win_rate=win_rate,
        total_return=total_return,
        profit_factor=profit_factor,
        max_drawdown=max_dd,
    )


class OptimizationResult(TypedDict):
    swing_lookback: int
    risk_pct: float
    rr_ratio: float
    total_trades: int
    win_rate: float
    total_return: float
    profit_factor: float
    max_drawdown: float


@dataclass
class ParameterRanges:
    """Define ranges for parameter optimization."""

    swing_lookback: list[int]
    risk_pct: list[float]
    rr_ratio: list[float]

    @classmethod
    def default(cls) -> ParameterRanges:
        """Default parameter ranges for optimization."""
        return cls(
            swing_lookback=[3, 4, 5, 6, 7, 8, 9, 10],
            risk_pct=[0.005, 0.01, 0.015, 0.02],  # 0.5%, 1%, 1.5%, 2%
            rr_ratio=[1.5, 2.0, 2.5, 3.0],
        )

    def total_combinations(self) -> int:
        return len(self.swing_lookback) * len(self.risk_pct) * len(self.rr_ratio)


class Optimizer:
    """Grid search optimizer for trading bot parameters."""

    def __init__(
        self,
        df: pl.DataFrame,
        symbol: str = "UNKNOWN",
        capital: float = 100000,
        params: ParameterRanges | None = None,
    ):
        self.df: pl.DataFrame = df
        self.symbol: str = symbol
        self.capital: float = capital
        self.params: ParameterRanges = params or ParameterRanges.default()
        self.results: list[OptimizationResult] = []

    def optimize(self, verbose: bool = True, parallel: bool = True) -> list[OptimizationResult]:
        """Run optimization across all parameter combinations.

        Args:
            verbose: Show progress bar
            parallel: Run backtests in parallel (default True)
        """
        combinations = list(
            product(
                self.params.swing_lookback,
                self.params.risk_pct,
                self.params.rr_ratio,
            )
        )

        total: int = len(combinations)
        self.results = []

        if parallel:
            # Prepare args for parallel execution
            worker_args = [
                (self.df, self.symbol, self.capital, swing_lb, risk, rr) for swing_lb, risk, rr in combinations
            ]

            if verbose:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task(f"Testing {total} combinations ({MAX_WORKERS} workers)...", total=total)

                    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
                        futures = {executor.submit(_run_backtest_worker, args): args for args in worker_args}
                        for future in as_completed(futures):
                            result = future.result()
                            if result:
                                self.results.append(result)
                            progress.update(task, advance=1)

                console.print(f"[green]Completed {len(self.results)} valid backtests[/green]")
            else:
                with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    for result in executor.map(_run_backtest_worker, worker_args):
                        if result:
                            self.results.append(result)
        else:
            # Sequential execution
            if verbose:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task(f"Testing {total} combinations...", total=total)

                    for swing_lb, risk, rr in combinations:
                        opt_result = self._run_single(swing_lb, risk, rr)
                        if opt_result:
                            self.results.append(opt_result)
                        progress.update(task, advance=1)

                console.print(f"[green]Completed {len(self.results)} valid backtests[/green]")
            else:
                for swing_lb, risk, rr in combinations:
                    result = self._run_single(swing_lb, risk, rr)
                    if result:
                        self.results.append(result)

        return self.results

    def _run_single(self, swing_lb: int, risk: float, rr: float) -> OptimizationResult | None:
        """Run a single backtest with given parameters."""
        bot = MarketStructureBot(
            capital=self.capital,
            risk_pct=risk,
            rr_ratio=rr,
            swing_lb=swing_lb,
        )

        bot.backtest(self.df, self.symbol)

        if not bot.trades:
            return None

        stats = bot.get_stats()
        if "error" in stats:
            return None

        # Parse stats (they're formatted strings)
        win_rate: float = float(str(stats["win_rate"]).rstrip("%"))
        total_return: float = float(str(stats["total_return"]).rstrip("%"))
        max_dd: float = float(str(stats["max_drawdown"]).rstrip("%"))

        pf_str: str = str(stats["profit_factor"])
        profit_factor: float = float(pf_str) if pf_str != "inf" else 999.0

        return {
            "swing_lookback": swing_lb,
            "risk_pct": risk,
            "rr_ratio": rr,
            "total_trades": int(stats["total_trades"]),
            "win_rate": win_rate,
            "total_return": total_return,
            "profit_factor": profit_factor,
            "max_drawdown": max_dd,
        }

    def best_by_return(self) -> OptimizationResult | None:
        """Get best parameters by total return."""
        if not self.results:
            return None
        return max(self.results, key=lambda r: r["total_return"])

    def best_by_sharpe(self) -> OptimizationResult | None:
        """Get best parameters by risk-adjusted return (return/drawdown)."""
        if not self.results:
            return None
        return max(
            self.results,
            key=lambda r: r["total_return"] / max(r["max_drawdown"], 0.1),
        )

    def best_by_profit_factor(self) -> OptimizationResult | None:
        """Get best parameters by profit factor."""
        if not self.results:
            return None
        # Filter for minimum trades
        valid = [r for r in self.results if r["total_trades"] >= 5]
        if not valid:
            return None
        return max(valid, key=lambda r: r["profit_factor"])

    def top_results(self, n: int = 10, sort_by: str = "total_return") -> pl.DataFrame:
        """Get top N results as DataFrame."""
        if not self.results:
            return pl.DataFrame()

        df = pl.DataFrame(self.results)
        df = df.sort(sort_by, descending=True).head(n)
        return df

    def print_report(self) -> None:
        """Print optimization report."""
        if not self.results:
            console.print("[yellow]No results to report[/yellow]")
            return

        console.print()
        console.rule("[bold]OPTIMIZATION REPORT[/bold]")

        console.print(f"\nTested [cyan]{len(self.results)}[/cyan] valid parameter combinations")
        console.print(f"Symbol: [yellow]{self.symbol}[/yellow]")
        console.print(f"Data: [cyan]{len(self.df)}[/cyan] bars")

        # Best by return
        best_ret = self.best_by_return()
        if best_ret:
            console.print()
            console.rule("[bold cyan]Best by Total Return[/bold cyan]", style="dim")
            self._print_result(best_ret)

        # Best by risk-adjusted
        best_sharpe = self.best_by_sharpe()
        if best_sharpe and best_sharpe != best_ret:
            console.print()
            console.rule("[bold cyan]Best by Risk-Adjusted Return[/bold cyan]", style="dim")
            self._print_result(best_sharpe)

        # Best by profit factor
        best_pf = self.best_by_profit_factor()
        if best_pf and best_pf not in [best_ret, best_sharpe]:
            console.print()
            console.rule("[bold cyan]Best by Profit Factor[/bold cyan]", style="dim")
            self._print_result(best_pf)

        # Top 5 table
        console.print()
        console.rule("[bold cyan]Top 5 Parameter Sets[/bold cyan]", style="dim")
        top5 = self.top_results(5)
        if not top5.is_empty():
            table = Table()
            table.add_column("Swing LB", justify="center")
            table.add_column("Risk %", justify="center")
            table.add_column("R:R", justify="center")
            table.add_column("Trades", justify="center")
            table.add_column("Win Rate", justify="center")
            table.add_column("Return", justify="right")
            table.add_column("PF", justify="center")
            table.add_column("Max DD", justify="center")

            for row in top5.iter_rows(named=True):
                ret_style = "green" if row["total_return"] > 0 else "red"
                table.add_row(
                    str(row["swing_lookback"]),
                    f"{row['risk_pct'] * 100:.1f}%",
                    str(row["rr_ratio"]),
                    str(row["total_trades"]),
                    f"{row['win_rate']:.1f}%",
                    f"[{ret_style}]{row['total_return']:+.2f}%[/{ret_style}]",
                    f"{row['profit_factor']:.2f}",
                    f"{row['max_drawdown']:.2f}%",
                )
            console.print(table)

    def _print_result(self, r: OptimizationResult) -> None:
        """Print a single result."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Param", style="cyan")
        table.add_column("Value")

        table.add_row("swing_lookback", str(r["swing_lookback"]))
        table.add_row("risk_pct", f"{r['risk_pct'] * 100:.1f}%")
        table.add_row("rr_ratio", str(r["rr_ratio"]))
        table.add_row("", "")
        table.add_row("Total Trades", str(r["total_trades"]))
        table.add_row("Win Rate", f"{r['win_rate']:.1f}%")

        ret_style = "green" if r["total_return"] > 0 else "red"
        table.add_row("Total Return", f"[{ret_style}]{r['total_return']:+.2f}%[/{ret_style}]")
        table.add_row("Profit Factor", f"{r['profit_factor']:.2f}")
        table.add_row("Max Drawdown", f"{r['max_drawdown']:.2f}%")

        console.print(table)

    def plot_heatmap(self, metric: str = "total_return") -> None:
        """Plot heatmap of parameter performance."""
        if not self.results:
            console.print("[yellow]No results to plot[/yellow]")
            return

        df = pl.DataFrame(self.results)

        console.print()
        console.rule(f"[bold]Parameter Heatmaps ({metric})[/bold]")

        # Heatmap 1: swing_lookback vs rr_ratio (averaged over risk_pct)
        pivot1 = (
            df.group_by(["swing_lookback", "rr_ratio"])
            .agg(pl.col(metric).mean().alias("value"))
            .pivot(on="rr_ratio", index="swing_lookback", values="value")
            .sort("swing_lookback")
        )
        self._print_text_heatmap(
            pivot1,
            "Swing Lookback vs R:R Ratio",
            "Swing LB",
            "R:R",
            "swing_lookback",
        )

        # Heatmap 2: swing_lookback vs risk_pct (averaged over rr_ratio)
        pivot2 = (
            df.group_by(["swing_lookback", "risk_pct"])
            .agg(pl.col(metric).mean().alias("value"))
            .pivot(on="risk_pct", index="swing_lookback", values="value")
            .sort("swing_lookback")
        )
        self._print_text_heatmap(
            pivot2,
            "Swing Lookback vs Risk %",
            "Swing LB",
            "Risk %",
            "swing_lookback",
            format_cols_as_pct=True,
        )

        # Heatmap 3: risk_pct vs rr_ratio (averaged over swing_lookback)
        pivot3 = (
            df.group_by(["risk_pct", "rr_ratio"])
            .agg(pl.col(metric).mean().alias("value"))
            .pivot(on="rr_ratio", index="risk_pct", values="value")
            .sort("risk_pct")
        )
        self._print_text_heatmap(
            pivot3,
            "Risk % vs R:R Ratio",
            "Risk %",
            "R:R",
            "risk_pct",
            format_rows_as_pct=True,
        )

    def _print_text_heatmap(
        self,
        pivot: pl.DataFrame,
        title: str,
        row_label: str,
        col_label: str,
        index_col: str,
        format_cols_as_pct: bool = False,
        format_rows_as_pct: bool = False,
    ) -> None:
        """Print a text-based heatmap using Rich table."""
        console.print(f"\n[bold]{title}[/bold]")

        # Get value columns (all except index column)
        value_cols = [c for c in pivot.columns if c != index_col]
        if not value_cols:
            console.print("  [dim]No data[/dim]")
            return

        # Get min/max for coloring
        all_values: list[float] = []
        for col in value_cols:
            all_values.extend([v for v in pivot[col].to_list() if v is not None])
        if not all_values:
            console.print("  [dim]No data[/dim]")
            return

        vmin, vmax = min(all_values), max(all_values)
        vmid = (vmin + vmax) / 2

        # Create table
        table = Table(title=f"{col_label} →", show_header=True, header_style="bold")
        table.add_column(row_label, style="cyan")

        for col in value_cols:
            col_name = f"{float(col) * 100:.1f}%" if format_cols_as_pct else str(col)
            table.add_column(col_name, justify="right")

        # Data rows
        for row in pivot.iter_rows(named=True):
            idx_val = row[index_col]
            idx_str = f"{idx_val * 100:.1f}%" if format_rows_as_pct else str(idx_val)
            row_data: list[str] = [idx_str]
            for col in value_cols:
                val = row[col]
                if val is None:
                    row_data.append("[dim]--[/dim]")
                else:
                    # Color based on value
                    if val >= vmid:
                        intensity = (val - vmid) / (vmax - vmid + 0.001)
                        color = "green" if intensity > 0.5 else "yellow"
                    else:
                        color = "red"
                    row_data.append(f"[{color}]{val:+.1f}%[/{color}]")
            table.add_row(*row_data)

        console.print(table)

    def check_overfitting(self, test_ratio: float = 0.3) -> dict[str, float]:
        """
        Check for overfitting using walk-forward analysis.

        Splits data into train/test and compares performance.
        Large differences suggest overfitting.
        """
        console.print()
        console.rule("[bold]Overfitting Analysis[/bold]")

        n_bars = len(self.df)
        split_idx = int(n_bars * (1 - test_ratio))

        train_df = self.df.head(split_idx)
        test_df = self.df.slice(split_idx, n_bars - split_idx)

        console.print(f"Training period: [cyan]{len(train_df)}[/cyan] bars")
        console.print(f"Testing period:  [cyan]{len(test_df)}[/cyan] bars")

        # Find best params on training data
        console.print("\n[dim]Optimizing on training data...[/dim]")
        train_opt = Optimizer(train_df, self.symbol, self.capital, self.params)
        train_opt.optimize(verbose=False)

        best_train = train_opt.best_by_return()
        if not best_train:
            console.print("[yellow]No valid results on training data[/yellow]")
            return {}

        console.print("\n[bold]Best training params:[/bold]")
        console.print(
            f"  swing_lookback={best_train['swing_lookback']}, "
            f"risk={best_train['risk_pct'] * 100:.1f}%, "
            f"rr={best_train['rr_ratio']}"
        )
        console.print(f"  Training return: [green]{best_train['total_return']:+.2f}%[/green]")

        # Test on out-of-sample data
        test_bot = MarketStructureBot(
            capital=self.capital,
            risk_pct=best_train["risk_pct"],
            rr_ratio=best_train["rr_ratio"],
            swing_lb=best_train["swing_lookback"],
        )
        test_bot.backtest(test_df, self.symbol)

        if not test_bot.trades:
            console.print("\n[yellow]Warning: No trades in test period[/yellow]")
            return {"train_return": best_train["total_return"], "test_return": 0.0}

        test_stats = test_bot.get_stats()
        test_return = float(str(test_stats.get("total_return", "0")).rstrip("%"))

        test_color = "green" if test_return > 0 else "red"
        console.print(f"  Test return:     [{test_color}]{test_return:+.2f}%[/{test_color}]")

        # Calculate degradation
        degradation = best_train["total_return"] - test_return

        console.print("\n[bold]Overfitting Assessment:[/bold]")

        if degradation > best_train["total_return"] * 0.5:
            console.print(
                f"[red bold]⚠ HIGH RISK:[/red bold] [red]Performance dropped {degradation:.1f}% on test data[/red]"
            )
            console.print("[red]  The optimized parameters may be overfit to historical data[/red]")
            console.print("[yellow]  Recommendation: Use more conservative parameters or longer test period[/yellow]")
        elif degradation > best_train["total_return"] * 0.25:
            console.print(
                f"[yellow bold]⚠ MODERATE RISK:[/yellow bold] [yellow]Performance dropped {degradation:.1f}% on test data[/yellow]"
            )
            console.print("[yellow]  Consider validating on additional out-of-sample data[/yellow]")
        elif test_return > 0:
            console.print(
                "[green bold]✓ LOW RISK:[/green bold] [green]Strategy maintains positive returns on test data[/green]"
            )
            console.print("[green]  Parameters appear robust[/green]")
        else:
            console.print("[red bold]⚠ WARNING:[/red bold] [red]Strategy lost money on test data[/red]")
            console.print("[red]  Optimized parameters may not generalize well[/red]")

        # Sensitivity analysis
        self._sensitivity_analysis(best_train)

        return {
            "train_return": best_train["total_return"],
            "test_return": test_return,
            "degradation": degradation,
        }

    def _sensitivity_analysis(self, best: OptimizationResult) -> None:
        """Check how sensitive results are to small parameter changes."""
        console.print("\n[bold]Parameter Sensitivity:[/bold]")

        df = pl.DataFrame(self.results)

        # Check nearby swing_lookback values
        nearby_swing = df.filter(
            (pl.col("risk_pct") == best["risk_pct"])
            & (pl.col("rr_ratio") == best["rr_ratio"])
            & (abs(pl.col("swing_lookback") - best["swing_lookback"]) <= 1)
        )["total_return"]

        if len(nearby_swing) > 1:
            std_val = nearby_swing.std()
            swing_std: float = float(std_val) if isinstance(std_val, (int, float)) else 0.0
            if swing_std > 5:
                console.print(f"[yellow]  swing_lookback: HIGH sensitivity (±{swing_std:.1f}%)[/yellow]")
            else:
                console.print(f"[green]  swing_lookback: stable (±{swing_std:.1f}%)[/green]")

        # Check nearby rr_ratio values
        nearby_rr = df.filter(
            (pl.col("risk_pct") == best["risk_pct"]) & (pl.col("swing_lookback") == best["swing_lookback"])
        )["total_return"]

        if len(nearby_rr) > 1:
            std_val = nearby_rr.std()
            rr_std: float = float(std_val) if isinstance(std_val, (int, float)) else 0.0
            if rr_std > 5:
                console.print(f"[yellow]  rr_ratio: HIGH sensitivity (±{rr_std:.1f}%)[/yellow]")
            else:
                console.print(f"[green]  rr_ratio: stable (±{rr_std:.1f}%)[/green]")

    def plot_parameter_impact(self) -> None:
        """Plot how each parameter affects returns."""
        if not self.results:
            console.print("[yellow]No results to plot[/yellow]")
            return

        df = pl.DataFrame(self.results)

        plt.clf()
        plt.theme("clear")
        plt.subplots(1, 3)

        # Plot 1: swing_lookback impact
        plt.subplot(1, 1)
        swing_avg = df.group_by("swing_lookback").agg(pl.col("total_return").mean().alias("avg")).sort("swing_lookback")
        plt.bar(swing_avg["swing_lookback"].to_list(), swing_avg["avg"].to_list(), color="cyan")
        plt.title("Swing Lookback Impact")
        plt.xlabel("Swing Lookback")
        plt.ylabel("Avg Return %")

        # Plot 2: risk_pct impact
        plt.subplot(1, 2)
        risk_avg = df.group_by("risk_pct").agg(pl.col("total_return").mean().alias("avg")).sort("risk_pct")
        plt.bar(
            [f"{x * 100:.1f}%" for x in risk_avg["risk_pct"].to_list()],
            risk_avg["avg"].to_list(),
            color="magenta",
        )
        plt.title("Risk % Impact")
        plt.xlabel("Risk %")

        # Plot 3: rr_ratio impact
        plt.subplot(1, 3)
        rr_avg = df.group_by("rr_ratio").agg(pl.col("total_return").mean().alias("avg")).sort("rr_ratio")
        plt.bar([str(x) for x in rr_avg["rr_ratio"].to_list()], rr_avg["avg"].to_list(), color="yellow")
        plt.title("R:R Ratio Impact")
        plt.xlabel("R:R Ratio")

        plt.show()


def optimize(
    symbol: str,
    period: str = "2y",
    interval: str = "1d",
    capital: float = 100000,
    params: ParameterRanges | None = None,
    parallel: bool = True,
) -> Optimizer:
    """Convenience function to run optimization."""
    from .feeds import DataFeed

    df: pl.DataFrame = DataFeed.history(symbol, period=period, interval=interval)

    optimizer = Optimizer(df, symbol, capital, params)
    optimizer.optimize(parallel=parallel)
    optimizer.print_report()

    return optimizer


def main() -> None:
    """CLI entry point for optimizer."""
    import argparse

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

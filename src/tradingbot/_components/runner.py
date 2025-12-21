from typing import TypedDict, Unpack

import polars as pl
from rich.console import Console
from rich.table import Table

from tradingbot.config import get_bot_config

from .bot import MarketStructureBot, Stats
from .feeds import DataFeed


class BacktestParams(TypedDict, total=False):
    period: str
    interval: str
    capital: float
    risk: float
    rr: float
    swing_lb: int


console = Console()


def run_single_backtest(
    symbol: str,
    period: str = "2y",
    interval: str = "1d",
    capital: float | None = None,
    risk: float | None = None,
    rr: float | None = None,
    swing_lb: int | None = None,
) -> tuple[MarketStructureBot, pl.DataFrame]:
    cfg = get_bot_config()
    capital_val = capital if capital is not None else cfg.capital
    risk_pct = risk if risk is not None else cfg.risk_pct
    rr_ratio = rr if rr is not None else cfg.rr_ratio
    swing_lb_val = swing_lb if swing_lb is not None else cfg.swing_lb

    console.print()
    console.rule(f"[bold yellow]BACKTEST: {symbol}[/bold yellow]", style="cyan")

    df: pl.DataFrame = DataFeed.history(symbol, period=period, interval=interval)

    bot = MarketStructureBot(
        capital=capital_val,
        risk_pct=risk_pct,
        rr_ratio=rr_ratio,
        swing_lb=swing_lb_val,
    )

    results: pl.DataFrame = bot.backtest(df, symbol)

    stats: Stats | dict[str, str] = bot.get_stats()

    # Performance summary table
    stats_table = Table(title="Performance Summary", show_header=False, box=None, padding=(0, 2))
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value")

    for k, v in stats.items():
        val_str = str(v)
        style = ""
        if "pnl" in k.lower() or "return" in k.lower():
            if val_str.startswith("-") or val_str.startswith("$-"):
                style = "red"
            elif val_str.startswith("$") or (val_str and val_str[0].isdigit()):
                style = "green"
        stats_table.add_row(k, f"[{style}]{v}[/{style}]" if style else str(v))

    console.print()
    console.print(stats_table)

    # Recent trades table
    if bot.trades:
        console.print()
        trades_table = Table(title="Recent Trades", box=None)
        trades_table.add_column("Status", justify="center")
        trades_table.add_column("Direction", justify="center")
        trades_table.add_column("Entry", justify="right")
        trades_table.add_column("Exit", justify="right")
        trades_table.add_column("P&L", justify="right")
        trades_table.add_column("Reason", justify="center")

        for t in bot.trades[-5:]:
            if t.pnl > 0:
                status = "[green]WIN[/green]"
                pnl_style = "green"
            else:
                status = "[red]LOSS[/red]"
                pnl_style = "red"

            trades_table.add_row(
                status,
                t.direction,
                f"${t.entry_price:.2f}",
                f"${t.exit_price:.2f}",
                f"[{pnl_style}]${t.pnl:+,.2f}[/{pnl_style}]",
                t.exit_reason,
            )

        console.print(trades_table)

    return bot, results


def run_multi_backtest(symbols: list[str], **kwargs: Unpack[BacktestParams]) -> list[Stats | dict[str, str]]:
    all_stats: list[Stats | dict[str, str]] = []

    for sym in symbols:
        try:
            bot: MarketStructureBot
            bot, _ = run_single_backtest(sym, **kwargs)
            stats: Stats | dict[str, str] = bot.get_stats()
            all_stats.append(stats)
        except Exception as e:
            console.print(f"[red]Error with {sym}: {e}[/red]")

    if all_stats:
        console.print()
        console.rule("[bold]Multi-Symbol Comparison[/bold]")

        comparison_table = Table()
        if all_stats:
            for key in all_stats[0]:
                comparison_table.add_column(key)

            for stats in all_stats:
                comparison_table.add_row(*[str(v) for v in stats.values()])

        console.print(comparison_table)

    return all_stats


def main() -> None:
    """CLI entry point for backtest."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run trading bot backtest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  tradingbot SPY
  tradingbot AAPL TSLA GOOGL
  tradingbot SPY --period 5y --interval 1d
  tradingbot AAPL --capital 50000 --risk 0.02
        """,
    )

    parser.add_argument("symbols", nargs="+", help="Stock symbol(s) to backtest (e.g., SPY, AAPL)")
    parser.add_argument("--period", default="2y", help="Data period (default: 2y)")
    parser.add_argument("--interval", default="1d", help="Data interval (default: 1d)")
    parser.add_argument("--capital", type=float, help="Starting capital (uses config default)")
    parser.add_argument("--risk", type=float, help="Risk per trade as decimal (e.g., 0.01 for 1%%)")
    parser.add_argument("--rr", type=float, help="Reward/risk ratio (e.g., 2.0)")
    parser.add_argument("--swing-lb", type=int, help="Swing lookback period")

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
        )

import time
from datetime import datetime
from typing import TypedDict, Unpack

import polars as pl
from rich.console import Console
from rich.table import Table

from tradingbot.config import get_bot_config
from tradingbot.types import Position, Signal

from .bot import BacktestCallbacks, MarketStructureBot, Stats
from .feeds import DataFeed


class BacktestParams(TypedDict, total=False):
    period: str
    interval: str
    capital: float
    risk: float
    rr: float
    swing_lb: int
    refresh: bool
    verbose: bool
    speed: float


console = Console()


def make_verbose_callbacks() -> BacktestCallbacks:
    """Create callbacks for verbose backtest output."""
    callbacks = BacktestCallbacks()

    @callbacks.on_bar
    def on_bar(
        bar_time: datetime, symbol: str, price: float, signal: Signal, trend: str, position: Position | None
    ) -> None:
        pos_str = f"[{position.direction}]" if position else ""
        signal_color = {"BUY": "green", "SELL": "red", "HOLD": "dim"}.get(signal.value, "white")
        console.print(
            f"[dim]{bar_time.strftime('%Y-%m-%d %H:%M')}[/dim] "
            f"{symbol} ${price:.2f} "
            f"[{signal_color}]{signal.value}[/{signal_color}] "
            f"[dim]{trend}[/dim] {pos_str}"
        )

    @callbacks.on_signal
    def on_signal(direction: str, symbol: str, entry: float, stop: float, tp: float, size: float) -> None:
        console.print()
        emoji = "🔼" if direction == "LONG" else "🔽"
        console.print(f"[bold cyan]{emoji} {direction} SIGNAL: {symbol}[/bold cyan]")
        console.print(f"  Entry: ${entry:.2f}  Stop: ${stop:.2f}  TP: ${tp:.2f}  Size: {size:.2f}")

    @callbacks.on_trade_closed
    def on_trade_closed(direction: str, symbol: str, entry: float, exit_price: float, pnl: float, reason: str) -> None:
        console.print()
        emoji = "🛑" if reason == "STOP_LOSS" else "✅"
        console.print(f"[bold]{emoji} EXIT {symbol}: {reason}[/bold]")
        console.print(f"  Entry: ${entry:.2f}  Exit: ${exit_price:.2f}")
        color = "green" if pnl > 0 else "red"
        console.print(f"  P&L: [{color}]${pnl:+,.2f}[/{color}]")

    return callbacks


def run_single_backtest(
    symbol: str,
    period: str = "2y",
    interval: str = "1d",
    capital: float | None = None,
    risk: float | None = None,
    rr: float | None = None,
    swing_lb: int | None = None,
    refresh: bool = False,
    verbose: bool = False,
    speed: float = 0,
) -> tuple[MarketStructureBot, pl.DataFrame]:
    cfg = get_bot_config()
    capital_val = capital if capital is not None else cfg.capital
    risk_pct = risk if risk is not None else cfg.risk_pct
    rr_ratio = rr if rr is not None else cfg.rr_ratio
    swing_lb_val = swing_lb if swing_lb is not None else cfg.swing_lb

    console.print()
    console.rule(f"[bold yellow]BACKTEST: {symbol}[/bold yellow]", style="cyan")

    df: pl.DataFrame = DataFeed.history(symbol, period=period, interval=interval, refresh=refresh)

    if verbose or speed > 0:
        console.print(f"[dim]Bars: {len(df)} | Period: {period} | Interval: {interval}[/dim]")
        if speed > 0:
            console.print(f"[dim]Speed: {speed} bars/sec[/dim]")
        console.print()

    bot = MarketStructureBot(
        capital=capital_val,
        risk_pct=risk_pct,
        rr_ratio=rr_ratio,
        swing_lb=swing_lb_val,
    )

    callbacks = make_verbose_callbacks() if verbose else None

    # Use time.sleep for speed control instead of asyncio
    results: list[dict[str, object]] = []
    bot.symbol = symbol
    bot.callbacks = callbacks
    bot.position = None
    bot.trades = []
    bot.equity = [bot.pos_sizer.capital]

    for i in range(len(df)):
        bar = df.row(i, named=True)
        price = float(bar["close"])
        bar_time: datetime = bar["datetime"]

        if bot.position:
            if bot.trailing_stop:
                bot._trail_stop(bar)
            exit_reason = bot._check_exit(bar)
            if exit_reason:
                bot._close(price, i, bar_time, exit_reason)

        signal, details = bot.sig_gen.generate(df, i, bot.position)

        if not bot.position and signal in [Signal.BUY, Signal.SELL]:
            from .swing import find_swing_points

            swings = find_swing_points(df.head(i + 1), bot.swing_lb)
            bot._open(
                "LONG" if signal == Signal.BUY else "SHORT",
                price,
                i,
                bar_time,
                df,
                swings,
            )

        bot.equity.append(bot.pos_sizer.capital)
        results.append(
            {
                "datetime": bar_time,
                "close": price,
                "signal": signal.value,
                "trend": details.get("trend", "N/A"),
                "position": bot.position.direction if bot.position else "",
                "equity": bot.pos_sizer.capital,
            }
        )

        if callbacks and callbacks._on_bar:
            trend = str(details.get("trend", "N/A"))
            callbacks._on_bar(bar_time, symbol, price, signal, trend, bot.position)

        if speed > 0:
            time.sleep(1.0 / speed)

    results_df = pl.DataFrame(results)

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

    return bot, results_df


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

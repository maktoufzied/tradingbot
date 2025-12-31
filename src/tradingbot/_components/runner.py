import time
from datetime import datetime
from typing import TypedDict, Unpack

import polars as pl
from rich.console import Console
from rich.table import Table

from tradingbot.config import get_bot_config, get_provider_config, get_strategy_config
from tradingbot.types import PartialExitLevel, Position, Signal

from .bot import BacktestCallbacks, MarketStructureBot, Stats
from .execution import ExecutionModel
from .feeds import DataFeed


class BacktestParams(TypedDict, total=False):
    period: str
    interval: str
    capital: float
    risk: float
    rr: float
    swing_lb: int
    strategy: str
    preset: str
    refresh: bool
    verbose: bool
    speed: float
    # Execution cost parameters
    no_costs: bool
    slippage_bps: float
    spread_bps: float
    commission: float
    # Position sizing
    use_atr_sizing: bool
    # Trailing stops
    atr_trail: bool
    atr_trail_multiplier: float
    atr_trail_activation_r: float
    # Partial exits (None = use preset/config default)
    partial_exit_levels: tuple[PartialExitLevel, ...] | None


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
    period: str = "1y",
    interval: str = "1h",
    capital: float | None = None,
    risk: float | None = None,
    rr: float | None = None,
    swing_lb: int | None = None,
    strategy: str | None = None,
    preset: str | None = None,
    refresh: bool = False,
    verbose: bool = False,
    speed: float = 0,
    no_costs: bool = False,
    slippage_bps: float | None = None,
    spread_bps: float | None = None,
    commission: float | None = None,
    use_atr_sizing: bool = False,
    atr_trail: bool = False,
    atr_trail_multiplier: float | None = None,
    atr_trail_activation_r: float | None = None,
    partial_exit_levels: tuple[PartialExitLevel, ...] | None = None,
) -> tuple[MarketStructureBot, pl.DataFrame]:
    bot_cfg = get_bot_config()
    strategy_cfg = get_strategy_config()

    # Load preset if specified
    preset_obj = None
    if preset:
        from .presets import get_preset

        preset_obj = get_preset(preset)

    # Apply values: CLI args > preset > config defaults
    capital_val = capital if capital is not None else bot_cfg.capital
    risk_pct = risk if risk is not None else (preset_obj.risk_pct if preset_obj else strategy_cfg.risk_pct)
    rr_ratio = rr if rr is not None else (preset_obj.rr_ratio if preset_obj else strategy_cfg.rr_ratio)
    stop_pct = preset_obj.stop_pct if preset_obj else 0.01
    swing_lb_val = swing_lb if swing_lb is not None else strategy_cfg.swing_lb
    entry_strategy = strategy if strategy is not None else (preset_obj.entry if preset_obj else None)
    exit_strategy = preset_obj.exit if preset_obj else None
    allow_short = strategy_cfg.allow_short
    # Priority: CLI flag > preset > config
    use_atr = use_atr_sizing if use_atr_sizing else (preset_obj.atr_sizing if preset_obj else strategy_cfg.atr_sizing)
    # ATR trailing: CLI flag > preset > config
    use_atr_trail = atr_trail if atr_trail else (preset_obj.atr_trail if preset_obj else strategy_cfg.atr_trail)
    trail_multiplier = (
        atr_trail_multiplier
        if atr_trail_multiplier is not None
        else (preset_obj.atr_trail_multiplier if preset_obj else strategy_cfg.atr_trail_multiplier)
    )
    trail_activation = (
        atr_trail_activation_r
        if atr_trail_activation_r is not None
        else (preset_obj.atr_trail_activation_r if preset_obj else strategy_cfg.atr_trail_activation_r)
    )
    # Priority: CLI arg > preset > config (empty tuple = all-or-nothing)
    partial_levels = (
        partial_exit_levels
        if partial_exit_levels is not None
        else (preset_obj.partial_exit_levels if preset_obj else strategy_cfg.partial_exit_levels)
    )
    # EOD exit: preset > config (typically True for day trading presets)
    use_eod_exit = preset_obj.eod_exit if preset_obj else strategy_cfg.eod_exit
    eod_minutes = strategy_cfg.eod_exit_minutes_before

    # Build execution model: CLI args > provider config > defaults (zero)
    provider_cfg = get_provider_config()
    if no_costs:
        execution_model = ExecutionModel.zero()
    else:
        execution_model = ExecutionModel(
            slippage_bps=slippage_bps if slippage_bps is not None else provider_cfg.slippage_bps,
            spread_bps=spread_bps if spread_bps is not None else provider_cfg.spread_bps,
            commission_per_share=commission if commission is not None else provider_cfg.commission_per_share,
        )

    console.print()
    console.rule(f"[bold yellow]BACKTEST: {symbol}[/bold yellow]", style="cyan")

    df: pl.DataFrame = DataFeed.history(symbol, period=period, interval=interval, refresh=refresh)

    # Show config summary
    entry_name = entry_strategy or "swing_break"
    exit_name = exit_strategy or "swing"
    preset_info = f"[cyan]{preset}[/cyan] | " if preset else ""
    short_info = "long+short" if allow_short else "long only"
    total_bps = execution_model.slippage_bps + execution_model.spread_bps
    has_costs = total_bps > 0 or execution_model.commission_per_share > 0
    costs_info = (
        f"[dim]costs: {total_bps}bps + ${execution_model.commission_per_share}/sh[/dim]"
        if has_costs
        else "[dim]no costs[/dim]"
    )
    atr_info = "[cyan]ATR-sized[/cyan]" if use_atr else ""
    trail_info = (
        f"[cyan]ATR-trail ({trail_multiplier}× @ {trail_activation}R)[/cyan]"
        if use_atr_trail and trail_activation > 0
        else f"[cyan]ATR-trail ({trail_multiplier}×)[/cyan]"
        if use_atr_trail
        else ""
    )
    partial_info = f"[cyan]partial: {len(partial_levels)} levels[/cyan]" if partial_levels else ""
    console.print(
        f"  {preset_info}"
        f"[dim]{period} {interval}[/dim] | "
        f"[dim]{len(df)} bars[/dim] | "
        f"entry=[cyan]{entry_name}[/cyan] exit=[cyan]{exit_name}[/cyan] | "
        f"risk=[cyan]{risk_pct * 100:.1f}%[/cyan] rr=[cyan]{rr_ratio}:1[/cyan] | "
        f"[dim]{short_info}[/dim]"
        f"{' | ' + atr_info if atr_info else ''}"
        f"{' | ' + trail_info if trail_info else ''}"
        f"{' | ' + partial_info if partial_info else ''}"
    )
    console.print(f"  {costs_info}")
    if verbose and speed > 0:
        console.print(f"  [dim]Speed: {speed} bars/sec[/dim]")
    console.print()

    bot = MarketStructureBot(
        capital=capital_val,
        risk_pct=risk_pct,
        rr_ratio=rr_ratio,
        stop_pct=stop_pct,
        swing_lb=swing_lb_val,
        entry_strategy=entry_strategy,
        exit_strategy=exit_strategy,
        allow_short=allow_short,
        execution_model=execution_model,
        use_atr_sizing=use_atr,
        atr_trail=use_atr_trail,
        atr_trail_multiplier=trail_multiplier,
        atr_trail_activation_r=trail_activation,
        partial_exit_levels=partial_levels,
        eod_exit=use_eod_exit,
        eod_exit_minutes_before=eod_minutes,
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
            if bot.trailing_stop or bot.atr_trail:
                bot._trail_stop(bar)
            # Check for partial exits first (if configured)
            bot._process_partial_exits(bar, bar_time)
            # Then check for full exit
            exit_reason = bot._check_exit(bar)
            if exit_reason:
                bot._close(price, i, bar_time, exit_reason)

        signal, details = bot.sig_gen.generate(df, i, bool(bot.position))

        can_trade = signal == Signal.BUY or (signal == Signal.SELL and bot.allow_short)
        if not bot.position and can_trade:
            bot._open(
                "LONG" if signal == Signal.BUY else "SHORT",
                price,
                i,
                bar_time,
                df,
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
        trades_table.add_column("Date", justify="left")
        trades_table.add_column("Dir", justify="center")
        trades_table.add_column("Entry", justify="right")
        trades_table.add_column("Exit", justify="right")
        trades_table.add_column("P&L", justify="right")
        trades_table.add_column("Hold", justify="right")
        trades_table.add_column("Reason", justify="center")

        # Short labels for exit reasons
        exit_labels = {
            "STOP_LOSS": "[red]SL[/red]",
            "TAKE_PROFIT": "[green]TP[/green]",
            "EOD_EXIT": "[yellow]EOD[/yellow]",
            "PARTIAL_EXIT": "[cyan]PART[/cyan]",
            "TIME_EXIT": "[dim]TIME[/dim]",
        }

        for t in bot.trades[-10:]:
            pnl_style = "green" if t.pnl > 0 else "red"
            reason = exit_labels.get(t.exit_reason, t.exit_reason)

            trades_table.add_row(
                t.entry_time.strftime("%Y-%m-%d"),
                t.direction[:1],  # L or S
                f"${t.entry_price:.2f}",
                f"${t.exit_price:.2f}",
                f"[{pnl_style}]${t.pnl:+,.2f}[/{pnl_style}]",
                f"{t.holding_period}",  # bars
                reason,
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

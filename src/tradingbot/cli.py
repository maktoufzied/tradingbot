"""CLI entry point and callbacks for the trading engine."""

import asyncio
import contextlib

from rich.console import Console

from tradingbot import (
    BarEvent,
    EngineCallbacks,
    EngineStartedEvent,
    EngineStoppedEvent,
    LiveRiskManager,
    MessageEvent,
    MessageLevel,
    PositionSizer,
    SignalEvent,
    SignalGenerator,
    StatsUpdatedEvent,
    TradeClosedEvent,
    TradingEngine,
    TradingTUI,
    get_broker_registry,
    get_feed_registry,
)
from tradingbot.config import get_bot_config, get_engine_config
from tradingbot.interfaces import BrokerProtocol, DataFeedProtocol

console = Console()


def make_cli_callbacks() -> EngineCallbacks:
    """Create callbacks for CLI output."""
    callbacks = EngineCallbacks()

    @callbacks.on_started
    def on_started(event: EngineStartedEvent) -> None:
        engine_cfg = get_engine_config()
        console.print()
        console.rule("[bold green]TRADING ENGINE[/bold green]")
        console.print(f"Symbols: [cyan]{', '.join(event.symbols)}[/cyan]")
        console.print(f"Broker: [cyan]{event.broker_name}[/cyan]")
        console.print(f"Feed: [cyan]{event.feed_name}[/cyan]")
        console.print(f"Dry run: [yellow]{event.dry_run}[/yellow]")
        console.print()
        console.print("[bold]Risk Controls:[/bold]")
        console.print(f"  Max daily loss: [cyan]{engine_cfg.risk.max_daily_loss_pct:.1%}[/cyan]")
        console.print(f"  Circuit breaker: [cyan]{engine_cfg.risk.circuit_breaker_loss_pct:.1%}[/cyan]")
        console.print(f"  Max positions: [cyan]{engine_cfg.risk.max_open_positions}[/cyan]")
        console.print(f"  Max position size: [cyan]{engine_cfg.risk.max_position_size_pct:.1%}[/cyan]")
        console.print(f"  Trading hours only: [cyan]{engine_cfg.risk.trading_hours_only}[/cyan]")
        console.print()

    @callbacks.on_stopped
    def on_stopped(event: EngineStoppedEvent) -> None:
        risk = event.risk_manager
        console.print()
        console.rule("[bold]SESSION SUMMARY[/bold]")

        if risk.session_trades == 0:
            console.print("[dim]No trades executed during this session[/dim]")
            return

        pnl_color = "green" if risk.session_pnl >= 0 else "red"
        console.print()
        console.print("[bold]Performance[/bold]")
        console.print(f"  Total Trades:    {risk.session_trades}")
        console.print(f"  Winners:         {risk.session_winners}")
        console.print(f"  Losers:          {risk.session_losers}")
        console.print(f"  Win Rate:        {risk.session_win_rate:.1%}")
        console.print()
        console.print(f"  Total P&L:       [{pnl_color}]${risk.session_pnl:+,.2f}[/{pnl_color}]")
        console.print(f"  Total Return:    [{pnl_color}]{risk.session_return_pct:+.2%}[/{pnl_color}]")
        console.print(f"  Profit Factor:   {risk.session_profit_factor:.2f}")
        console.print()
        console.print(f"  Starting Equity: ${risk._initial_equity:,.2f}")
        console.print(f"  Final Equity:    [{pnl_color}]${risk.final_equity:,.2f}[/{pnl_color}]")
        console.print()

    @callbacks.on_message
    def on_message(event: MessageEvent) -> None:
        style_map = {
            MessageLevel.INFO: "",
            MessageLevel.SUCCESS: "green",
            MessageLevel.WARNING: "yellow",
            MessageLevel.ERROR: "red",
            MessageLevel.DEBUG: "dim",
        }
        style = style_map.get(event.level, "")
        if style:
            console.print(f"[{style}]{event.message}[/{style}]")
        else:
            console.print(event.message)

    @callbacks.on_bar
    def on_bar(event: BarEvent) -> None:
        pos_str = f"[{event.position.direction}]" if event.position else ""
        signal_color = {"BUY": "green", "SELL": "red", "HOLD": "dim"}.get(event.signal.value, "white")
        console.print(
            f"[dim]{event.bar.datetime.strftime('%Y-%m-%d %H:%M')}[/dim] "
            f"{event.bar.symbol} ${event.bar.close:.2f} "
            f"[{signal_color}]{event.signal.value}[/{signal_color}] "
            f"[dim]{event.trend}[/dim] {pos_str}"
        )

    @callbacks.on_signal
    def on_signal(event: SignalEvent) -> None:
        console.print()
        emoji = "🔼" if event.direction == "LONG" else "🔽"
        console.print(f"[bold cyan]{emoji} {event.direction} SIGNAL: {event.symbol}[/bold cyan]")
        console.print(
            f"  Entry: ${event.entry:.2f}  Stop: ${event.stop:.2f}  TP: ${event.tp:.2f}  Size: {event.size:.2f}"
        )
        if event.was_capped:
            console.print("  [yellow]⚠ Size capped to max position limit[/yellow]")
        if event.blocked:
            console.print(f"  [red]✗ BLOCKED: {event.reason}[/red]")
        elif event.reason:
            console.print(f"  [yellow]⚠ Would be blocked: {event.reason}[/yellow]")

    @callbacks.on_trade_closed
    def on_trade_closed(event: TradeClosedEvent) -> None:
        console.print()
        emoji = "🛑" if event.reason == "STOP_LOSS" else "✅"
        console.print(f"[bold]{emoji} EXIT {event.symbol}: {event.reason}[/bold]")
        console.print(f"  Entry: ${event.entry:.2f}  Exit: ${event.exit_price:.2f}")
        color = "green" if event.pnl > 0 else "red"
        console.print(f"  P&L: [{color}]${event.pnl:+,.2f}[/{color}]")

    return callbacks


async def run_live(
    symbols: list[str],
    broker: BrokerProtocol,
    feed: DataFeedProtocol,
    signal_generator: SignalGenerator,
    position_sizer: PositionSizer,
    live_risk_manager: LiveRiskManager,
    rr_ratio: float = 2.0,
    dry_run: bool = False,
    allow_short: bool = False,
    callbacks: EngineCallbacks | None = None,
) -> None:
    """Run trading engine."""
    engine = TradingEngine(
        symbols=symbols,
        broker=broker,
        feed=feed,
        signal_generator=signal_generator,
        position_sizer=position_sizer,
        live_risk_manager=live_risk_manager,
        rr_ratio=rr_ratio,
        dry_run=dry_run,
        allow_short=allow_short,
        callbacks=callbacks,
    )

    try:
        await engine.start()
        while engine._feed.is_connected:
            await asyncio.sleep(0.1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await engine.stop()


def _run_with_tui(
    symbols: list[str],
    broker: BrokerProtocol,
    feed: DataFeedProtocol,
    signal_generator: SignalGenerator,
    position_sizer: PositionSizer,
    live_risk_manager: LiveRiskManager,
    rr_ratio: float,
    dry_run: bool,
    allow_short: bool,
) -> None:
    """Run live trading with TUI."""

    def make_tui_callbacks(tui: TradingTUI) -> EngineCallbacks:
        """Create callbacks that route to TUI."""
        callbacks = EngineCallbacks()

        level_to_style = {
            MessageLevel.INFO: "",
            MessageLevel.SUCCESS: "green",
            MessageLevel.WARNING: "yellow",
            MessageLevel.ERROR: "red",
            MessageLevel.DEBUG: "dim",
        }

        @callbacks.on_started
        def on_started(event: EngineStartedEvent) -> None:
            tui.log_message(f"Starting: {', '.join(event.symbols)}", "bold")
            tui.log_message(f"Broker: {event.broker_name}, Feed: {event.feed_name}")

        @callbacks.on_message
        def on_message(event: MessageEvent) -> None:
            tui.log_message(event.message, level_to_style.get(event.level, ""))

        @callbacks.on_bar
        def on_bar(event: BarEvent) -> None:
            tui.log_bar(event.bar, event.signal, event.trend, event.position)

        @callbacks.on_signal
        def on_signal(event: SignalEvent) -> None:
            tui.log_signal(
                event.direction,
                event.symbol,
                event.entry,
                event.stop,
                event.tp,
                event.size,
                event.blocked,
                event.reason,
                event.was_capped,
            )

        @callbacks.on_trade_closed
        def on_trade_closed(event: TradeClosedEvent) -> None:
            tui.log_trade_close(event.direction, event.symbol, event.entry, event.exit_price, event.pnl, event.reason)

        @callbacks.on_stats_updated
        def on_stats_updated(event: StatsUpdatedEvent) -> None:
            tui.update_session_stats(event.pnl, event.trades, event.winners, event.losers)

        return callbacks

    class TradingApp(TradingTUI):
        """TUI app with trading engine worker."""

        def __init__(self) -> None:
            super().__init__(broker=broker, symbols=symbols)
            # Set raw bar callback early so backfill progress is visible
            with contextlib.suppress(NotImplementedError):
                feed.set_raw_bar_callback(self.update_aggregation)

        def on_mount(self) -> None:
            """Start trading engine when app mounts."""
            super().on_mount()
            self.run_worker(self._run_engine, exclusive=True)  # type: ignore[arg-type]

        async def _run_engine(self) -> None:
            """Run the trading engine."""
            await run_live(
                symbols=symbols,
                broker=broker,
                feed=feed,
                signal_generator=signal_generator,
                position_sizer=position_sizer,
                live_risk_manager=live_risk_manager,
                rr_ratio=rr_ratio,
                dry_run=dry_run,
                allow_short=allow_short,
                callbacks=make_tui_callbacks(self),
            )

    app = TradingApp()
    app.run()


def main() -> None:
    """CLI entry point for live trading."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run live trading bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  tradingbot-live AAPL
  tradingbot-live AAPL QQQ --dry-run
  tradingbot-live AAPL --tui
        """,
    )

    parser.add_argument("symbols", nargs="+", help="Symbols to trade (e.g., MSFT AAPL)")
    parser.add_argument("--dry-run", action="store_true", help="Log signals without executing trades")
    parser.add_argument("--tui", action="store_true", help="Run with terminal UI")
    args = parser.parse_args()

    symbols: list[str] = []
    for sym in args.symbols:
        symbols.extend(s.strip().upper() for s in sym.split(",") if s.strip())

    cfg = get_bot_config()
    engine_cfg = get_engine_config()

    broker = get_broker_registry().get(engine_cfg.broker)
    signal_generator = SignalGenerator(cfg.swing_lb)
    position_sizer = PositionSizer(cfg.capital, cfg.risk_pct)
    live_risk_manager = LiveRiskManager(engine_cfg.risk, cfg.capital)

    feed = get_feed_registry().get(engine_cfg.feed)

    if args.tui:
        _run_with_tui(
            symbols=symbols,
            broker=broker,
            feed=feed,
            signal_generator=signal_generator,
            position_sizer=position_sizer,
            live_risk_manager=live_risk_manager,
            rr_ratio=cfg.rr_ratio,
            dry_run=args.dry_run,
            allow_short=cfg.allow_short,
        )
    else:
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(
                run_live(
                    symbols=symbols,
                    broker=broker,
                    feed=feed,
                    signal_generator=signal_generator,
                    position_sizer=position_sizer,
                    live_risk_manager=live_risk_manager,
                    rr_ratio=cfg.rr_ratio,
                    dry_run=args.dry_run,
                    allow_short=cfg.allow_short,
                    callbacks=make_cli_callbacks(),
                )
            )

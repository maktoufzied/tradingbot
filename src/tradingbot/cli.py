"""CLI entry point and callbacks for the trading engine."""

import asyncio
import contextlib
import threading
from datetime import datetime, timedelta

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

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
    TradeClosedEvent,
    TradingEngine,
    get_broker_registry,
    get_feed_registry,
)
from tradingbot._components.hub import EngineAdapter, EventHub, HubServer
from tradingbot._components.logging import get_logger
from tradingbot.config import get_bot_config, get_engine_config, get_strategy_config
from tradingbot.interfaces import BrokerProtocol, DataFeedProtocol

console = Console()
logger = get_logger(__name__)


def update_cache_for_replay(symbols: list[str], days: int) -> None:
    """Update cache with latest data before replay."""
    from tradingbot._components.cache.db import get_date_range, insert_bars

    engine_cfg = get_engine_config()
    # Derive feed from provider: alpaca -> alpaca, paper -> yahoo
    feed_name = "alpaca" if engine_cfg.provider == "alpaca" else "yahoo"
    feed = get_feed_registry().get(feed_name)
    interval = engine_cfg.bar_interval  # Use same interval as replay

    # Use local time for date range - users think in terms of local dates
    # (e.g., "14 days ago" from Dec 24 local should be Dec 10, not Dec 11 if it's already Dec 25 UTC)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for symbol in symbols:
            task = progress.add_task(f"[cyan]{symbol}[/cyan] checking cache...", total=None)

            # Check what we have cached
            cached_start, cached_end = get_date_range(symbol, interval)

            need_fetch = False
            if cached_start is None or cached_end is None:
                need_fetch = True
                progress.update(task, description=f"[cyan]{symbol}[/cyan] fetching {days} days...")
            elif cached_start > start_date or cached_end < end_date - timedelta(hours=1):
                need_fetch = True
                progress.update(task, description=f"[cyan]{symbol}[/cyan] updating cache...")

            if need_fetch:
                try:
                    df = feed.history(
                        symbol,
                        start_date=start_date.strftime("%Y-%m-%d"),
                        end_date=end_date.strftime("%Y-%m-%d"),
                        interval=interval,
                    )
                    if not df.is_empty():
                        insert_bars(df, symbol, interval, feed_name)
                        progress.update(task, description=f"[green]{symbol}[/green] cached {len(df)} bars")
                    else:
                        progress.update(task, description=f"[yellow]{symbol}[/yellow] no data")
                except Exception as e:
                    progress.update(task, description=f"[red]{symbol}[/red] error: {e}")
            else:
                progress.update(task, description=f"[green]{symbol}[/green] cache up to date")

            progress.remove_task(task)

    console.print()


def make_cli_callbacks() -> EngineCallbacks:
    """Create callbacks for CLI output."""
    callbacks = EngineCallbacks()

    @callbacks.on_started
    def on_started(event: EngineStartedEvent) -> None:
        engine_cfg = get_engine_config()

        # Structured logging
        logger.info(
            "engine_started",
            symbols=event.symbols,
            broker=event.broker_name,
            feed=event.feed_name,
            dry_run=event.dry_run,
            max_daily_loss_pct=engine_cfg.risk.max_daily_loss_pct,
            max_positions=engine_cfg.risk.max_open_positions,
        )

        # Console output for user
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

        # Structured logging
        logger.info(
            "engine_stopped",
            trades=risk.session_trades,
            winners=risk.session_winners,
            losers=risk.session_losers,
            win_rate=risk.session_win_rate,
            pnl=risk.session_pnl,
            return_pct=risk.session_return_pct,
            profit_factor=risk.session_profit_factor,
            final_equity=risk.final_equity,
        )

        # Console output for user
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
        # Structured logging based on level
        log_method = {
            MessageLevel.INFO: logger.info,
            MessageLevel.SUCCESS: logger.info,
            MessageLevel.WARNING: logger.warning,
            MessageLevel.ERROR: logger.error,
            MessageLevel.DEBUG: logger.debug,
        }.get(event.level, logger.info)
        log_method("engine_message", message=event.message, level=event.level.value)

        # Console output for user
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
        # Structured logging
        logger.info(
            "signal_generated",
            symbol=event.symbol,
            direction=event.direction,
            entry=event.entry,
            stop=event.stop,
            tp=event.tp,
            size=event.size,
            blocked=event.blocked,
            reason=event.reason,
            was_capped=event.was_capped,
        )

        # Console output for user
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
        # Structured logging
        logger.info(
            "trade_closed",
            symbol=event.symbol,
            reason=event.reason,
            entry=event.entry,
            exit_price=event.exit_price,
            pnl=event.pnl,
        )

        # Console output for user
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


def _run_with_modern_tui(
    symbols: list[str],
    broker: BrokerProtocol,
    feed: DataFeedProtocol,
    signal_generator: SignalGenerator,
    position_sizer: PositionSizer,
    live_risk_manager: LiveRiskManager,
    rr_ratio: float,
    dry_run: bool,
    allow_short: bool,
    ws_port: int = 8765,
    enable_ws: bool = True,
    serve_web: bool = False,
    web_port: int | None = None,
    preset_name: str = "custom",
    entry_strategy: str = "swing_break",
    exit_strategy: str = "swing",
    risk_pct: float = 0.01,
    indicators: list[str] | None = None,
    is_replay: bool = False,
) -> None:
    """Run live trading with modern hub-based TUI.

    This uses the new event-driven architecture with:
    - EventHub for state management and callbacks
    - EngineAdapter for event transformation
    - WebSocket server for remote clients
    - Modern TradingApp with multi-stock grid
    """
    from tradingbot._components.hub.logging import setup_logging
    from tradingbot._components.hub.types import StrategyInfo
    from tradingbot._components.tui.app import TradingApp as ModernTradingApp

    # Create the event hub
    hub = EventHub()

    # Setup logging to file and hub
    setup_logging(hub)

    # Set strategy info
    strategy_info = StrategyInfo(
        preset_name=preset_name,
        entry_strategy=entry_strategy,
        exit_strategy=exit_strategy,
        risk_pct=risk_pct,
        rr_ratio=rr_ratio,
        indicators=indicators or [],
    )
    hub.set_strategy(strategy_info)

    # Wire feed connection status to hub (if feed supports it)
    if hasattr(feed, "set_connection_callback"):
        from tradingbot._components.resilience import ConnectionStatus

        def on_feed_connection_change(status: ConnectionStatus) -> None:
            hub.update_connection_status_sync(
                component=status.component,
                state=status.state,
                retry_count=status.retry_count,
                error=status.last_error,
            )

        feed.set_connection_callback(on_feed_connection_change)

    # Create adapter that transforms engine events to hub updates
    provider_name = broker.name.title()  # "alpaca" -> "Alpaca", "paper" -> "Paper"
    adapter = EngineAdapter(hub, symbols, is_replay=is_replay, provider=provider_name)

    class ModernTUIApp(ModernTradingApp):
        """Modern TUI app with integrated trading engine."""

        def __init__(self) -> None:
            super().__init__(hub, symbols, title="TRADINGBOT")
            self._ws_server: HubServer | None = None

        def on_mount(self) -> None:
            """Start trading engine on mount."""
            super().on_mount()
            # Start trading engine (WS server is started before TUI)
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
                callbacks=adapter.callbacks,
            )

    # Start WebSocket server in background thread (needs its own event loop)
    ws_server: HubServer | None = None
    ws_loop: asyncio.AbstractEventLoop | None = None
    ws_thread: threading.Thread | None = None

    if enable_ws:
        import asyncio

        def run_ws_server() -> None:
            nonlocal ws_server, ws_loop
            ws_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(ws_loop)

            async def start_and_run() -> None:
                nonlocal ws_server
                ws_server = HubServer(hub, port=ws_port, serve_web=serve_web, web_port=web_port)
                await ws_server.start()
                # Keep running until cancelled
                try:
                    await asyncio.Future()  # Run forever
                except asyncio.CancelledError:
                    await ws_server.stop()

            with contextlib.suppress(Exception):
                ws_loop.run_until_complete(start_and_run())

        ws_thread = threading.Thread(target=run_ws_server, daemon=True)
        ws_thread.start()

        # Wait for server to start
        import time

        for _ in range(50):  # Wait up to 5 seconds
            time.sleep(0.1)
            if ws_server and ws_server.is_running:
                break

        if ws_server and ws_server.is_running:
            print(f"\n📡 WebSocket server: ws://127.0.0.1:{ws_port}")
            if ws_server.web_url:
                print(f"🌐 Web interface: {ws_server.web_url}")
            print()
        else:
            print("\n⚠️  WebSocket server failed to start\n")

    app = ModernTUIApp()
    app.run()

    # Cleanup after TUI exits
    if ws_loop:
        ws_loop.call_soon_threadsafe(ws_loop.stop)


def _run_headless_with_hub(
    symbols: list[str],
    broker: BrokerProtocol,
    feed: DataFeedProtocol,
    signal_generator: SignalGenerator,
    position_sizer: PositionSizer,
    live_risk_manager: LiveRiskManager,
    rr_ratio: float,
    dry_run: bool,
    allow_short: bool,
    ws_port: int = 8765,
    serve_web: bool = False,
    web_port: int | None = None,
    preset_name: str = "custom",
    entry_strategy: str = "swing_break",
    exit_strategy: str = "swing",
    risk_pct: float = 0.01,
    indicators: list[str] | None = None,
    is_replay: bool = False,
) -> None:
    """Run headless with hub-based architecture (WebSocket + optional web UI).

    This mode runs without a terminal UI but provides:
    - WebSocket server for remote clients
    - Optional HTTP server for web interface
    - Console output for monitoring
    """
    import contextlib

    from tradingbot._components.hub.logging import setup_logging
    from tradingbot._components.hub.types import StrategyInfo

    # Create the event hub
    hub = EventHub()

    # Setup logging to file and hub
    setup_logging(hub)

    # Set strategy info
    strategy_info = StrategyInfo(
        preset_name=preset_name,
        entry_strategy=entry_strategy,
        exit_strategy=exit_strategy,
        risk_pct=risk_pct,
        rr_ratio=rr_ratio,
        indicators=indicators or [],
    )
    hub.set_strategy(strategy_info)

    # Wire feed connection status to hub (if feed supports it)
    if hasattr(feed, "set_connection_callback"):
        from tradingbot._components.resilience import ConnectionStatus

        def on_feed_connection_change(status: ConnectionStatus) -> None:
            hub.update_connection_status_sync(
                component=status.component,
                state=status.state,
                retry_count=status.retry_count,
                error=status.last_error,
            )

        feed.set_connection_callback(on_feed_connection_change)

    # Create adapter that transforms engine events to hub updates
    provider_name = broker.name.title()  # "alpaca" -> "Alpaca", "paper" -> "Paper"
    adapter = EngineAdapter(hub, symbols, is_replay=is_replay, provider=provider_name)

    async def run_with_server() -> None:
        # Start WebSocket server (and optionally web server)
        server = HubServer(hub, port=ws_port, serve_web=serve_web, web_port=web_port)
        await server.start()

        print(f"\nWebSocket server: ws://127.0.0.1:{ws_port}")
        if server.web_url:
            print(f"Web interface:    {server.web_url}")
        print()

        try:
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
                callbacks=adapter.callbacks,
            )
        finally:
            await server.stop()

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run_with_server())


def main() -> None:
    """CLI entry point for live trading."""
    import argparse

    from tradingbot._components.logging import configure_logging
    from tradingbot._components.presets import get_preset
    from tradingbot.config import get_logging_config

    # Initialize structured logging from config
    log_cfg = get_logging_config()
    configure_logging(
        level=log_cfg.level,
        log_format=log_cfg.format,  # type: ignore[arg-type]
        log_file=log_cfg.log_file,
        enable_colors=log_cfg.colors,
    )

    parser = argparse.ArgumentParser(
        description="Run live trading bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  tradingbot-live AAPL
  tradingbot-live AAPL QQQ --dry-run
  tradingbot-live AAPL --tui
  tradingbot-live AAPL -p conservative --tui
  tradingbot-live AAPL --atr-sizing       # Volatility-adjusted sizing
        """,
    )

    parser.add_argument("symbols", nargs="+", help="Symbols to trade (e.g., MSFT AAPL)")
    parser.add_argument("--preset", "-p", help="Use a preset (overrides strategy, risk, indicators)")
    parser.add_argument(
        "--strategy", "-s", help="Entry strategy: swing_break, vwap_reversion, orb, rsi_divergence, atr_breakout"
    )
    parser.add_argument("--risk", type=float, help="Risk per trade as decimal (e.g., 0.01 for 1%%)")
    parser.add_argument("--rr", type=float, help="Reward/risk ratio (e.g., 2.0)")
    parser.add_argument("--dry-run", action="store_true", help="Log signals without executing trades")
    parser.add_argument("--replay", action="store_true", help="Use historical data replay instead of live feed")
    parser.add_argument(
        "--replay-speed", type=float, default=0.5, help="Seconds between bars in replay mode (default: 0.5)"
    )
    parser.add_argument("--replay-days", type=int, default=5, help="Days of historical data to replay (default: 5)")
    parser.add_argument("--tui", action="store_true", help="Run with terminal UI")
    parser.add_argument("--ws-port", type=int, default=8765, help="WebSocket server port (default: 8765)")
    parser.add_argument("--no-ws", action="store_true", help="Disable WebSocket server")
    parser.add_argument("--web", action="store_true", help="Serve web interface (on ws-port - 1)")
    parser.add_argument("--web-port", type=int, help="Web interface port (default: ws-port - 1)")
    parser.add_argument(
        "--atr-sizing",
        action="store_true",
        help="Enable ATR-based volatility-adjusted position sizing",
    )
    parser.add_argument(
        "--partial-exits",
        action="store_true",
        help="Enable partial profit taking (backtest mode via preset/config)",
    )
    args = parser.parse_args()

    symbols: list[str] = []
    for sym in args.symbols:
        symbols.extend(s.strip().upper() for s in sym.split(",") if s.strip())

    bot_cfg = get_bot_config()
    strategy_cfg = get_strategy_config()
    engine_cfg = get_engine_config()

    # Load preset if specified
    preset = None
    if args.preset:
        preset = get_preset(args.preset)

    # Apply values: CLI args > preset > config defaults
    risk_pct = args.risk if args.risk is not None else (preset.risk_pct if preset else strategy_cfg.risk_pct)
    rr_ratio = args.rr if args.rr is not None else (preset.rr_ratio if preset else strategy_cfg.rr_ratio)
    entry_strategy = args.strategy if args.strategy is not None else (preset.entry if preset else strategy_cfg.entry)
    exit_strategy = preset.exit if preset else strategy_cfg.exit
    indicators = preset.indicators if preset else []
    preset_name = preset.name if preset else "custom"

    # Use config if --atr-sizing not explicitly passed
    use_atr = args.atr_sizing if args.atr_sizing else strategy_cfg.atr_sizing

    signal_generator = SignalGenerator(strategy_cfg.swing_lb, entry_strategy=entry_strategy)
    position_sizer = PositionSizer(bot_cfg.capital, risk_pct, use_atr_sizing=use_atr)

    # For replay mode, disable trading hours restriction since we're replaying historical data
    risk_config = engine_cfg.risk
    if args.replay:
        from dataclasses import replace

        risk_config = replace(risk_config, trading_hours_only=False)

    live_risk_manager = LiveRiskManager(risk_config, bot_cfg.capital)

    # Use replay feed and paper broker if --replay specified
    feed: DataFeedProtocol
    broker: BrokerProtocol
    if args.replay:
        from tradingbot._components.brokers.plugins.paper import PaperBroker
        from tradingbot._components.feeds.plugins.replay import ReplayFeed

        # Update cache before replay
        console.print("[bold]Updating cache for replay...[/bold]")
        update_cache_for_replay(symbols, args.replay_days)

        feed = ReplayFeed(delay=args.replay_speed, days=args.replay_days)
        broker = PaperBroker(initial_capital=bot_cfg.capital)
        # PaperBroker is safe (simulated) so we don't need dry_run
        # dry_run would prevent orders from reaching the broker, breaking account tracking
    else:
        # Derive feed/broker from provider
        feed_name = "alpaca" if engine_cfg.provider == "alpaca" else "yahoo"
        feed = get_feed_registry().get(feed_name)
        broker = get_broker_registry().get(engine_cfg.provider)

    if args.tui:
        # Modern TUI with hub-based architecture
        _run_with_modern_tui(
            symbols=symbols,
            broker=broker,
            feed=feed,
            signal_generator=signal_generator,
            position_sizer=position_sizer,
            live_risk_manager=live_risk_manager,
            rr_ratio=rr_ratio,
            dry_run=args.dry_run,
            allow_short=strategy_cfg.allow_short,
            ws_port=args.ws_port,
            enable_ws=not args.no_ws,
            serve_web=args.web,
            web_port=args.web_port,
            preset_name=preset_name,
            entry_strategy=entry_strategy,
            exit_strategy=exit_strategy,
            risk_pct=risk_pct,
            indicators=indicators,
            is_replay=args.replay,
        )
    elif args.web:
        # Headless mode with web interface (includes WebSocket server)
        _run_headless_with_hub(
            symbols=symbols,
            broker=broker,
            feed=feed,
            signal_generator=signal_generator,
            position_sizer=position_sizer,
            live_risk_manager=live_risk_manager,
            rr_ratio=rr_ratio,
            dry_run=args.dry_run,
            allow_short=strategy_cfg.allow_short,
            ws_port=args.ws_port,
            serve_web=args.web,
            web_port=args.web_port,
            preset_name=preset_name,
            entry_strategy=entry_strategy,
            exit_strategy=exit_strategy,
            risk_pct=risk_pct,
            indicators=indicators,
            is_replay=args.replay,
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
                    rr_ratio=rr_ratio,
                    dry_run=args.dry_run,
                    allow_short=strategy_cfg.allow_short,
                    callbacks=make_cli_callbacks(),
                )
            )

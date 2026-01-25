"""CLI entry point and callbacks for the trading engine."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

if TYPE_CHECKING:
    from tradingbot._components.hub.types import SymbolStrategyConfig

from tradingbot import (
    BarEvent,
    EngineCallbacks,
    EngineStartedEvent,
    EngineStoppedEvent,
    MessageEvent,
    MessageLevel,
    PositionSizer,
    RiskManager,
    SignalEvent,
    SignalGenerator,
    TradeClosedEvent,
    TradingEngine,
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
    """Create callbacks for CLI output.

    Each callback uses dual output:
    - Structured logging for file/aggregation (machine-parseable JSON in production)
    - Rich console output for interactive user feedback (human-readable)
    """
    callbacks = EngineCallbacks()

    @callbacks.on_started
    def on_started(event: EngineStartedEvent) -> None:
        engine_cfg = get_engine_config()

        logger.info(
            "Engine started: symbols=%s broker=%s feed=%s dry_run=%s max_loss=%.1f%% max_positions=%d",
            event.symbols,
            event.broker_name,
            event.feed_name,
            event.dry_run,
            engine_cfg.risk.max_daily_loss_pct * 100,
            engine_cfg.risk.max_open_positions,
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

        logger.info(
            "Engine stopped: trades=%d win=%d loss=%d win_rate=%.1f%% pnl=$%.2f return=%.2f%% pf=%.2f equity=$%.2f",
            risk.session_trades,
            risk.session_winners,
            risk.session_losers,
            risk.session_win_rate * 100,
            risk.session_pnl,
            risk.session_return_pct * 100,
            risk.session_profit_factor,
            risk.final_equity,
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
        # Log based on level
        log_method = {
            MessageLevel.INFO: logger.info,
            MessageLevel.SUCCESS: logger.info,
            MessageLevel.WARNING: logger.warning,
            MessageLevel.ERROR: logger.error,
            MessageLevel.DEBUG: logger.debug,
        }.get(event.level, logger.info)
        log_method("[%s] %s", event.level.value, event.message)

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
        logger.info(
            "Signal: %s %s entry=$%.2f stop=$%.2f tp=$%.2f size=%.2f blocked=%s reason=%s capped=%s",
            event.direction,
            event.symbol,
            event.entry,
            event.stop,
            event.tp,
            event.size,
            event.blocked,
            event.reason or "N/A",
            event.was_capped,
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
        logger.info(
            "Trade closed: %s reason=%s entry=$%.2f exit=$%.2f pnl=$%.2f",
            event.symbol,
            event.reason,
            event.entry,
            event.exit_price,
            event.pnl,
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
    signal_generators: dict[str, SignalGenerator],
    position_sizers: dict[str, PositionSizer],
    risk_manager: RiskManager,
    rr_ratio: float = 2.0,
    dry_run: bool = False,
    allow_short: bool = False,
    callbacks: EngineCallbacks | None = None,
    strategy_names: dict[str, str] | None = None,
    on_engine_ready: Callable[[TradingEngine], None] | None = None,
) -> None:
    """Run trading engine."""
    engine = TradingEngine(
        symbols=symbols,
        broker=broker,
        feed=feed,
        signal_generators=signal_generators,
        position_sizers=position_sizers,
        risk_manager=risk_manager,
        rr_ratio=rr_ratio,
        dry_run=dry_run,
        allow_short=allow_short,
        callbacks=callbacks,
        strategy_names=strategy_names,
    )

    # Notify caller that engine is ready (for command handler setup)
    if on_engine_ready:
        on_engine_ready(engine)

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
    signal_generators: dict[str, SignalGenerator],
    position_sizers: dict[str, PositionSizer],
    risk_manager: RiskManager,
    rr_ratio: float,
    dry_run: bool,
    allow_short: bool,
    ws_port: int = 8765,
    enable_ws: bool = True,
    serve_web: bool = False,
    web_port: int | None = None,
    preset_name: str = "custom",
    strategy_names: dict[str, str] | None = None,
    risk_pct: float = 0.01,
    indicators: list[str] | None = None,
    is_replay: bool = False,
    symbol_configs: dict[str, SymbolStrategyConfig] | None = None,
) -> None:
    """Run live trading with modern hub-based TUI.

    This uses the new event-driven architecture with:
    - EventHub for state management and callbacks
    - EngineAdapter for event transformation
    - WebSocket server for remote clients
    - Modern TradingApp with multi-stock grid
    """
    from tradingbot._components.hub.types import StrategyInfo
    from tradingbot._components.tui.app import TradingApp as ModernTradingApp

    strategy_names = strategy_names or {}
    symbol_configs = symbol_configs or {}

    # Create the event hub
    hub = EventHub()

    # Set strategy info (use first symbol's strategy for display, or "multi-strategy")
    first_symbol = symbols[0] if symbols else ""
    first_sig_gen = signal_generators.get(first_symbol)
    strategy_info = StrategyInfo(
        preset_name=preset_name,
        entry_strategy=first_sig_gen.entry_name if first_sig_gen else "swing_break",
        exit_strategy=first_sig_gen.exit_name if first_sig_gen else "swing",
        risk_pct=risk_pct,
        rr_ratio=rr_ratio,
        indicators=indicators or [],
        symbol_strategies=strategy_names,
        symbol_configs=symbol_configs,
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

    # Engine reference for command handling
    engine_ref: list[TradingEngine | None] = [None]

    def on_engine_ready(engine: TradingEngine) -> None:
        engine_ref[0] = engine

    async def handle_command(command: str, params: dict[str, Any]) -> bool:
        """Handle UI commands like close_position."""
        if command == "close_position":
            symbol = params.get("symbol")
            if not isinstance(symbol, str) or not symbol or engine_ref[0] is None:
                return False
            return await engine_ref[0].close_position_manually(symbol)
        return False

    hub.set_command_handler(handle_command)

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
                signal_generators=signal_generators,
                position_sizers=position_sizers,
                risk_manager=risk_manager,
                rr_ratio=rr_ratio,
                dry_run=dry_run,
                allow_short=allow_short,
                callbacks=adapter.callbacks,
                strategy_names=strategy_names,
                on_engine_ready=on_engine_ready,
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
    signal_generators: dict[str, SignalGenerator],
    position_sizers: dict[str, PositionSizer],
    risk_manager: RiskManager,
    rr_ratio: float,
    dry_run: bool,
    allow_short: bool,
    ws_port: int = 8765,
    serve_web: bool = False,
    web_port: int | None = None,
    preset_name: str = "custom",
    strategy_names: dict[str, str] | None = None,
    risk_pct: float = 0.01,
    indicators: list[str] | None = None,
    is_replay: bool = False,
    symbol_configs: dict[str, SymbolStrategyConfig] | None = None,
) -> None:
    """Run headless with hub-based architecture (WebSocket + optional web UI).

    This mode runs without a terminal UI but provides:
    - WebSocket server for remote clients
    - Optional HTTP server for web interface
    - Console output for monitoring
    """
    import contextlib

    from tradingbot._components.hub.types import StrategyInfo

    strategy_names = strategy_names or {}
    symbol_configs = symbol_configs or {}

    # Create the event hub
    hub = EventHub()

    # Set strategy info (use first symbol's strategy for display, or "multi-strategy")
    first_symbol = symbols[0] if symbols else ""
    first_sig_gen = signal_generators.get(first_symbol)
    strategy_info = StrategyInfo(
        preset_name=preset_name,
        entry_strategy=first_sig_gen.entry_name if first_sig_gen else "swing_break",
        exit_strategy=first_sig_gen.exit_name if first_sig_gen else "swing",
        risk_pct=risk_pct,
        rr_ratio=rr_ratio,
        indicators=indicators or [],
        symbol_strategies=strategy_names,
        symbol_configs=symbol_configs,
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
                signal_generators=signal_generators,
                position_sizers=position_sizers,
                risk_manager=risk_manager,
                rr_ratio=rr_ratio,
                dry_run=dry_run,
                allow_short=allow_short,
                callbacks=adapter.callbacks,
                strategy_names=strategy_names,
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

    # Initialize logging from config
    log_cfg = get_logging_config()
    configure_logging(level=log_cfg.level, log_file=log_cfg.log_file)

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
    parser.add_argument(
        "--budget",
        type=str,
        metavar="AMOUNT",
        help="Fixed budget per trade: dollar amount (e.g., 5000) or percentage (e.g., 50%%). Overrides risk-based sizing.",
    )
    args = parser.parse_args()

    # Parse symbols with optional per-symbol presets (e.g., "SPY:day_momentum" or "AAPL")
    symbols: list[str] = []
    symbol_presets: dict[str, str] = {}  # symbol -> preset name
    for sym in args.symbols:
        for s in sym.split(","):
            s = s.strip().upper()
            if not s:
                continue
            if ":" in s:
                symbol, preset_name = s.split(":", 1)
                symbols.append(symbol)
                symbol_presets[symbol] = preset_name.lower()
            else:
                symbols.append(s)

    bot_cfg = get_bot_config()
    strategy_cfg = get_strategy_config()
    engine_cfg = get_engine_config()

    # Create broker to fetch account equity (for live trading, equity comes from broker)
    from tradingbot._components.brokers.registry import get_broker_registry
    from tradingbot._components.feeds.registry import get_feed_registry

    feed: DataFeedProtocol
    broker: BrokerProtocol
    if args.replay:
        from tradingbot._components.brokers.plugins.paper import PaperBroker
        from tradingbot._components.feeds.plugins.replay import ReplayFeed

        # Replay mode requires --capital since we're simulating with paper broker
        if args.capital is None:
            parser.error("replay mode requires --capital (e.g., --capital 10000)")
        capital = args.capital

        # Update cache before replay
        console.print("[bold]Updating cache for replay...[/bold]")
        update_cache_for_replay(symbols, args.replay_days)

        feed = ReplayFeed(delay=args.replay_speed, days=args.replay_days)
        broker = PaperBroker(initial_capital=capital)
    else:
        # Live trading: fetch equity from broker
        feed_name = "alpaca" if engine_cfg.provider == "alpaca" else "yahoo"
        feed = get_feed_registry().get(feed_name)
        broker = get_broker_registry().get(engine_cfg.provider)
        account = broker.get_account()
        capital = account.equity
        console.print(f"[bold cyan]Account equity:[/bold cyan] ${capital:,.2f}")

    # Load default preset if specified via --preset
    default_preset = None
    if args.preset:
        default_preset = get_preset(args.preset)

    # Default values from CLI args > preset > config
    default_risk_pct = (
        args.risk if args.risk is not None else (default_preset.risk_pct if default_preset else strategy_cfg.risk_pct)
    )
    default_rr_ratio = (
        args.rr if args.rr is not None else (default_preset.rr_ratio if default_preset else strategy_cfg.rr_ratio)
    )
    default_entry = (
        args.strategy if args.strategy is not None else (default_preset.entry if default_preset else strategy_cfg.entry)
    )
    default_exit = default_preset.exit if default_preset else strategy_cfg.exit
    default_indicators = default_preset.indicators if default_preset else []
    default_preset_name = default_preset.name if default_preset else "custom"
    default_filter_mode = default_preset.filter_mode if default_preset else "all"
    default_eod_exit = default_preset.eod_exit if default_preset else True
    default_partial_exits = default_preset.partial_exit_levels if default_preset else ()

    # Use config if --atr-sizing not explicitly passed
    use_atr = args.atr_sizing if args.atr_sizing else strategy_cfg.atr_sizing

    # Parse budget (dollar amount or percentage), split between symbols
    cli_budget: float | None = None
    if args.budget:
        if args.budget.endswith("%"):
            pct = float(args.budget.rstrip("%")) / 100
            total_budget = capital * pct
        else:
            total_budget = float(args.budget)
        # Split budget equally between symbols
        cli_budget = total_budget / len(symbols)

    def format_partial_exits(levels: tuple[object, ...]) -> str:
        """Format partial exit levels into a summary string like '1R→50%, 2R→25%'."""
        if not levels:
            return ""
        parts = [f"{lvl.r_multiple}R→{int(lvl.exit_pct * 100)}%" for lvl in levels]  # type: ignore[attr-defined]
        return ", ".join(parts)

    # Create per-symbol SignalGenerators, strategy names, and configs
    from tradingbot._components.hub.types import SymbolStrategyConfig

    signal_generators: dict[str, SignalGenerator] = {}
    strategy_names: dict[str, str] = {}  # symbol -> display name (preset or "custom")
    symbol_configs: dict[str, SymbolStrategyConfig] = {}  # symbol -> full strategy config

    for symbol in symbols:
        if symbol in symbol_presets:
            # Symbol has a specific preset
            preset = get_preset(symbol_presets[symbol])
            signal_generators[symbol] = SignalGenerator(
                strategy_cfg.swing_lb,
                entry_strategy=preset.entry,
                exit_strategy=preset.exit,
            )
            strategy_names[symbol] = preset.name
            symbol_configs[symbol] = SymbolStrategyConfig(
                preset_name=preset.name,
                entry_strategy=preset.entry,
                exit_strategy=preset.exit,
                risk_pct=preset.risk_pct,
                rr_ratio=preset.rr_ratio,
                indicators=list(preset.indicators),
                filter_mode=preset.filter_mode,
                eod_exit=preset.eod_exit,
                partial_exits=format_partial_exits(preset.partial_exit_levels),
            )
        else:
            # Use default preset/strategy
            signal_generators[symbol] = SignalGenerator(
                strategy_cfg.swing_lb,
                entry_strategy=default_entry,
                exit_strategy=default_exit,
            )
            # Ensure all symbols have strategy names for consistent display
            strategy_names[symbol] = default_preset_name
            symbol_configs[symbol] = SymbolStrategyConfig(
                preset_name=default_preset_name,
                entry_strategy=default_entry,
                exit_strategy=default_exit,
                risk_pct=default_risk_pct,
                rr_ratio=default_rr_ratio,
                indicators=list(default_indicators),
                filter_mode=default_filter_mode,
                eod_exit=default_eod_exit,
                partial_exits=format_partial_exits(default_partial_exits),
            )

    # For backward compatibility, use first symbol's config for global values
    rr_ratio = default_rr_ratio
    indicators = default_indicators
    preset_name = default_preset_name if not symbol_presets else "multi-strategy"

    # Create per-symbol PositionSizers
    position_sizers: dict[str, PositionSizer] = {}
    if cli_budget or bot_cfg.budgets.enabled:
        # Budget-based sizing: CLI budget or per-symbol config budgets
        console.print("[bold cyan]Capital & Budgets:[/bold cyan]")
        for symbol in symbols:
            symbol_budget = cli_budget if cli_budget else bot_cfg.budgets.get_budget(symbol, capital)
            position_sizers[symbol] = PositionSizer(
                capital, default_risk_pct, use_atr_sizing=use_atr, budget=symbol_budget
            )
            budget_info = f"budget=${symbol_budget:,.0f}" if symbol_budget else "risk-based"
            console.print(f"  {symbol}: {budget_info}")
    else:
        # Risk-based sizing: shared pool
        shared_sizer = PositionSizer(capital, default_risk_pct, use_atr_sizing=use_atr)
        for symbol in symbols:
            position_sizers[symbol] = shared_sizer
        console.print(f"[bold cyan]Capital:[/bold cyan] ${capital:,.0f} (risk-based sizing)")

    # For replay mode, disable trading hours restriction since we're replaying historical data
    risk_config = engine_cfg.risk
    if args.replay:
        from dataclasses import replace

        risk_config = replace(risk_config, trading_hours_only=False)

    risk_manager = RiskManager(risk_config, capital)

    if args.tui:
        # Modern TUI with hub-based architecture
        _run_with_modern_tui(
            symbols=symbols,
            broker=broker,
            feed=feed,
            signal_generators=signal_generators,
            position_sizers=position_sizers,
            risk_manager=risk_manager,
            rr_ratio=rr_ratio,
            dry_run=args.dry_run,
            allow_short=strategy_cfg.allow_short,
            ws_port=args.ws_port,
            enable_ws=not args.no_ws,
            serve_web=args.web,
            web_port=args.web_port,
            preset_name=preset_name,
            strategy_names=strategy_names,
            risk_pct=default_risk_pct,
            indicators=indicators,
            is_replay=args.replay,
            symbol_configs=symbol_configs,
        )
    elif args.web:
        # Headless mode with web interface (includes WebSocket server)
        _run_headless_with_hub(
            symbols=symbols,
            broker=broker,
            feed=feed,
            signal_generators=signal_generators,
            position_sizers=position_sizers,
            risk_manager=risk_manager,
            rr_ratio=rr_ratio,
            dry_run=args.dry_run,
            allow_short=strategy_cfg.allow_short,
            ws_port=args.ws_port,
            serve_web=args.web,
            web_port=args.web_port,
            preset_name=preset_name,
            strategy_names=strategy_names,
            risk_pct=default_risk_pct,
            indicators=indicators,
            is_replay=args.replay,
            symbol_configs=symbol_configs,
        )
    else:
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(
                run_live(
                    symbols=symbols,
                    broker=broker,
                    feed=feed,
                    signal_generators=signal_generators,
                    strategy_names=strategy_names,
                    position_sizers=position_sizers,
                    risk_manager=risk_manager,
                    rr_ratio=rr_ratio,
                    dry_run=args.dry_run,
                    allow_short=strategy_cfg.allow_short,
                    callbacks=make_cli_callbacks(),
                )
            )

"""Trading engine for real-time trading."""

import asyncio
import contextlib
from collections import deque
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Final, TypeVar

import polars as pl
from rich.console import Console

from tradingbot.config import get_live_config
from tradingbot.interfaces import BrokerProtocol, DataFeedProtocol
from tradingbot.types import Bar, Direction, Order, Position, Signal, SwingPoint

from . import sounds
from .brokers.plugins.paper import PaperBroker
from .feeds import DataFeed
from .feeds.plugins.replay import ReplayFeed
from .live_risk import LiveRiskManager
from .risk import RiskManager
from .signals import SignalGenerator
from .swing import find_swing_points

MIN_BARS_REQUIRED: Final[int] = 50
MAX_BARS_HISTORY: Final[int] = 500


# =============================================================================
# Event Types
# =============================================================================


@dataclass
class EngineStartedEvent:
    symbols: list[str]
    broker_name: str
    feed_name: str
    dry_run: bool


@dataclass
class EngineStoppedEvent:
    risk_manager: LiveRiskManager


class MessageLevel(Enum):
    """Semantic message levels for engine events."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    DEBUG = "debug"


@dataclass
class MessageEvent:
    message: str
    level: MessageLevel = MessageLevel.INFO


@dataclass
class BarEvent:
    bar: Bar
    signal: Signal
    trend: str
    position: Position | None


@dataclass
class SignalEvent:
    direction: Direction
    symbol: str
    entry: float
    stop: float
    tp: float
    size: float
    blocked: bool
    reason: str
    was_capped: bool


@dataclass
class TradeClosedEvent:
    direction: Direction
    symbol: str
    entry: float
    exit_price: float
    pnl: float
    reason: str


@dataclass
class StatsUpdatedEvent:
    pnl: float
    trades: int
    winners: int
    losers: int


# =============================================================================
# Event Callbacks Container
# =============================================================================

T = TypeVar("T")
EventCallback = Callable[[T], None] | Callable[[T], Awaitable[None]]


@dataclass
class EngineCallbacks:
    """Container for engine event callbacks.

    Supports multiple callbacks per event. Callbacks can be sync or async.

    Example:
        callbacks = EngineCallbacks()

        @callbacks.on_bar
        def handle_bar(event: BarEvent):
            print(f"{event.bar.symbol} @ {event.bar.close}")

        @callbacks.on_signal
        async def handle_signal(event: SignalEvent):
            await log_to_db(event)

        engine = TradingEngine(..., callbacks=callbacks)
    """

    _on_started: list[EventCallback[EngineStartedEvent]] = field(default_factory=list)
    _on_stopped: list[EventCallback[EngineStoppedEvent]] = field(default_factory=list)
    _on_message: list[EventCallback[MessageEvent]] = field(default_factory=list)
    _on_bar: list[EventCallback[BarEvent]] = field(default_factory=list)
    _on_signal: list[EventCallback[SignalEvent]] = field(default_factory=list)
    _on_trade_closed: list[EventCallback[TradeClosedEvent]] = field(default_factory=list)
    _on_stats_updated: list[EventCallback[StatsUpdatedEvent]] = field(default_factory=list)

    def on_started[C: EventCallback[EngineStartedEvent]](self, cb: C) -> C:
        self._on_started.append(cb)
        return cb

    def on_stopped[C: EventCallback[EngineStoppedEvent]](self, cb: C) -> C:
        self._on_stopped.append(cb)
        return cb

    def on_message[C: EventCallback[MessageEvent]](self, cb: C) -> C:
        self._on_message.append(cb)
        return cb

    def on_bar[C: EventCallback[BarEvent]](self, cb: C) -> C:
        self._on_bar.append(cb)
        return cb

    def on_signal[C: EventCallback[SignalEvent]](self, cb: C) -> C:
        self._on_signal.append(cb)
        return cb

    def on_trade_closed[C: EventCallback[TradeClosedEvent]](self, cb: C) -> C:
        self._on_trade_closed.append(cb)
        return cb

    def on_stats_updated[C: EventCallback[StatsUpdatedEvent]](self, cb: C) -> C:
        self._on_stats_updated.append(cb)
        return cb

    async def emit_started(self, event: EngineStartedEvent) -> None:
        await self._emit(self._on_started, event)

    async def emit_stopped(self, event: EngineStoppedEvent) -> None:
        await self._emit(self._on_stopped, event)

    async def emit_message(self, event: MessageEvent) -> None:
        await self._emit(self._on_message, event)

    async def emit_bar(self, event: BarEvent) -> None:
        await self._emit(self._on_bar, event)

    async def emit_signal(self, event: SignalEvent) -> None:
        await self._emit(self._on_signal, event)

    async def emit_trade_closed(self, event: TradeClosedEvent) -> None:
        await self._emit(self._on_trade_closed, event)

    async def emit_stats_updated(self, event: StatsUpdatedEvent) -> None:
        await self._emit(self._on_stats_updated, event)

    async def _emit[E](self, callbacks: list[EventCallback[E]], event: E) -> None:
        """Emit an event to all registered callbacks."""
        import inspect

        for cb in callbacks:
            result = cb(event)
            if inspect.isawaitable(result):
                await result


# =============================================================================
# Trading Engine
# =============================================================================


class TradingEngine:
    """Event-driven engine for real-time trading."""

    def __init__(
        self,
        symbols: Collection[str],
        broker: BrokerProtocol,
        feed: DataFeedProtocol,
        signal_generator: SignalGenerator,
        risk_manager: RiskManager,
        live_risk_manager: LiveRiskManager,
        dry_run: bool = False,
        callbacks: EngineCallbacks | None = None,
    ) -> None:
        self._symbols = list(set(symbols))
        self._dry_run = dry_run
        self._broker = broker
        self._feed = feed
        self._sig_gen = signal_generator
        self._risk_mgr = risk_manager
        self._live_risk = live_risk_manager
        self._cb = callbacks or EngineCallbacks()

        # State tracking
        self._positions: dict[str, Position] = {}
        self._pending_orders: set[str] = set()
        self._bars: dict[str, deque[Bar]] = {sym: deque(maxlen=MAX_BARS_HISTORY) for sym in self._symbols}
        self._running = False

    @property
    def symbols(self) -> list[str]:
        return self._symbols

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    async def _emit_message(self, message: str, level: MessageLevel = MessageLevel.INFO) -> None:
        await self._cb.emit_message(MessageEvent(message, level))

    async def _emit_stats(self) -> None:
        await self._cb.emit_stats_updated(
            StatsUpdatedEvent(
                pnl=self._live_risk.session_pnl,
                trades=self._live_risk.session_trades,
                winners=self._live_risk.session_winners,
                losers=self._live_risk.session_losers,
            )
        )

    async def start(self) -> None:
        """Start live trading."""
        await self._cb.emit_started(
            EngineStartedEvent(
                symbols=self._symbols,
                broker_name=self._broker.name,
                feed_name=self._feed.name,
                dry_run=self._dry_run,
            )
        )

        # Reset daily tracking
        account = self._broker.get_account()
        self._live_risk.reset_daily(account.equity)

        # Load historical data to bootstrap
        await self._load_history()

        # Sync existing positions from broker
        await self._sync_broker_positions()

        # Subscribe to feed
        await self._feed.subscribe(self._symbols, self._on_bar)

        # Start feed
        self._running = True
        await self._emit_message("Live feed started", MessageLevel.SUCCESS)
        await self._feed.start()

    async def stop(self) -> None:
        """Stop live trading gracefully."""
        self._running = False
        await self._feed.stop()
        await self._cb.emit_stopped(EngineStoppedEvent(risk_manager=self._live_risk))

    async def _load_history(self) -> None:
        """Load historical data for each symbol to bootstrap indicators."""
        await self._emit_message("Loading historical data...", MessageLevel.DEBUG)

        for symbol in self._symbols:
            try:
                df: pl.DataFrame = DataFeed.history(symbol, period="3mo", interval="1d")

                for row in df.iter_rows(named=True):
                    bar = Bar(
                        symbol=symbol,
                        datetime=row["datetime"],
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=int(row["volume"]),
                    )
                    self._bars[symbol].append(bar)

                await self._emit_message(f"✓ {symbol}: {len(self._bars[symbol])} bars loaded", MessageLevel.SUCCESS)
            except Exception as e:
                await self._emit_message(f"✗ {symbol}: {e}", MessageLevel.ERROR)

    async def _sync_broker_positions(self) -> None:
        """Sync existing positions from broker on startup."""
        broker_positions = self._broker.get_positions()

        for bp in broker_positions:
            if bp.symbol not in self._symbols:
                continue

            # Calculate stop/TP from current market structure
            if bp.symbol in self._bars and len(self._bars[bp.symbol]) >= MIN_BARS_REQUIRED:
                df = self._bars_to_df(bp.symbol)
                idx = len(df) - 1
                swings = find_swing_points(df, self._sig_gen.swing_lookback)
                stop = self._risk_mgr.calc_stop(bp.direction, bp.avg_entry_price, df, idx, swings)
                tp = self._risk_mgr.calc_tp(bp.direction, bp.avg_entry_price, stop)
            else:
                stop = bp.avg_entry_price * (0.98 if bp.direction == "LONG" else 1.02)
                tp = bp.avg_entry_price * (1.04 if bp.direction == "LONG" else 0.96)

            self._positions[bp.symbol] = Position(
                entry_price=bp.avg_entry_price,
                entry_index=0,
                entry_time=datetime.now(),
                direction=bp.direction,
                size=bp.size,
                stop_loss=stop,
                take_profit=tp,
                initial_stop_loss=stop,
            )

            await self._emit_message(
                f"⚠ Synced: {bp.symbol} {bp.direction} {bp.size:.1f} @ ${bp.avg_entry_price:.2f}",
                MessageLevel.WARNING,
            )

        if broker_positions:
            self._live_risk.update_position_count(len(self._positions))

    async def _on_bar(self, bar: Bar) -> None:
        """Process new bar - main trading logic."""
        if not self._running:
            return

        self._bars[bar.symbol].append(bar)

        if isinstance(self._broker, PaperBroker):
            self._broker.set_price(bar.symbol, bar.close)

        account = self._broker.get_account()
        self._live_risk.reset_daily(account.equity)

        if self._live_risk.check_circuit_breaker():
            return

        if len(self._bars[bar.symbol]) < MIN_BARS_REQUIRED:
            return

        df = self._bars_to_df(bar.symbol)

        position = self._positions.get(bar.symbol)
        if position:
            await self._check_exit(bar, position)

        signal, details = self._sig_gen.generate(df, len(df) - 1, position)

        if position is None and bar.symbol not in self._pending_orders and signal in (Signal.BUY, Signal.SELL):
            await self._open_position(bar, signal, df)

        # Emit bar event
        trend = str(details.get("trend", "N/A"))
        current_pos = self._positions.get(bar.symbol)
        await self._cb.emit_bar(BarEvent(bar=bar, signal=signal, trend=trend, position=current_pos))
        await self._emit_stats()

    def _bars_to_df(self, symbol: str) -> pl.DataFrame:
        """Convert bar deque to DataFrame."""
        bars = list(self._bars[symbol])
        return pl.DataFrame(
            {
                "datetime": [b.datetime for b in bars],
                "open": [b.open for b in bars],
                "high": [b.high for b in bars],
                "low": [b.low for b in bars],
                "close": [b.close for b in bars],
                "volume": [b.volume for b in bars],
            }
        )

    async def _open_position(self, bar: Bar, signal: Signal, df: pl.DataFrame) -> None:
        """Open a new position."""
        direction: Direction = "LONG" if signal == Signal.BUY else "SHORT"
        price = bar.close
        idx = len(df) - 1

        swings: list[SwingPoint] = find_swing_points(df, self._sig_gen.swing_lookback)
        stop = self._risk_mgr.calc_stop(direction, price, df, idx, swings)
        tp = self._risk_mgr.calc_tp(direction, price, stop)
        size = self._risk_mgr.calc_size(price, stop)

        account = self._broker.get_account()
        self._live_risk.update_position_count(len(self._positions))
        can_trade, reason = self._live_risk.can_open_position()
        size, was_capped = self._live_risk.cap_position_size(size, price, account.equity)

        blocked = not can_trade and not self._dry_run
        await self._cb.emit_signal(
            SignalEvent(
                direction=direction,
                symbol=bar.symbol,
                entry=price,
                stop=stop,
                tp=tp,
                size=size,
                blocked=blocked,
                reason=reason,
                was_capped=was_capped,
            )
        )

        if not can_trade and not self._dry_run:
            return

        if self._dry_run:
            self._positions[bar.symbol] = Position(
                entry_price=price,
                entry_index=idx,
                entry_time=bar.datetime,
                direction=direction,
                size=size,
                stop_loss=stop,
                take_profit=tp,
                initial_stop_loss=stop,
            )
            self._live_risk.update_position_count(len(self._positions))
            return

        order = Order(symbol=bar.symbol, direction=direction, size=size, order_type="MARKET")
        self._pending_orders.add(bar.symbol)

        try:
            result = self._broker.submit_order(order)

            if result.status == "FILLED":
                self._positions[bar.symbol] = Position(
                    entry_price=result.filled_price or price,
                    entry_index=idx,
                    entry_time=bar.datetime,
                    direction=direction,
                    size=result.filled_size,
                    stop_loss=stop,
                    take_profit=tp,
                    initial_stop_loss=stop,
                )
                self._live_risk.update_position_count(len(self._positions))
                await self._emit_message(f"✓ Order filled at ${result.filled_price:.2f}", MessageLevel.SUCCESS)
                sounds.play(sounds.BUY if direction == "LONG" else sounds.SELL)
            else:
                await self._emit_message(f"✗ Order {result.status}: {result.message}", MessageLevel.ERROR)
        finally:
            self._pending_orders.discard(bar.symbol)

    async def _check_exit(self, bar: Bar, position: Position) -> None:
        """Check if position should be exited."""
        should_exit = False
        exit_reason = ""

        if position.direction == "LONG":
            if bar.low <= position.stop_loss:
                should_exit, exit_reason = True, "STOP_LOSS"
            elif bar.high >= position.take_profit:
                should_exit, exit_reason = True, "TAKE_PROFIT"
        else:
            if bar.high >= position.stop_loss:
                should_exit, exit_reason = True, "STOP_LOSS"
            elif bar.low <= position.take_profit:
                should_exit, exit_reason = True, "TAKE_PROFIT"

        if should_exit:
            await self._close_position(bar, position, exit_reason)

    async def _close_position(self, bar: Bar, position: Position, reason: str) -> None:
        """Close an existing position."""
        exit_price = position.stop_loss if reason == "STOP_LOSS" else position.take_profit

        if self._dry_run:
            pnl = (exit_price - position.entry_price) * position.size
            if position.direction == "SHORT":
                pnl = -pnl
            self._live_risk.record_trade_pnl(pnl)

            await self._cb.emit_trade_closed(
                TradeClosedEvent(
                    direction=position.direction,
                    symbol=bar.symbol,
                    entry=position.entry_price,
                    exit_price=exit_price,
                    pnl=pnl,
                    reason=reason,
                )
            )
            await self._emit_stats()

            sounds.play(sounds.PROFIT if pnl > 0 else sounds.LOSS)
            del self._positions[bar.symbol]
            self._live_risk.update_position_count(len(self._positions))
            return

        close_direction: Direction = "SHORT" if position.direction == "LONG" else "LONG"
        order = Order(symbol=bar.symbol, direction=close_direction, size=position.size, order_type="MARKET")
        result = self._broker.submit_order(order)

        if result.status == "FILLED":
            actual_exit = result.filled_price or exit_price
            pnl = (actual_exit - position.entry_price) * position.size
            if position.direction == "SHORT":
                pnl = -pnl
            self._live_risk.record_trade_pnl(pnl)

            await self._cb.emit_trade_closed(
                TradeClosedEvent(
                    direction=position.direction,
                    symbol=bar.symbol,
                    entry=position.entry_price,
                    exit_price=actual_exit,
                    pnl=pnl,
                    reason=reason,
                )
            )
            await self._emit_stats()

            sounds.play(sounds.PROFIT if pnl > 0 else sounds.LOSS)
            del self._positions[bar.symbol]
            self._live_risk.update_position_count(len(self._positions))

            if self._live_risk.check_circuit_breaker():
                await self._emit_message("⚠ CIRCUIT BREAKER TRIGGERED - Trading paused", MessageLevel.ERROR)
        else:
            await self._emit_message(f"✗ Close order {result.status}: {result.message}", MessageLevel.ERROR)


# =============================================================================
# CLI Output Callbacks
# =============================================================================

console = Console()


def make_cli_callbacks() -> EngineCallbacks:
    """Create callbacks for CLI output."""
    callbacks = EngineCallbacks()

    @callbacks.on_started
    def on_started(event: EngineStartedEvent) -> None:
        live_cfg = get_live_config()
        console.print()
        console.rule("[bold green]TRADING ENGINE[/bold green]")
        console.print(f"Symbols: [cyan]{', '.join(event.symbols)}[/cyan]")
        console.print(f"Broker: [cyan]{event.broker_name}[/cyan]")
        console.print(f"Feed: [cyan]{event.feed_name}[/cyan]")
        console.print(f"Dry run: [yellow]{event.dry_run}[/yellow]")
        console.print()
        console.print("[bold]Risk Controls:[/bold]")
        console.print(f"  Max daily loss: [cyan]{live_cfg.risk.max_daily_loss_pct:.1%}[/cyan]")
        console.print(f"  Circuit breaker: [cyan]{live_cfg.risk.circuit_breaker_loss_pct:.1%}[/cyan]")
        console.print(f"  Max positions: [cyan]{live_cfg.risk.max_open_positions}[/cyan]")
        console.print(f"  Max position size: [cyan]{live_cfg.risk.max_position_size_pct:.1%}[/cyan]")
        console.print(f"  Trading hours only: [cyan]{live_cfg.risk.trading_hours_only}[/cyan]")
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


# =============================================================================
# Entry Points
# =============================================================================


async def run_live(
    symbols: list[str],
    broker: BrokerProtocol,
    feed: DataFeedProtocol,
    signal_generator: SignalGenerator,
    risk_manager: RiskManager,
    live_risk_manager: LiveRiskManager,
    dry_run: bool = False,
    callbacks: EngineCallbacks | None = None,
) -> None:
    """Run trading engine."""
    engine = TradingEngine(
        symbols=symbols,
        broker=broker,
        feed=feed,
        signal_generator=signal_generator,
        risk_manager=risk_manager,
        live_risk_manager=live_risk_manager,
        dry_run=dry_run,
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


def _parse_date(date_str: str) -> date:
    """Parse date string in YYYY-MM-DD format."""
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def main() -> None:
    """CLI entry point for live trading."""
    import argparse

    from tradingbot.config import get_bot_config

    from .brokers import get_registry as get_broker_registry
    from .feeds import get_registry as get_feed_registry

    parser = argparse.ArgumentParser(
        description="Run live trading bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  tradingbot-live SPY
  tradingbot-live SPY QQQ --dry-run

Replay mode (simulate live trading with historical data):
  tradingbot-live SPY --replay
  tradingbot-live SPY --replay --speed 10
  tradingbot-live SPY --replay --speed 0
  tradingbot-live SPY --replay --from 2024-01-01 --to 2024-06-30
        """,
    )

    parser.add_argument("symbols", nargs="+", help="Symbols to trade (e.g., SPY AAPL)")
    parser.add_argument("--dry-run", action="store_true", help="Log signals without executing trades")
    parser.add_argument("--replay", action="store_true", help="Replay historical data as if it were live")
    parser.add_argument("--speed", type=float, default=1.0, help="Replay speed: bars per second (0 = instant)")
    parser.add_argument("--from", dest="from_date", type=_parse_date, default=None, help="Replay start date")
    parser.add_argument("--to", dest="to_date", type=_parse_date, default=None, help="Replay end date")
    parser.add_argument("--period", default="1d", help="Historical period for replay (default: 1d)")
    parser.add_argument("--interval", default="15m", help="Bar interval for replay (default: 15m)")
    parser.add_argument("--tui", action="store_true", help="Run with terminal UI")
    args = parser.parse_args()

    symbols: list[str] = []
    for sym in args.symbols:
        symbols.extend(s.strip().upper() for s in sym.split(",") if s.strip())

    cfg = get_bot_config()
    live_cfg = get_live_config()

    broker = get_broker_registry().get(live_cfg.broker)
    signal_generator = SignalGenerator(cfg.swing_lb)
    risk_manager = RiskManager(cfg.capital, cfg.risk_pct, cfg.rr_ratio)
    live_risk_manager = LiveRiskManager(live_cfg.risk, cfg.capital)

    feed: DataFeedProtocol
    if args.replay:
        feed = ReplayFeed(
            speed=args.speed,
            start_date=args.from_date,
            end_date=args.to_date,
            period=args.period,
            interval=args.interval,
        )
    else:
        feed = get_feed_registry().get(live_cfg.feed)

    if args.tui:
        _run_with_tui(
            symbols=symbols,
            broker=broker,
            feed=feed,
            signal_generator=signal_generator,
            risk_manager=risk_manager,
            live_risk_manager=live_risk_manager,
            dry_run=args.dry_run,
        )
    else:
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(
                run_live(
                    symbols=symbols,
                    broker=broker,
                    feed=feed,
                    signal_generator=signal_generator,
                    risk_manager=risk_manager,
                    live_risk_manager=live_risk_manager,
                    dry_run=args.dry_run,
                    callbacks=make_cli_callbacks(),
                )
            )


def _run_with_tui(
    symbols: list[str],
    broker: BrokerProtocol,
    feed: DataFeedProtocol,
    signal_generator: SignalGenerator,
    risk_manager: RiskManager,
    live_risk_manager: LiveRiskManager,
    dry_run: bool,
) -> None:
    """Run live trading with TUI."""
    from .tui import TradingTUI

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
                risk_manager=risk_manager,
                live_risk_manager=live_risk_manager,
                dry_run=dry_run,
                callbacks=make_tui_callbacks(self),
            )

    app = TradingApp()
    app.run()

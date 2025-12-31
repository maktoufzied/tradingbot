"""Core trading engine."""

from collections import deque
from collections.abc import Collection
from datetime import datetime
from typing import Final

import polars as pl

from tradingbot.config import get_engine_config, get_health_config, get_strategy_config
from tradingbot.interfaces import BrokerProtocol, DataFeedProtocol
from tradingbot.types import Bar, BarOrigin, Direction, Order, PendingOrder, Position, Signal

from .. import sounds
from ..brokers.plugins.paper import PaperBroker
from ..feeds import DataFeed
from ..health import HealthChecker
from ..live_risk import LiveRiskManager
from ..risk import PositionSizer
from ..signals import SignalGenerator
from .callbacks import EngineCallbacks
from .events import (
    AccountEvent,
    BarEvent,
    ClockEvent,
    EngineStartedEvent,
    EngineStoppedEvent,
    MessageEvent,
    MessageLevel,
    RiskEvent,
    SignalEvent,
    StatsUpdatedEvent,
    TradeClosedEvent,
)

MIN_BARS_REQUIRED: Final[int] = 50
MAX_BARS_HISTORY: Final[int] = 500


class TradingEngine:
    """Event-driven engine for real-time trading."""

    def __init__(
        self,
        symbols: Collection[str],
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
        self._symbols = list(set(symbols))
        self._dry_run = dry_run
        self._allow_short = allow_short
        self._broker = broker
        self._feed = feed
        self._sig_gen = signal_generator
        self._pos_sizer = position_sizer
        self._live_risk = live_risk_manager
        self._rr_ratio = rr_ratio
        self._cb = callbacks or EngineCallbacks()

        # State tracking
        self._positions: dict[str, Position] = {}
        self._pending_orders: dict[str, PendingOrder] = {}  # symbol -> pending entry order
        self._pending_closes: set[str] = set()  # symbols with pending close orders
        self._bars: dict[str, deque[Bar]] = {sym: deque(maxlen=MAX_BARS_HISTORY) for sym in self._symbols}
        self._running = False
        self._last_bar_time: datetime | None = None

        # Health checker
        self._health_checker = HealthChecker(
            config=get_health_config(),
            broker=broker,
            feed=feed,
            risk_manager=live_risk_manager,
            get_positions_count=lambda: len(self._positions),
            get_last_bar_time=lambda: self._last_bar_time,
        )

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

    async def _emit_account(self) -> None:
        account = self._broker.get_account()
        await self._cb.emit_account(
            AccountEvent(
                equity=account.equity,
                cash=account.cash,
                buying_power=account.buying_power,
                day_pnl=self._live_risk.session_pnl,
            )
        )

    async def _emit_risk(self) -> None:
        can_trade, blocked_reason = self._live_risk.can_open_position()
        await self._cb.emit_risk(
            RiskEvent(
                daily_loss_pct=self._live_risk.daily_pnl_pct,
                max_daily_loss_pct=self._live_risk._config.max_daily_loss_pct,
                open_positions=len(self._positions),
                max_positions=self._live_risk._config.max_open_positions,
                circuit_breaker_active=self._live_risk.check_circuit_breaker(),
                can_trade=can_trade,
                blocked_reason=blocked_reason if not can_trade else None,
            )
        )

    async def _emit_clock(self) -> None:
        clock = self._broker.get_clock()
        if clock:
            await self._cb.emit_clock(
                ClockEvent(
                    is_open=clock.is_open,
                    next_open=clock.next_open,
                    next_close=clock.next_close,
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

        # Emit initial clock status
        await self._emit_clock()

        # Check if market is open
        clock = self._broker.get_clock()
        if clock and not clock.is_open:
            next_open_str = clock.next_open.strftime("%Y-%m-%d %H:%M") if clock.next_open else "unknown"
            await self._emit_message(
                f"Market is closed. Next open: {next_open_str} UTC",
                MessageLevel.WARNING,
            )
            if not self._dry_run:
                await self._emit_message(
                    "Live trading requires market to be open. Use --dry-run to test outside market hours.",
                    MessageLevel.ERROR,
                )
                return

        # Reset daily tracking
        account = self._broker.get_account()
        self._live_risk.reset_daily(account.equity)

        # Sync today's trades from broker (if available)
        if hasattr(self._broker, "get_today_trades"):
            trades = self._broker.get_today_trades()
            for trade in trades:
                # Record trade stats
                self._live_risk.record_trade_pnl(trade.pnl)
                # Emit trade event to TUI
                await self._cb.emit_trade_closed(
                    TradeClosedEvent(
                        direction=trade.direction,
                        symbol=trade.symbol,
                        entry=trade.entry_price,
                        exit_price=trade.exit_price,
                        size=trade.size,
                        pnl=trade.pnl,
                        reason="SYNCED",
                    )
                )
            if trades:
                total_pnl = sum(t.pnl for t in trades)
                await self._emit_message(
                    f"Synced {len(trades)} trade(s) from today, P&L: ${total_pnl:+.2f}",
                    MessageLevel.INFO,
                )

        # Load historical data to bootstrap
        await self._load_history()

        # Sync existing positions from broker
        await self._sync_broker_positions()

        # Emit initial account/stats/risk to TUI
        await self._emit_account()
        await self._emit_stats()
        await self._emit_risk()

        # Subscribe to feed
        await self._feed.subscribe(self._symbols, self._on_bar)
        await self._emit_message(f"Subscribed to: {', '.join(self._symbols)}", MessageLevel.DEBUG)

        # Start feed and health checker
        self._running = True
        await self._health_checker.start()
        await self._emit_message("Live feed started", MessageLevel.SUCCESS)
        await self._feed.start()

    async def stop(self) -> None:
        """Stop live trading gracefully."""
        self._running = False
        await self._health_checker.stop()
        await self._feed.stop()
        await self._cb.emit_stopped(EngineStoppedEvent(risk_manager=self._live_risk))

    async def _load_history(self) -> None:
        """Load historical intraday data for each symbol to bootstrap indicators.

        Uses configured interval bars from the past 5 days to establish intraday swing points.
        This ensures stop/TP levels are based on recent intraday price action,
        not old daily swings from months ago.
        """
        interval = get_engine_config().bar_interval
        await self._emit_message(f"Loading historical data ({interval} bars)...", MessageLevel.DEBUG)

        for symbol in self._symbols:
            try:
                df: pl.DataFrame = DataFeed.history(symbol, period="5d", interval=interval)

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

                # Emit recent bars to populate TUI sparkline immediately (last 60 bars)
                if self._bars[symbol] and len(self._bars[symbol]) >= MIN_BARS_REQUIRED:
                    hist_df = self._bars_to_df(symbol)
                    bars_to_emit = list(self._bars[symbol])[-60:]
                    for bar in bars_to_emit:
                        # Use HOLD signal for historical bars (avoid triggering trades)
                        await self._cb.emit_bar(BarEvent(bar=bar, signal=Signal.HOLD, trend="NEUTRAL", position=None))
                    # Emit final bar with actual signal/trend
                    last_bar = bars_to_emit[-1]
                    signal, details = self._sig_gen.generate(hist_df, len(hist_df) - 1, False)
                    trend = str(details.get("trend", "NEUTRAL"))
                    await self._cb.emit_bar(BarEvent(bar=last_bar, signal=signal, trend=trend, position=None))
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
                exit_params = self._sig_gen.calc_exit(bp.direction, bp.avg_entry_price, df, self._rr_ratio)
                stop, tp = exit_params.stop_loss, exit_params.take_profit
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

        # REALTIME bars are for chart updates only - emit and skip strategy
        if bar.origin == BarOrigin.REALTIME:
            current_pos = self._positions.get(bar.symbol)
            await self._cb.emit_bar(BarEvent(bar=bar, signal=Signal.HOLD, trend="", position=current_pos))
            return

        # Validate symbol - only process bars for symbols we're configured to trade
        if bar.symbol not in self._bars:
            await self._emit_message(
                f"⚠ Ignoring bar for unexpected symbol: {bar.symbol} (subscribed: {self._symbols})",
                MessageLevel.WARNING,
            )
            return

        self._bars[bar.symbol].append(bar)
        self._last_bar_time = bar.datetime

        if isinstance(self._broker, PaperBroker):
            self._broker.set_price(bar.symbol, bar.close)

        account = self._broker.get_account()
        self._live_risk.reset_daily(account.equity)

        if self._live_risk.check_circuit_breaker():
            return

        if len(self._bars[bar.symbol]) < MIN_BARS_REQUIRED:
            return

        df = self._bars_to_df(bar.symbol)

        # Check pending orders for this symbol
        if bar.symbol in self._pending_orders:
            await self._check_pending_order(bar.symbol)

        position = self._positions.get(bar.symbol)
        if position:
            await self._check_exit(bar, position)

        signal, details = self._sig_gen.generate(df, len(df) - 1, bool(position))

        # Check if we should open a new position
        can_open = (
            position is None
            and bar.symbol not in self._pending_orders
            and signal in (Signal.BUY, Signal.SELL)
            and (signal != Signal.SELL or self._allow_short)  # Skip SELL if shorting disabled
        )
        if can_open:
            await self._open_position(bar, signal, df)

        # Emit bar event
        trend = str(details.get("trend", "N/A"))
        current_pos = self._positions.get(bar.symbol)
        await self._cb.emit_bar(BarEvent(bar=bar, signal=signal, trend=trend, position=current_pos))
        await self._emit_stats()
        await self._emit_account()
        await self._emit_risk()
        await self._emit_clock()

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

        exit_params = self._sig_gen.calc_exit(direction, price, df, self._rr_ratio)
        stop, tp = exit_params.stop_loss, exit_params.take_profit
        size = self._pos_sizer.calc_size(price, stop)

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

        # Use bracket order with SL/TP so Alpaca manages exits
        order = Order(
            symbol=bar.symbol,
            direction=direction,
            size=size,
            order_type="MARKET",
            stop_loss=stop,
            take_profit=tp,
        )
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
        elif result.status == "PENDING":
            self._pending_orders[bar.symbol] = PendingOrder(
                order_id=result.order_id,
                symbol=bar.symbol,
                direction=direction,
                expected_price=price,
                stop_loss=stop,
                take_profit=tp,
                entry_index=idx,
                entry_time=bar.datetime,
            )
            await self._emit_message(f"⏳ Order pending (ID: {result.order_id})", MessageLevel.WARNING)
        else:
            await self._emit_message(f"✗ Order {result.status}: {result.message}", MessageLevel.ERROR)

    async def _check_pending_order(self, symbol: str) -> None:
        """Poll broker for pending order status and create position if filled."""
        pending = self._pending_orders.get(symbol)
        if pending is None:
            return

        result = self._broker.get_order(pending.order_id)
        if result is None:
            return

        if result.status == "FILLED":
            del self._pending_orders[symbol]
            self._positions[symbol] = Position(
                entry_price=result.filled_price or pending.expected_price,
                entry_index=pending.entry_index,
                entry_time=pending.entry_time,
                direction=pending.direction,
                size=result.filled_size,
                stop_loss=pending.stop_loss,
                take_profit=pending.take_profit,
                initial_stop_loss=pending.stop_loss,
            )
            self._live_risk.update_position_count(len(self._positions))
            await self._emit_message(f"✓ Order filled at ${result.filled_price:.2f}", MessageLevel.SUCCESS)
            sounds.play(sounds.BUY if pending.direction == "LONG" else sounds.SELL)
        elif result.status in ("REJECTED", "CANCELLED"):
            del self._pending_orders[symbol]
            await self._emit_message(f"✗ Order {result.status}: {result.message}", MessageLevel.ERROR)

    async def _check_exit(self, bar: Bar, position: Position) -> None:
        """Check if position should be exited."""
        # Skip if close order already pending for this symbol
        if bar.symbol in self._pending_closes:
            return

        # Sync with broker - check if position was closed by bracket order (SL/TP on Alpaca)
        broker_pos = self._broker.get_position(bar.symbol)
        if broker_pos is None:
            # Position closed by Alpaca (bracket order SL/TP triggered)
            # Determine exit reason based on price action
            if position.direction == "LONG":
                exit_reason = "STOP_LOSS" if bar.low <= position.stop_loss else "TAKE_PROFIT"
            else:
                exit_reason = "STOP_LOSS" if bar.high >= position.stop_loss else "TAKE_PROFIT"

            # Calculate P&L and record trade
            exit_price = position.stop_loss if exit_reason == "STOP_LOSS" else position.take_profit
            pnl = (exit_price - position.entry_price) * position.size
            if position.direction == "SHORT":
                pnl = -pnl

            del self._positions[bar.symbol]
            self._live_risk.update_position_count(len(self._positions))
            self._live_risk.record_trade_pnl(pnl)
            await self._emit_message(
                f"✓ Position closed by Alpaca ({exit_reason}) at ${exit_price:.2f}, P&L: ${pnl:+.2f}",
                MessageLevel.SUCCESS if pnl > 0 else MessageLevel.WARNING,
            )
            sounds.play(sounds.PROFIT if pnl > 0 else sounds.LOSS)
            return

        should_exit = False
        exit_reason = ""

        # Skip internal SL/TP monitoring - Alpaca bracket order handles it
        # Only check time-based exits here

        # Check time-based exits if no SL/TP triggered
        if not should_exit:
            strategy_cfg = get_strategy_config()

            # Check TIME_EXIT: close after N minutes
            if strategy_cfg.time_exit_minutes > 0:
                hold_minutes = (bar.datetime - position.entry_time).total_seconds() / 60
                if hold_minutes >= strategy_cfg.time_exit_minutes:
                    should_exit, exit_reason = True, "TIME_EXIT"

            # Check EOD_EXIT: close before market close
            if not should_exit and strategy_cfg.eod_exit:
                clock = self._broker.get_clock()
                if clock and clock.is_open and clock.next_close:
                    minutes_to_close = (clock.next_close - bar.datetime).total_seconds() / 60
                    if 0 < minutes_to_close <= strategy_cfg.eod_exit_minutes_before:
                        should_exit, exit_reason = True, "EOD_EXIT"

        if should_exit:
            await self._close_position(bar, position, exit_reason)

    async def _close_position(self, bar: Bar, position: Position, reason: str) -> None:
        """Close an existing position."""
        if reason == "STOP_LOSS":
            exit_price = position.stop_loss
        elif reason == "TAKE_PROFIT":
            exit_price = position.take_profit
        else:
            # TIME_EXIT and EOD_EXIT use current market price
            exit_price = bar.close

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
                    size=position.size,
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
                    size=position.size,
                    pnl=pnl,
                    reason=reason,
                )
            )
            await self._emit_stats()

            sounds.play(sounds.PROFIT if pnl > 0 else sounds.LOSS)
            del self._positions[bar.symbol]
            self._pending_closes.discard(bar.symbol)
            self._live_risk.update_position_count(len(self._positions))

            if self._live_risk.check_circuit_breaker():
                await self._emit_message("⚠ CIRCUIT BREAKER TRIGGERED - Trading paused", MessageLevel.ERROR)
        elif result.status == "PENDING":
            self._pending_closes.add(bar.symbol)
            await self._emit_message(f"⏳ Close order pending (ID: {result.order_id})", MessageLevel.WARNING)
        else:
            await self._emit_message(f"✗ Close order {result.status}: {result.message}", MessageLevel.ERROR)

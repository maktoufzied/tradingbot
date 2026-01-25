"""Core trading engine."""

from collections import deque
from collections.abc import Collection
from datetime import datetime
from typing import Final

import polars as pl

from tradingbot.config import get_engine_config, get_health_config, get_strategy_config
from tradingbot.interfaces import BrokerProtocol, DataFeedProtocol
from tradingbot.types import Bar, BarOrigin, Direction, ExitReason, Order, PendingOrder, Position, Signal

from .. import sounds
from ..brokers.plugins.paper import PaperBroker
from ..feeds import DataFeed
from ..health import HealthChecker
from ..logging import get_logger
from ..risk import PositionSizer
from ..risk_manager import RiskManager
from ..signals import SignalGenerator
from ..state import (
    delete_position,
    end_session,
    get_last_session_info,
    load_positions,
    reconcile_positions,
    record_trade,
    save_position,
    set_circuit_breaker,
    start_session,
)
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

logger = get_logger(__name__)

MIN_BARS_REQUIRED: Final[int] = 20  # ~1.5 hours at 5m bars, enough for swing detection
MAX_BARS_HISTORY: Final[int] = 500


class TradingEngine:
    """Event-driven engine for real-time trading."""

    def __init__(
        self,
        symbols: Collection[str],
        broker: BrokerProtocol,
        feed: DataFeedProtocol,
        signal_generators: dict[str, SignalGenerator],
        position_sizers: dict[str, PositionSizer],
        risk_manager: RiskManager,
        rr_ratio: float = 2.0,
        dry_run: bool = False,
        allow_short: bool = False,
        callbacks: EngineCallbacks | None = None,
        persist_state: bool = True,
        strategy_names: dict[str, str] | None = None,
    ) -> None:
        self._symbols = list(set(symbols))
        self._dry_run = dry_run
        self._allow_short = allow_short
        self._broker = broker
        self._feed = feed
        self._sig_gens = signal_generators
        # Validate all symbols have position sizers
        missing_sizers = set(self._symbols) - set(position_sizers.keys())
        if missing_sizers:
            raise ValueError(f"Missing position sizers for: {', '.join(sorted(missing_sizers))}")
        self._pos_sizers = position_sizers
        self._risk_mgr = risk_manager
        self._rr_ratio = rr_ratio
        self._cb = callbacks or EngineCallbacks()
        self._persist_state = persist_state
        self._strategy_names = strategy_names or {}

        # State tracking
        self._positions: dict[str, Position] = {}
        self._pending_orders: dict[str, PendingOrder] = {}  # symbol -> pending entry order
        self._pending_closes: set[str] = set()  # symbols with pending close orders
        self._bars: dict[str, deque[Bar]] = {sym: deque(maxlen=MAX_BARS_HISTORY) for sym in self._symbols}
        self._running = False
        self._last_bar_time: datetime | None = None
        self._session_id: int | None = None

        # Health checker
        self._health_checker = HealthChecker(
            config=get_health_config(),
            broker=broker,
            feed=feed,
            risk_manager=risk_manager,
            get_positions_count=lambda: len(self._positions),
            get_last_bar_time=lambda: self._last_bar_time,
        )

    @property
    def symbols(self) -> list[str]:
        return self._symbols

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    @property
    def strategy_names(self) -> dict[str, str]:
        """Get per-symbol strategy name mapping."""
        return self._strategy_names

    async def _emit_message(self, message: str, level: MessageLevel = MessageLevel.INFO) -> None:
        await self._cb.emit_message(MessageEvent(message, level))

    async def _emit_stats(self) -> None:
        await self._cb.emit_stats_updated(
            StatsUpdatedEvent(
                pnl=self._risk_mgr.session_pnl,
                trades=self._risk_mgr.session_trades,
                winners=self._risk_mgr.session_winners,
                losers=self._risk_mgr.session_losers,
            )
        )

    async def _emit_account(self) -> None:
        account = self._broker.get_account()
        await self._cb.emit_account(
            AccountEvent(
                equity=account.equity,
                cash=account.cash,
                buying_power=account.buying_power,
                day_pnl=self._risk_mgr.session_pnl,
            )
        )

    async def _emit_risk(self) -> None:
        can_trade, blocked_reason = self._risk_mgr.can_open_position()
        await self._cb.emit_risk(
            RiskEvent(
                daily_loss_pct=self._risk_mgr.daily_pnl_pct,
                max_daily_loss_pct=self._risk_mgr._config.max_daily_loss_pct,
                open_positions=len(self._positions),
                max_positions=self._risk_mgr._config.max_open_positions,
                circuit_breaker_active=self._risk_mgr.check_circuit_breaker(),
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

        # Start session and check previous session state
        if self._persist_state:
            last_session = get_last_session_info()
            if last_session and not last_session["ended_gracefully"]:
                await self._emit_message(
                    f"Previous session {last_session['id']} did not end gracefully",
                    MessageLevel.WARNING,
                )
                if last_session["circuit_breaker_triggered"]:
                    await self._emit_message(
                        "Circuit breaker was triggered in previous session",
                        MessageLevel.WARNING,
                    )
            self._session_id = start_session()
            logger.info("Started session %d", self._session_id)

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
        self._risk_mgr.reset_daily(account.equity)

        # Sync today's trades from broker (if available)
        if hasattr(self._broker, "get_today_trades"):
            trades = self._broker.get_today_trades()
            for trade in trades:
                # Record trade stats
                self._risk_mgr.record_trade_pnl(trade.pnl)
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

        # End session
        if self._persist_state and self._session_id is not None:
            end_session(self._session_id)
            logger.info("Ended session %d", self._session_id)

        await self._cb.emit_stopped(EngineStoppedEvent(risk_manager=self._risk_mgr))

    async def close_position_manually(self, symbol: str) -> bool:
        """Close a position manually from UI command.

        Args:
            symbol: Symbol to close position for.

        Returns:
            True if position was closed, False if no position exists.
        """
        if symbol not in self._positions:
            logger.warning("No position to close for %s", symbol)
            return False

        # Prevent double-close if automatic exit is already pending
        if symbol in self._pending_closes:
            logger.warning("Close already pending for %s", symbol)
            return False

        position = self._positions[symbol]
        bars = self._bars.get(symbol)
        if not bars:
            logger.warning("No bar data available for %s", symbol)
            return False

        # Use the most recent bar for exit price
        last_bar = bars[-1]
        await self._close_position(last_bar, position, "MANUAL_EXIT")
        logger.info("Manually closed position for %s", symbol)
        return True

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
                    sig_gen = self._sig_gens.get(symbol)
                    if sig_gen:
                        signal, details = sig_gen.generate(hist_df, len(hist_df) - 1, False)
                        trend = str(details.get("trend", "NEUTRAL"))
                        await self._cb.emit_bar(BarEvent(bar=last_bar, signal=signal, trend=trend, position=None))
            except Exception as e:
                await self._emit_message(f"✗ {symbol}: {e}", MessageLevel.ERROR)

    async def _sync_broker_positions(self) -> None:
        """Sync existing positions from broker on startup with reconciliation."""
        broker_positions = self._broker.get_positions()
        broker_pos_dict = {bp.symbol: bp for bp in broker_positions if bp.symbol in self._symbols}

        # Load persisted positions for reconciliation
        local_positions: dict[str, Position] = {}
        if self._persist_state:
            local_positions = load_positions()
            if local_positions:
                await self._emit_message(
                    f"Loaded {len(local_positions)} persisted position(s)",
                    MessageLevel.INFO,
                )

            # Reconcile local with broker
            result = reconcile_positions(local_positions, broker_pos_dict)

            # Report reconciliation results
            if result.closed_externally:
                for symbol in result.closed_externally:
                    await self._emit_message(
                        f"⚠ {symbol} position closed externally, removed from local state",
                        MessageLevel.WARNING,
                    )
                    sounds.play(sounds.ALERT)

            if result.size_mismatches:
                for symbol, (local_size, broker_size) in result.size_mismatches.items():
                    await self._emit_message(
                        f"⚠ {symbol} size mismatch: local={local_size:.1f}, broker={broker_size:.1f}",
                        MessageLevel.WARNING,
                    )

            # Use local positions that matched or had size updated
            symbols_to_restore = result.matched + list(result.size_mismatches.keys())
            for symbol in symbols_to_restore:
                pos = local_positions[symbol]
                # Update size from broker if mismatched
                if symbol in result.size_mismatches:
                    broker_size = result.size_mismatches[symbol][1]
                    pos = Position(
                        entry_price=pos.entry_price,
                        entry_index=pos.entry_index,
                        entry_time=pos.entry_time,
                        direction=pos.direction,
                        size=broker_size,
                        stop_loss=pos.stop_loss,
                        take_profit=pos.take_profit,
                        initial_stop_loss=pos.initial_stop_loss,
                        remaining_size=broker_size,
                        partial_exits=pos.partial_exits,
                        triggered_levels=pos.triggered_levels,
                        high_water_mark=pos.high_water_mark,
                    )
                    save_position(symbol, pos)
                self._positions[symbol] = pos
                await self._emit_message(
                    f"✓ Restored: {symbol} {pos.direction} {pos.get_remaining_size():.1f} @ ${pos.entry_price:.2f}",
                    MessageLevel.SUCCESS,
                )

        # Adopt broker positions not in local state
        for bp in broker_positions:
            if bp.symbol not in self._symbols:
                continue
            if bp.symbol in self._positions:
                continue

            # Calculate stop/TP from current market structure
            sig_gen = self._sig_gens.get(bp.symbol)
            if sig_gen and bp.symbol in self._bars and len(self._bars[bp.symbol]) >= MIN_BARS_REQUIRED:
                df = self._bars_to_df(bp.symbol)
                exit_params = sig_gen.calc_exit(bp.direction, bp.avg_entry_price, df, self._rr_ratio)
                stop, tp = exit_params.stop_loss, exit_params.take_profit
            else:
                stop = bp.avg_entry_price * (0.98 if bp.direction == "LONG" else 1.02)
                tp = bp.avg_entry_price * (1.04 if bp.direction == "LONG" else 0.96)

            position = Position(
                entry_price=bp.avg_entry_price,
                entry_index=0,
                entry_time=datetime.now(),
                direction=bp.direction,
                size=bp.size,
                stop_loss=stop,
                take_profit=tp,
                initial_stop_loss=stop,
            )
            self._positions[bp.symbol] = position

            # Persist adopted position
            if self._persist_state:
                save_position(bp.symbol, position)

            await self._emit_message(
                f"⚠ Adopted: {bp.symbol} {bp.direction} {bp.size:.1f} @ ${bp.avg_entry_price:.2f}",
                MessageLevel.WARNING,
            )

        if self._positions:
            self._risk_mgr.update_position_count(len(self._positions))

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
        self._risk_mgr.reset_daily(account.equity)

        if self._risk_mgr.check_circuit_breaker():
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

        # Get the signal generator for this symbol
        sig_gen = self._sig_gens.get(bar.symbol)
        if sig_gen is None:
            return  # No strategy configured for this symbol
        signal, details = sig_gen.generate(df, len(df) - 1, bool(position))

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

        sig_gen = self._sig_gens.get(bar.symbol)
        if sig_gen is None:
            return  # No strategy configured
        exit_params = sig_gen.calc_exit(direction, price, df, self._rr_ratio)
        stop, tp = exit_params.stop_loss, exit_params.take_profit
        pos_sizer = self._pos_sizers.get(bar.symbol)
        if pos_sizer is None:
            logger.warning(f"No position sizer for {bar.symbol}")
            return
        size = pos_sizer.calc_size(price, stop, df)

        account = self._broker.get_account()
        self._risk_mgr.update_position_count(len(self._positions))
        can_trade, reason = self._risk_mgr.can_open_position()
        size, was_capped = self._risk_mgr.cap_position_size(size, price, account.equity)

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
            position = Position(
                entry_price=price,
                entry_index=idx,
                entry_time=bar.datetime,
                direction=direction,
                size=size,
                stop_loss=stop,
                take_profit=tp,
                initial_stop_loss=stop,
            )
            self._positions[bar.symbol] = position
            self._risk_mgr.update_position_count(len(self._positions))
            if self._persist_state:
                save_position(bar.symbol, position)
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
            position = Position(
                entry_price=result.filled_price or price,
                entry_index=idx,
                entry_time=bar.datetime,
                direction=direction,
                size=result.filled_size,
                stop_loss=stop,
                take_profit=tp,
                initial_stop_loss=stop,
            )
            self._positions[bar.symbol] = position
            self._risk_mgr.update_position_count(len(self._positions))
            if self._persist_state:
                save_position(bar.symbol, position)
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
            position = Position(
                entry_price=result.filled_price or pending.expected_price,
                entry_index=pending.entry_index,
                entry_time=pending.entry_time,
                direction=pending.direction,
                size=result.filled_size,
                stop_loss=pending.stop_loss,
                take_profit=pending.take_profit,
                initial_stop_loss=pending.stop_loss,
            )
            self._positions[symbol] = position
            self._risk_mgr.update_position_count(len(self._positions))
            if self._persist_state:
                save_position(symbol, position)
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
                reason: ExitReason = "STOP_LOSS" if bar.low <= position.stop_loss else "TAKE_PROFIT"
            else:
                reason = "STOP_LOSS" if bar.high >= position.stop_loss else "TAKE_PROFIT"

            # Calculate P&L and record trade
            exit_price = position.stop_loss if reason == "STOP_LOSS" else position.take_profit
            pnl = (exit_price - position.entry_price) * position.size
            if position.direction == "SHORT":
                pnl = -pnl
            pnl_pct = pnl / (position.entry_price * position.size) * 100

            del self._positions[bar.symbol]
            self._risk_mgr.update_position_count(len(self._positions))
            self._risk_mgr.record_trade_pnl(pnl)

            # Persist state changes
            if self._persist_state:
                delete_position(bar.symbol)
                record_trade(
                    symbol=bar.symbol,
                    direction=position.direction,
                    entered_at=position.entry_time,
                    exited_at=bar.datetime,
                    entry_price=position.entry_price,
                    exit_price=exit_price,
                    size=position.size,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    exit_reason=reason,
                    strategy=self._strategy_names.get(bar.symbol),
                )

            await self._emit_message(
                f"✓ Position closed by Alpaca ({reason}) at ${exit_price:.2f}, P&L: ${pnl:+.2f}",
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
        # Map reason string to ExitReason type
        exit_reason_map: dict[str, ExitReason] = {
            "STOP_LOSS": "STOP_LOSS",
            "TAKE_PROFIT": "TAKE_PROFIT",
            "TIME_EXIT": "TIME_EXIT",
            "EOD_EXIT": "EOD_EXIT",
            "PARTIAL_EXIT": "PARTIAL_EXIT",
            "MANUAL_EXIT": "TIME_EXIT",  # Manual exits use TIME_EXIT for persistence
        }
        exit_reason: ExitReason = exit_reason_map.get(reason, "TIME_EXIT")

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
            pnl_pct = pnl / (position.entry_price * position.size) * 100
            self._risk_mgr.record_trade_pnl(pnl)

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
            self._risk_mgr.update_position_count(len(self._positions))

            # Persist state changes
            if self._persist_state:
                delete_position(bar.symbol)
                record_trade(
                    symbol=bar.symbol,
                    direction=position.direction,
                    entered_at=position.entry_time,
                    exited_at=bar.datetime,
                    entry_price=position.entry_price,
                    exit_price=exit_price,
                    size=position.size,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    exit_reason=exit_reason,
                    strategy=self._strategy_names.get(bar.symbol),
                )
            return

        close_direction: Direction = "SHORT" if position.direction == "LONG" else "LONG"
        order = Order(symbol=bar.symbol, direction=close_direction, size=position.size, order_type="MARKET")
        result = self._broker.submit_order(order)

        if result.status == "FILLED":
            actual_exit = result.filled_price or exit_price
            pnl = (actual_exit - position.entry_price) * position.size
            if position.direction == "SHORT":
                pnl = -pnl
            pnl_pct = pnl / (position.entry_price * position.size) * 100
            self._risk_mgr.record_trade_pnl(pnl)

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
            self._risk_mgr.update_position_count(len(self._positions))

            # Persist state changes
            if self._persist_state:
                delete_position(bar.symbol)
                record_trade(
                    symbol=bar.symbol,
                    direction=position.direction,
                    entered_at=position.entry_time,
                    exited_at=bar.datetime,
                    entry_price=position.entry_price,
                    exit_price=actual_exit,
                    size=position.size,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    exit_reason=exit_reason,
                    strategy=self._strategy_names.get(bar.symbol),
                )

            if self._risk_mgr.check_circuit_breaker():
                await self._emit_message("⚠ CIRCUIT BREAKER TRIGGERED - Trading paused", MessageLevel.ERROR)
                if self._persist_state and self._session_id:
                    set_circuit_breaker(self._session_id)
        elif result.status == "PENDING":
            self._pending_closes.add(bar.symbol)
            await self._emit_message(f"⏳ Close order pending (ID: {result.order_id})", MessageLevel.WARNING)
        else:
            await self._emit_message(f"✗ Close order {result.status}: {result.message}", MessageLevel.ERROR)

"""Engine Adapter - Transforms engine events to UI messages.

The adapter registers with the engine's callback system and transforms
each event into the appropriate UI message type, then pushes to the hub.
"""

from datetime import UTC, datetime

from tradingbot._components.engine.callbacks import EngineCallbacks
from tradingbot._components.engine.events import (
    AccountEvent,
    BarEvent,
    ClockEvent,
    EngineStartedEvent,
    EngineStoppedEvent,
    MessageEvent,
    RiskEvent,
    SignalEvent,
    StatsUpdatedEvent,
    TradeClosedEvent,
)
from tradingbot.types import Bar, BarOrigin

from .hub import EventHub
from .types import (
    AccountSnapshot,
    ChartUpdate,
    PositionUpdate,
    RiskStatus,
    SessionStats,
    SystemStatus,
    TickerUpdate,
    TradeAlert,
)


class EngineAdapter:
    """Transforms engine events into UI messages for the hub.

    The adapter connects the trading engine to the UI layer without
    modifying the engine. It registers callbacks that transform each
    engine event into the appropriate UI message type.

    Usage:
        hub = EventHub()
        adapter = EngineAdapter(hub, symbols=["AAPL", "MSFT"])
        engine = TradingEngine(..., callbacks=adapter.callbacks)
    """

    def __init__(self, hub: EventHub, symbols: list[str], *, is_replay: bool = False) -> None:
        self.hub = hub
        self.symbols = symbols
        self.is_replay = is_replay
        self.callbacks = EngineCallbacks()

        # Tracking state
        self._bars_received = 0
        self._errors = 0
        self._start_time = datetime.now(UTC)
        self._last_bar_time: datetime | None = None
        self._session_open_prices: dict[str, float] = {}
        self._session_highs: dict[str, float] = {}
        self._session_lows: dict[str, float] = {}
        self._initial_equity: float | None = None
        self._ohlc_history: dict[str, dict[str, list[float]]] = {
            s: {"opens": [], "highs": [], "lows": [], "closes": []} for s in symbols
        }
        self._timestamp_history: dict[str, list[datetime]] = {s: [] for s in symbols}
        self._equity_curve: list[float] = []
        self._trade_pnls: list[float] = []
        self._current_streak = 0
        self._market_open = True  # Updated from clock events
        self._market_next_change: datetime | None = None

        # Wire up all engine events
        self.callbacks.on_started(self._on_started)
        self.callbacks.on_stopped(self._on_stopped)
        self.callbacks.on_bar(self._on_bar)
        self.callbacks.on_signal(self._on_signal)
        self.callbacks.on_trade_closed(self._on_trade_closed)
        self.callbacks.on_stats_updated(self._on_stats_updated)
        self.callbacks.on_message(self._on_message)
        self.callbacks.on_account(self._on_account_event)
        self.callbacks.on_risk(self._on_risk_event)
        self.callbacks.on_clock(self._on_clock_event)

    async def _on_started(self, event: EngineStartedEvent) -> None:
        """Initialize hub state on engine start."""
        self._start_time = datetime.now(UTC)

        # Initialize empty positions for all symbols
        for symbol in event.symbols:
            await self.hub.update_position(PositionUpdate.empty(symbol))

        # Set initial status
        await self.hub.update_status(
            SystemStatus(
                feed_connected=True,
                broker_connected=True,
                market_open=self._market_open,
                market_next_change=self._market_next_change,
                uptime_seconds=0,
                bars_received=0,
                errors_count=0,
                is_replay=self.is_replay,
                replay_time=None,
            )
        )

        # Initialize risk status
        await self.hub.update_risk(RiskStatus.default())

    async def _on_stopped(self, event: EngineStoppedEvent) -> None:
        """Handle engine stop - update final stats."""
        rm = event.risk_manager

        # Final stats from risk manager
        final_stats = SessionStats(
            total_pnl=rm.session_pnl,
            total_pnl_pct=rm.session_return_pct * 100,
            trade_count=rm.session_trades,
            win_count=rm.session_winners,
            loss_count=rm.session_losers,
            win_rate=rm.session_win_rate * 100,
            profit_factor=rm.session_profit_factor,
            largest_win=max((p for p in self._trade_pnls if p > 0), default=0.0),
            largest_loss=min((p for p in self._trade_pnls if p < 0), default=0.0),
            current_streak=self._current_streak,
            equity_curve=self._equity_curve[-60:],
        )
        await self.hub.update_stats(final_stats)

        # Update status to disconnected
        await self.hub.update_status(
            SystemStatus(
                feed_connected=False,
                broker_connected=False,
                market_open=False,
                market_next_change=self._market_next_change,
                uptime_seconds=int((datetime.now(UTC) - self._start_time).total_seconds()),
                bars_received=self._bars_received,
                errors_count=self._errors,
                is_replay=self.is_replay,
                replay_time=self._last_bar_time,
            )
        )

    async def _on_bar(self, event: BarEvent) -> None:
        """Transform BarEvent -> TickerUpdate + PositionUpdate."""
        bar = event.bar

        # REALTIME bars: update chart and send lightweight ticker update
        if bar.origin == BarOrigin.REALTIME:
            await self._update_chart(bar)

            # Send real-time price update to TUI/web (no session stats changes)
            if bar.symbol in self._session_open_prices:
                open_price = self._session_open_prices[bar.symbol]
                change = bar.close - open_price
                change_pct = (change / open_price * 100) if open_price > 0 else 0.0

                ticker = TickerUpdate(
                    symbol=bar.symbol,
                    price=bar.close,
                    change=change,
                    change_pct=change_pct,
                    high=max(self._session_highs.get(bar.symbol, bar.high), bar.high),
                    low=min(self._session_lows.get(bar.symbol, bar.low), bar.low),
                    volume=bar.volume,
                    timestamp=bar.datetime,
                    trend="NEUTRAL",
                    signal="HOLD",
                )
                await self.hub.update_ticker(ticker)
            return

        # AGGREGATED bars: full processing
        self._bars_received += 1
        self._last_bar_time = bar.datetime

        # Track session prices
        if bar.symbol not in self._session_open_prices:
            self._session_open_prices[bar.symbol] = bar.open
            self._session_highs[bar.symbol] = bar.high
            self._session_lows[bar.symbol] = bar.low
        else:
            self._session_highs[bar.symbol] = max(self._session_highs[bar.symbol], bar.high)
            self._session_lows[bar.symbol] = min(self._session_lows[bar.symbol], bar.low)

        # Calculate change from session open
        open_price = self._session_open_prices[bar.symbol]
        change = bar.close - open_price
        change_pct = (change / open_price * 100) if open_price > 0 else 0.0

        # Map signal enum to string
        raw_signal = event.signal.value if hasattr(event.signal, "value") else str(event.signal)
        signal_str = raw_signal.upper() if raw_signal.upper() in ("BUY", "SELL", "HOLD") else "HOLD"

        # Map trend to standard format
        trend = event.trend.upper() if event.trend else "NEUTRAL"
        if trend not in ("BULLISH", "BEARISH", "NEUTRAL"):
            trend = "NEUTRAL"

        ticker = TickerUpdate(
            symbol=bar.symbol,
            price=bar.close,
            change=change,
            change_pct=change_pct,
            high=self._session_highs[bar.symbol],
            low=self._session_lows[bar.symbol],
            volume=bar.volume,
            timestamp=bar.datetime,
            trend=trend,  # type: ignore[arg-type]
            signal=signal_str,  # type: ignore[arg-type]
        )
        await self.hub.update_ticker(ticker)

        # Track price history for charts
        await self._update_chart(bar)

        # Update position if exists
        pos = event.position
        if pos:
            current_price = bar.close
            if pos.direction == "LONG":
                unrealized = (current_price - pos.entry_price) * pos.size
            else:
                unrealized = (pos.entry_price - current_price) * pos.size

            position_value = pos.entry_price * pos.size
            unrealized_pct = (unrealized / position_value * 100) if position_value > 0 else 0.0
            hold_mins = int((bar.datetime - pos.entry_time).total_seconds() / 60)
            risk_amount = abs(pos.entry_price - pos.stop_loss) * pos.size

            position_update = PositionUpdate(
                symbol=bar.symbol,
                direction=pos.direction,
                entry_price=pos.entry_price,
                current_price=current_price,
                size=pos.size,
                stop_loss=pos.stop_loss,
                take_profit=pos.take_profit,
                unrealized_pnl=unrealized,
                unrealized_pnl_pct=unrealized_pct,
                holding_minutes=hold_mins,
                risk_amount=risk_amount,
                is_open=True,
            )
            await self.hub.update_position(position_update)
        else:
            # No position - send empty update
            await self.hub.update_position(PositionUpdate.empty(bar.symbol))

        # Update system status periodically
        uptime = int((datetime.now(UTC) - self._start_time).total_seconds())
        await self.hub.update_status(
            SystemStatus(
                feed_connected=True,
                broker_connected=True,
                market_open=self._market_open,
                market_next_change=self._market_next_change,
                uptime_seconds=uptime,
                bars_received=self._bars_received,
                errors_count=self._errors,
                is_replay=self.is_replay,
                replay_time=bar.datetime if self.is_replay else None,
            )
        )

    async def _on_signal(self, event: SignalEvent) -> None:
        """Transform SignalEvent -> TradeAlert."""
        alert_type = "BLOCKED" if event.blocked else "ENTRY"

        alert = TradeAlert(
            type=alert_type,  # type: ignore[arg-type]
            symbol=event.symbol,
            direction=event.direction,
            price=event.entry,
            size=event.size,
            stop_loss=event.stop,
            take_profit=event.tp,
            pnl=None,
            pnl_pct=None,
            reason=event.reason if event.blocked else None,
            strategy=None,
            timestamp=datetime.now(UTC),
            is_winner=None,
        )
        await self.hub.add_trade(alert)

    async def _on_trade_closed(self, event: TradeClosedEvent) -> None:
        """Transform TradeClosedEvent -> TradeAlert."""
        position_value = event.entry * event.size
        pnl_pct = (event.pnl / position_value * 100) if position_value > 0 else 0.0
        is_winner = event.pnl > 0

        # Track for stats
        self._trade_pnls.append(event.pnl)

        # Update streak
        if is_winner:
            self._current_streak = max(1, self._current_streak + 1)
        else:
            self._current_streak = min(-1, self._current_streak - 1)

        alert = TradeAlert(
            type="EXIT",
            symbol=event.symbol,
            direction=event.direction,
            price=event.exit_price,
            size=event.size,
            stop_loss=None,
            take_profit=None,
            pnl=event.pnl,
            pnl_pct=pnl_pct,
            reason=event.reason,
            strategy=None,
            timestamp=datetime.now(UTC),
            is_winner=is_winner,
        )
        await self.hub.add_trade(alert)

        # Clear position
        await self.hub.update_position(PositionUpdate.empty(event.symbol))

    async def _on_stats_updated(self, event: StatsUpdatedEvent) -> None:
        """Transform StatsUpdatedEvent -> SessionStats."""
        win_rate = (event.winners / event.trades * 100) if event.trades > 0 else 0.0

        # Track equity curve
        self._equity_curve.append(event.pnl)
        self._equity_curve = self._equity_curve[-120:]

        # Calculate profit factor from trades
        wins = [p for p in self._trade_pnls if p > 0]
        losses = [abs(p) for p in self._trade_pnls if p < 0]
        total_wins = sum(wins) if wins else 0.0
        total_losses = sum(losses) if losses else 0.0
        # PF = wins/losses. Use -1 as sentinel for "not applicable" (no losses yet)
        profit_factor = total_wins / total_losses if total_losses > 0 else -1.0

        # Calculate return % using initial equity
        total_pnl_pct = (event.pnl / self._initial_equity * 100) if self._initial_equity else 0.0

        stats = SessionStats(
            total_pnl=event.pnl,
            total_pnl_pct=total_pnl_pct,
            trade_count=event.trades,
            win_count=event.winners,
            loss_count=event.losers,
            win_rate=win_rate,
            profit_factor=profit_factor,
            largest_win=max((p for p in self._trade_pnls if p > 0), default=0.0),
            largest_loss=min((p for p in self._trade_pnls if p < 0), default=0.0),
            current_streak=self._current_streak,
            equity_curve=self._equity_curve.copy(),
        )
        await self.hub.update_stats(stats)

    async def _on_message(self, event: MessageEvent) -> None:
        """Forward messages to hub for TUI/web display and track errors."""
        from .logging import log_engine_message

        # Broadcast message to all UI clients (TUI and web)
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": event.level.value.upper(),
            "message": event.message,
        }
        await self.hub.broadcast_log(log_entry)

        # Also write to log file
        log_engine_message(event.level.value, event.message)

        # Track error count for status display
        if event.level.value == "error":
            self._errors += 1
            await self.hub.update_status(
                SystemStatus(
                    feed_connected=True,
                    broker_connected=True,
                    market_open=self._market_open,
                    market_next_change=self._market_next_change,
                    uptime_seconds=int((datetime.now(UTC) - self._start_time).total_seconds()),
                    bars_received=self._bars_received,
                    errors_count=self._errors,
                    is_replay=self.is_replay,
                    replay_time=self._last_bar_time,
                )
            )

    async def _on_account_event(self, event: AccountEvent) -> None:
        """Transform AccountEvent -> AccountSnapshot."""
        # Track initial equity for return % calculation
        if self._initial_equity is None:
            self._initial_equity = event.equity - event.day_pnl

        positions_value = event.equity - event.cash

        # Calculate total unrealized P&L from open positions
        unrealized_pnl = sum(pos.unrealized_pnl for pos in self.hub._positions.values() if pos.is_open)

        snapshot = AccountSnapshot(
            equity=event.equity,
            cash=event.cash,
            buying_power=event.buying_power,
            realized_pnl=event.day_pnl,
            unrealized_pnl=unrealized_pnl,
            positions_value=positions_value,
        )
        await self.hub.update_account(snapshot)

    async def _on_risk_event(self, event: RiskEvent) -> None:
        """Transform RiskEvent -> RiskStatus."""
        status = RiskStatus(
            daily_loss_pct=event.daily_loss_pct * 100,  # Convert to percentage
            max_daily_loss_pct=event.max_daily_loss_pct * 100,
            open_positions=event.open_positions,
            max_positions=event.max_positions,
            circuit_breaker_active=event.circuit_breaker_active,
            can_trade=event.can_trade,
            blocked_reason=event.blocked_reason,
        )
        await self.hub.update_risk(status)

    async def _on_clock_event(self, event: ClockEvent) -> None:
        """Update market clock status."""
        self._market_open = event.is_open
        self._market_next_change = event.next_close if event.is_open else event.next_open

    # --- Account Updates (called externally) ---

    async def update_account(self, account: AccountSnapshot) -> None:
        """Update account info from broker."""
        await self.hub.update_account(account)

    async def update_risk(self, risk: RiskStatus) -> None:
        """Update risk status from risk manager."""
        await self.hub.update_risk(risk)

    # --- Chart Updates ---

    async def _update_chart(self, bar: Bar) -> None:
        """Update chart with new bar data."""
        if bar.symbol not in self._ohlc_history:
            return

        ohlc = self._ohlc_history[bar.symbol]
        max_bars = 120

        # Update OHLC history
        ohlc["opens"].append(bar.open)
        ohlc["highs"].append(bar.high)
        ohlc["lows"].append(bar.low)
        ohlc["closes"].append(bar.close)
        ohlc["opens"] = ohlc["opens"][-max_bars:]
        ohlc["highs"] = ohlc["highs"][-max_bars:]
        ohlc["lows"] = ohlc["lows"][-max_bars:]
        ohlc["closes"] = ohlc["closes"][-max_bars:]

        self._timestamp_history[bar.symbol].append(bar.datetime)
        self._timestamp_history[bar.symbol] = self._timestamp_history[bar.symbol][-max_bars:]

        # Send chart update
        chart = ChartUpdate(
            symbol=bar.symbol,
            timestamps=self._timestamp_history[bar.symbol].copy(),
            opens=ohlc["opens"].copy(),
            highs=ohlc["highs"].copy(),
            lows=ohlc["lows"].copy(),
            closes=ohlc["closes"].copy(),
            swing_highs=[],
            swing_lows=[],
        )
        await self.hub.update_chart(chart)

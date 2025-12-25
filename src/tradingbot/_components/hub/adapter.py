"""Engine Adapter - Transforms engine events to UI messages.

The adapter registers with the engine's callback system and transforms
each event into the appropriate UI message type, then pushes to the hub.
"""

from datetime import UTC, datetime

from tradingbot._components.engine.callbacks import EngineCallbacks
from tradingbot._components.engine.events import (
    AccountEvent,
    BarEvent,
    EngineStartedEvent,
    EngineStoppedEvent,
    MessageEvent,
    RiskEvent,
    SignalEvent,
    StatsUpdatedEvent,
    TradeClosedEvent,
)

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
        self._price_history: dict[str, list[float]] = {s: [] for s in symbols}
        self._timestamp_history: dict[str, list[datetime]] = {s: [] for s in symbols}
        self._equity_curve: list[float] = []
        self._trade_pnls: list[float] = []
        self._current_streak = 0

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
                market_open=True,
                market_next_change=None,
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
            largest_win=max(self._trade_pnls) if self._trade_pnls else 0.0,
            largest_loss=min(self._trade_pnls) if self._trade_pnls else 0.0,
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
                market_next_change=None,
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
        if bar.symbol in self._price_history:
            self._price_history[bar.symbol].append(bar.close)
            self._price_history[bar.symbol] = self._price_history[bar.symbol][-120:]
            self._timestamp_history[bar.symbol].append(bar.datetime)
            self._timestamp_history[bar.symbol] = self._timestamp_history[bar.symbol][-120:]

            # Update chart data
            chart = ChartUpdate(
                symbol=bar.symbol,
                prices=self._price_history[bar.symbol].copy(),
                timestamps=self._timestamp_history[bar.symbol].copy(),
                swing_highs=[],
                swing_lows=[],
            )
            await self.hub.update_chart(chart)

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
                market_open=True,
                market_next_change=None,
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
        profit_factor = (total_wins / total_losses) if total_losses > 0 else 0.0

        stats = SessionStats(
            total_pnl=event.pnl,
            total_pnl_pct=0.0,  # Need starting equity for this
            trade_count=event.trades,
            win_count=event.winners,
            loss_count=event.losers,
            win_rate=win_rate,
            profit_factor=profit_factor,
            largest_win=max(self._trade_pnls) if self._trade_pnls else 0.0,
            largest_loss=min(self._trade_pnls) if self._trade_pnls else 0.0,
            current_streak=self._current_streak,
            equity_curve=self._equity_curve.copy(),
        )
        await self.hub.update_stats(stats)

    async def _on_message(self, event: MessageEvent) -> None:
        """Track errors from message events."""
        if event.level.value == "error":
            self._errors += 1
            await self.hub.update_status(
                SystemStatus(
                    feed_connected=True,
                    broker_connected=True,
                    market_open=True,
                    market_next_change=None,
                    uptime_seconds=int((datetime.now(UTC) - self._start_time).total_seconds()),
                    bars_received=self._bars_received,
                    errors_count=self._errors,
                    is_replay=self.is_replay,
                    replay_time=self._last_bar_time,
                )
            )

    async def _on_account_event(self, event: AccountEvent) -> None:
        """Transform AccountEvent -> AccountSnapshot."""
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

    # --- Account Updates (called externally) ---

    async def update_account(self, account: AccountSnapshot) -> None:
        """Update account info from broker."""
        await self.hub.update_account(account)

    async def update_risk(self, risk: RiskStatus) -> None:
        """Update risk status from risk manager."""
        await self.hub.update_risk(risk)

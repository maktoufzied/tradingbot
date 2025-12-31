"""Event Hub - Central dispatcher with state management.

The hub is the single source of truth for all UI state. It receives
updates from the engine adapter, maintains state, and broadcasts
to all registered callbacks and WebSocket clients.
"""

import asyncio
import contextlib
import json
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from tradingbot._components.logging import get_logger

from .types import (
    AccountSnapshot,
    ChartUpdate,
    ConnectionStateEnum,
    GlobalState,
    PositionUpdate,
    RiskStatus,
    SessionStats,
    StrategyInfo,
    SystemStatus,
    TickerUpdate,
    TradeAlert,
    UIChannel,
)

logger = get_logger(__name__)

type Unsubscribe = Callable[[], None]
type SyncCallback = Callable[[Any], None]
type AsyncCallback = Callable[[Any], Awaitable[None]]
type Callback = SyncCallback | AsyncCallback


@dataclass
class EventHub:
    """Central event dispatcher with state management.

    The hub maintains global state and broadcasts updates to all registered
    callbacks and WebSocket clients. New clients receive a full state snapshot
    on connection.

    Usage:
        hub = EventHub()

        # Register callbacks
        unsubscribe = hub.on_ticker(lambda t: print(f"{t.symbol}: {t.price}"))

        # Later, unsubscribe
        unsubscribe()
    """

    _callbacks: dict[UIChannel, list[Callback]] = field(default_factory=lambda: defaultdict(list))
    _websockets: set[Any] = field(default_factory=set)

    # State storage
    _tickers: dict[str, TickerUpdate] = field(default_factory=dict)
    _positions: dict[str, PositionUpdate] = field(default_factory=dict)
    _stats: SessionStats | None = field(default=None)
    _account: AccountSnapshot | None = field(default=None)
    _risk: RiskStatus | None = field(default=None)
    _status: SystemStatus | None = field(default=None)
    _charts: dict[str, ChartUpdate] = field(default_factory=dict)
    _recent_trades: list[TradeAlert] = field(default_factory=list)
    _strategy: StrategyInfo | None = field(default=None)

    # --- Callback Registration ---

    def on(self, channel: UIChannel, callback: Callback) -> Unsubscribe:
        """Register callback for a channel. Returns unsubscribe function."""
        # Prevent duplicate callbacks
        if callback not in self._callbacks[channel]:
            self._callbacks[channel].append(callback)

        def unsubscribe() -> None:
            with contextlib.suppress(ValueError):
                self._callbacks[channel].remove(callback)

        return unsubscribe

    def on_ticker(self, callback: Callback) -> Unsubscribe:
        """Register callback for ticker updates."""
        return self.on(UIChannel.TICKER, callback)

    def on_position(self, callback: Callback) -> Unsubscribe:
        """Register callback for position updates."""
        return self.on(UIChannel.POSITION, callback)

    def on_trade(self, callback: Callback) -> Unsubscribe:
        """Register callback for trade alerts."""
        return self.on(UIChannel.TRADE, callback)

    def on_stats(self, callback: Callback) -> Unsubscribe:
        """Register callback for session stats updates."""
        return self.on(UIChannel.STATS, callback)

    def on_account(self, callback: Callback) -> Unsubscribe:
        """Register callback for account updates."""
        return self.on(UIChannel.ACCOUNT, callback)

    def on_risk(self, callback: Callback) -> Unsubscribe:
        """Register callback for risk status updates."""
        return self.on(UIChannel.RISK, callback)

    def on_status(self, callback: Callback) -> Unsubscribe:
        """Register callback for system status updates."""
        return self.on(UIChannel.STATUS, callback)

    def on_chart(self, callback: Callback) -> Unsubscribe:
        """Register callback for chart data updates."""
        return self.on(UIChannel.CHART, callback)

    def on_log(self, callback: Callback) -> Unsubscribe:
        """Register callback for log messages."""
        return self.on(UIChannel.LOG, callback)

    # --- State Access ---

    def get_state(self) -> GlobalState:
        """Get complete state snapshot for new clients."""
        return GlobalState(
            tickers=self._tickers.copy(),
            positions=self._positions.copy(),
            stats=self._stats or SessionStats.empty(),
            account=self._account or AccountSnapshot.empty(),
            risk=self._risk or RiskStatus.default(),
            status=self._status or SystemStatus.default(),
            charts=self._charts.copy(),
            recent_trades=self._recent_trades.copy(),
            strategy=self._strategy or StrategyInfo.default(),
        )

    def set_strategy(self, strategy: StrategyInfo) -> None:
        """Set the strategy info (called once at startup)."""
        self._strategy = strategy

    def get_ticker(self, symbol: str) -> TickerUpdate | None:
        """Get latest ticker for symbol."""
        return self._tickers.get(symbol)

    def get_position(self, symbol: str) -> PositionUpdate | None:
        """Get position for symbol."""
        return self._positions.get(symbol)

    def get_stats(self) -> SessionStats:
        """Get current session stats."""
        return self._stats or SessionStats.empty()

    def get_account(self) -> AccountSnapshot:
        """Get current account snapshot."""
        return self._account or AccountSnapshot.empty()

    def get_risk(self) -> RiskStatus:
        """Get current risk status."""
        return self._risk or RiskStatus.default()

    def get_status(self) -> SystemStatus:
        """Get current system status."""
        return self._status or SystemStatus.default()

    def get_recent_trades(self) -> list[TradeAlert]:
        """Get recent trade alerts."""
        return self._recent_trades.copy()

    # --- Update Methods (called by adapter) ---

    async def update_ticker(self, update: TickerUpdate) -> None:
        """Update ticker state and broadcast."""
        self._tickers[update.symbol] = update
        await self._broadcast(UIChannel.TICKER, update)

    async def update_position(self, update: PositionUpdate) -> None:
        """Update position state and broadcast."""
        self._positions[update.symbol] = update
        await self._broadcast(UIChannel.POSITION, update)

    async def add_trade(self, alert: TradeAlert) -> None:
        """Add trade alert and broadcast."""
        self._recent_trades.insert(0, alert)
        self._recent_trades = self._recent_trades[:50]
        await self._broadcast(UIChannel.TRADE, alert)

    async def update_stats(self, stats: SessionStats) -> None:
        """Update session stats and broadcast."""
        self._stats = stats
        await self._broadcast(UIChannel.STATS, stats)

    async def update_account(self, account: AccountSnapshot) -> None:
        """Update account snapshot and broadcast."""
        self._account = account
        await self._broadcast(UIChannel.ACCOUNT, account)

    async def update_risk(self, risk: RiskStatus) -> None:
        """Update risk status and broadcast."""
        self._risk = risk
        await self._broadcast(UIChannel.RISK, risk)

    async def update_status(self, status: SystemStatus) -> None:
        """Update system status and broadcast.

        Preserves feed_state from current status if the incoming status
        has the default value (DISCONNECTED), since feed_state is managed
        by connection callbacks, not the adapter.
        """
        # Preserve connection state from current status (managed by connection callbacks)
        if self._status is not None and status.feed_state == ConnectionStateEnum.DISCONNECTED:
            # Incoming status has default feed_state - preserve current value
            from dataclasses import replace

            status = replace(status, feed_state=self._status.feed_state)

        self._status = status
        await self._broadcast(UIChannel.STATUS, status)

    def _build_updated_status(
        self,
        component: str,
        state: ConnectionStateEnum,
        retry_count: int,
        error: str | None,
    ) -> SystemStatus:
        """Build an updated SystemStatus for a component state change."""
        if self._status is None:
            self._status = SystemStatus.default()

        is_connected = state == ConnectionStateEnum.CONNECTED
        current = self._status

        if component == "feed":
            return SystemStatus(
                feed_connected=is_connected,
                broker_connected=current.broker_connected,
                market_open=current.market_open,
                market_next_change=current.market_next_change,
                uptime_seconds=current.uptime_seconds,
                bars_received=current.bars_received,
                errors_count=current.errors_count,
                is_replay=current.is_replay,
                replay_time=current.replay_time,
                provider=current.provider,
                feed_state=state,
                feed_retry_count=retry_count,
                feed_last_error=error,
                broker_state=current.broker_state,
                broker_retry_count=current.broker_retry_count,
                broker_last_error=current.broker_last_error,
            )
        else:  # broker
            return SystemStatus(
                feed_connected=current.feed_connected,
                broker_connected=is_connected,
                market_open=current.market_open,
                market_next_change=current.market_next_change,
                uptime_seconds=current.uptime_seconds,
                bars_received=current.bars_received,
                errors_count=current.errors_count,
                is_replay=current.is_replay,
                replay_time=current.replay_time,
                provider=current.provider,
                feed_state=current.feed_state,
                feed_retry_count=current.feed_retry_count,
                feed_last_error=current.feed_last_error,
                broker_state=state,
                broker_retry_count=retry_count,
                broker_last_error=error,
            )

    async def update_connection_status(
        self,
        component: str,
        state: ConnectionStateEnum,
        retry_count: int = 0,
        error: str | None = None,
    ) -> None:
        """Update connection status for a specific component and broadcast.

        Args:
            component: "feed" or "broker"
            state: New connection state
            retry_count: Current retry attempt (0 if connected)
            error: Error message if disconnected/failed
        """
        self._status = self._build_updated_status(component, state, retry_count, error)
        await self._broadcast(UIChannel.STATUS, self._status)

    def update_connection_status_sync(
        self,
        component: str,
        state: ConnectionStateEnum,
        retry_count: int = 0,
        error: str | None = None,
    ) -> None:
        """Synchronous version of update_connection_status."""
        self._status = self._build_updated_status(component, state, retry_count, error)
        self._broadcast_sync(UIChannel.STATUS, self._status)

    async def update_chart(self, chart: ChartUpdate) -> None:
        """Update chart data and broadcast."""
        self._charts[chart.symbol] = chart
        await self._broadcast(UIChannel.CHART, chart)

    async def broadcast_log(self, log_entry: dict[str, str]) -> None:
        """Broadcast a log entry to all clients (callbacks + WebSocket)."""
        # Invoke callbacks (for TUI)
        for cb in self._callbacks[UIChannel.LOG]:
            try:
                result = cb(log_entry)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning(f"Callback error on log: {e}")

        # Send to WebSocket clients (for web UI)
        await self._broadcast_raw(UIChannel.LOG, log_entry)

    # --- WebSocket Client Management ---

    def add_websocket(self, ws: Any) -> None:
        """Register a WebSocket client for broadcasts."""
        self._websockets.add(ws)

    def remove_websocket(self, ws: Any) -> None:
        """Unregister a WebSocket client."""
        self._websockets.discard(ws)

    @property
    def websocket_count(self) -> int:
        """Number of connected WebSocket clients."""
        return len(self._websockets)

    # --- Broadcasting ---

    async def _broadcast(self, channel: UIChannel, data: Any) -> None:
        """Broadcast to all callbacks and WebSocket clients."""
        # Invoke callbacks
        for cb in self._callbacks[channel]:
            try:
                result = cb(data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning(f"Callback error on {channel.value}: {e}")

        # Send to WebSocket clients
        await self._broadcast_raw(channel, data.to_dict() if hasattr(data, "to_dict") else data)

    async def _broadcast_raw(self, channel: UIChannel, data: Any) -> None:
        """Broadcast raw data to WebSocket clients (no callback invocation)."""
        if not self._websockets:
            return

        message = {
            "channel": channel.value,
            "data": data,
        }
        json_msg = json.dumps(message)

        dead_clients: set[Any] = set()
        for ws in self._websockets:
            try:
                await ws.send(json_msg)
            except Exception:
                dead_clients.add(ws)

        self._websockets -= dead_clients

    # --- Sync API for non-async contexts ---

    def update_ticker_sync(self, update: TickerUpdate) -> None:
        """Synchronous ticker update (for use in sync callbacks)."""
        self._tickers[update.symbol] = update
        self._broadcast_sync(UIChannel.TICKER, update)

    def update_position_sync(self, update: PositionUpdate) -> None:
        """Synchronous position update."""
        self._positions[update.symbol] = update
        self._broadcast_sync(UIChannel.POSITION, update)

    def add_trade_sync(self, alert: TradeAlert) -> None:
        """Synchronous trade alert."""
        self._recent_trades.insert(0, alert)
        self._recent_trades = self._recent_trades[:50]
        self._broadcast_sync(UIChannel.TRADE, alert)

    def update_stats_sync(self, stats: SessionStats) -> None:
        """Synchronous stats update."""
        self._stats = stats
        self._broadcast_sync(UIChannel.STATS, stats)

    def update_account_sync(self, account: AccountSnapshot) -> None:
        """Synchronous account update."""
        self._account = account
        self._broadcast_sync(UIChannel.ACCOUNT, account)

    def update_risk_sync(self, risk: RiskStatus) -> None:
        """Synchronous risk update."""
        self._risk = risk
        self._broadcast_sync(UIChannel.RISK, risk)

    def update_status_sync(self, status: SystemStatus) -> None:
        """Synchronous status update."""
        self._status = status
        self._broadcast_sync(UIChannel.STATUS, status)

    def _broadcast_sync(self, channel: UIChannel, data: Any) -> None:
        """Broadcast to callbacks synchronously (no WebSocket)."""
        for cb in self._callbacks[channel]:
            try:
                result = cb(data)
                if asyncio.iscoroutine(result):
                    # Schedule coroutine but don't await
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(result)
                    except RuntimeError:
                        pass
            except Exception as e:
                logger.warning(f"Callback error on {channel.value}: {e}")

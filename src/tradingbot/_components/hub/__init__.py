"""Event Hub - Central dispatcher for UI updates.

The hub provides a callback-based interface for UI clients to receive
real-time trading updates. It maintains global state and broadcasts
to both in-process callbacks and WebSocket clients.

Usage:
    from tradingbot._components.hub import EventHub, EngineAdapter, HubServer

    # Create hub
    hub = EventHub()

    # Register callbacks
    hub.on_ticker(lambda t: print(f"{t.symbol}: ${t.price}"))
    hub.on_trade(lambda t: print(f"Trade: {t.type} {t.symbol}"))

    # Create adapter to connect engine events
    adapter = EngineAdapter(hub, symbols=["AAPL", "MSFT"])

    # Optional: Start WebSocket server for web clients
    server = HubServer(hub)
    await server.start()

    # Run engine with adapter callbacks
    engine = TradingEngine(..., callbacks=adapter.callbacks)
"""

from .adapter import EngineAdapter
from .hub import EventHub
from .server import HubServer, run_server
from .types import (
    AccountSnapshot,
    ChartUpdate,
    GlobalState,
    PositionUpdate,
    RiskStatus,
    SessionStats,
    SystemStatus,
    TickerUpdate,
    TradeAlert,
    UIChannel,
)

__all__ = [
    # Core
    "EventHub",
    "EngineAdapter",
    "HubServer",
    "run_server",
    # Types
    "UIChannel",
    "TickerUpdate",
    "PositionUpdate",
    "TradeAlert",
    "SessionStats",
    "AccountSnapshot",
    "RiskStatus",
    "SystemStatus",
    "ChartUpdate",
    "GlobalState",
]

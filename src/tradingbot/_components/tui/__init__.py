"""Modern Trading TUI - Event-driven terminal interface.

A callback-based TUI that connects to the EventHub for real-time updates.
Supports multi-stock display, view mode switching, and modern styling.

Usage:
    from tradingbot._components.hub import EventHub
    from tradingbot._components.tui import TradingApp

    hub = EventHub()
    app = TradingApp(hub, symbols=["AAPL", "MSFT", "GOOGL", "NVDA"])
    app.run()
"""

from .app import TradingApp
from .theme import THEME, Theme
from .views import ViewMode, get_config, mode_name, next_mode

__all__ = [
    "TradingApp",
    "ViewMode",
    "THEME",
    "Theme",
    "get_config",
    "next_mode",
    "mode_name",
]

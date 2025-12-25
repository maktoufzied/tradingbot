"""Trading App - Main Textual application."""

import contextlib
import math
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Grid
from textual.widgets import Footer, Header

from tradingbot._components.hub import EventHub
from tradingbot._components.hub.types import (
    AccountSnapshot,
    PositionUpdate,
    RiskStatus,
    SessionStats,
    StrategyInfo,
    SystemStatus,
    TickerUpdate,
    TradeAlert,
)

from .views import ViewMode, get_config, next_mode
from .widgets import (
    SignalLog,
    StatsBar,
    StatusBar,
    SymbolCard,
)

STOCKS_PER_PAGE = 4


class TradingApp(App[None]):
    """Modern trading dashboard with multi-stock display.

    Features:
    - 2x2 grid of symbol cards (4 stocks per page)
    - Pagination with number keys (1-9) to switch pages
    - Real-time price updates via callbacks
    - Sparkline charts with trend coloring
    - Position tracking with P&L
    - Session/Account/Risk statistics
    - Trade signal log
    - View mode switching (Essential/Detailed/Maximum)

    Usage:
        hub = EventHub()
        app = TradingApp(hub, symbols=["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"])
        app.run()
    """

    CSS_PATH = Path(__file__).parent / "styles.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("v", "cycle_view", "View Mode"),
        Binding("left", "prev_page", "\u2190 Prev"),
        Binding("right", "next_page", "Next \u2192"),
        Binding("1", "select_page(0)", "Page 1", show=False),
        Binding("2", "select_page(1)", "Page 2", show=False),
        Binding("3", "select_page(2)", "Page 3", show=False),
        Binding("4", "select_page(3)", "Page 4", show=False),
        Binding("5", "select_page(4)", "Page 5", show=False),
        Binding("6", "select_page(5)", "Page 6", show=False),
        Binding("7", "select_page(6)", "Page 7", show=False),
        Binding("8", "select_page(7)", "Page 8", show=False),
        Binding("9", "select_page(8)", "Page 9", show=False),
        Binding("escape", "focus_grid", "Focus Grid", show=False),
    ]

    def __init__(
        self,
        hub: EventHub,
        symbols: list[str],
        title: str = "TRADINGBOT",
    ) -> None:
        super().__init__()
        self.hub = hub
        self._all_symbols = symbols
        self._current_page = 0
        self._total_pages = max(1, math.ceil(len(symbols) / STOCKS_PER_PAGE))
        self.title = title
        self._view_mode = ViewMode.DETAILED
        self._unsubscribes: list[Callable[[], None]] = []
        self._card_slots: list[SymbolCard] = []
        self._is_replay = False
        self._replay_time_str = ""

    @property
    def _page_symbols(self) -> list[str]:
        """Get symbols for current page."""
        start = self._current_page * STOCKS_PER_PAGE
        end = start + STOCKS_PER_PAGE
        return self._all_symbols[start:end]

    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        yield Header(show_clock=True)

        with Container(id="main-container"):
            # Symbol grid (2x2)
            with Grid(id="symbol-grid"):
                page_symbols = self._page_symbols
                for i in range(STOCKS_PER_PAGE):
                    symbol = page_symbols[i] if i < len(page_symbols) else ""
                    card = SymbolCard(symbol if symbol else "---", id=f"card-slot-{i}")
                    if not symbol:
                        card.display = False
                    self._card_slots.append(card)
                    yield card

            # Stats bar
            yield StatsBar(id="stats-bar")

            # Signal log
            yield SignalLog(id="signal-log")

        # Status bar
        yield StatusBar(id="status-bar")

        yield Footer()

    def on_mount(self) -> None:
        """Subscribe to hub events on mount."""
        # Load initial state FIRST (before subscribing to callbacks)
        # This prevents duplicate entries from both initial load and callbacks
        self._load_initial_state()
        # Then subscribe to live updates
        self._subscribe_to_hub()
        self._apply_view_mode()
        # Delay page indicator update to ensure status bar is ready
        self.call_later(self._update_page_indicator)

    def on_unmount(self) -> None:
        """Unsubscribe from hub events on unmount."""
        for unsub in self._unsubscribes:
            with contextlib.suppress(Exception):
                unsub()
        self._unsubscribes.clear()

    def _subscribe_to_hub(self) -> None:
        """Subscribe to all hub events."""
        self._unsubscribes.append(self.hub.on_ticker(self._on_ticker))
        self._unsubscribes.append(self.hub.on_position(self._on_position))
        self._unsubscribes.append(self.hub.on_trade(self._on_trade))
        self._unsubscribes.append(self.hub.on_stats(self._on_stats))
        self._unsubscribes.append(self.hub.on_account(self._on_account))
        self._unsubscribes.append(self.hub.on_risk(self._on_risk))
        self._unsubscribes.append(self.hub.on_status(self._on_status))

    def _call_safe(self, callback: Callable[..., Any], *args: Any) -> None:
        """Call a function thread-safely.

        If called from the main thread, calls directly.
        If called from a background thread, uses call_from_thread.
        """
        if self._thread_id == threading.get_ident():
            callback(*args)
        else:
            self.call_from_thread(callback, *args)

    def _load_initial_state(self) -> None:
        """Load initial state from hub."""
        state = self.hub.get_state()

        # Load tickers for current page
        for ticker in state.tickers.values():
            self._on_ticker(ticker)

        # Load positions for current page
        for position in state.positions.values():
            self._on_position(position)

        # Load stats
        self._on_stats(state.stats)
        self._on_account(state.account)
        self._on_risk(state.risk)
        self._on_status(state.status)

        # Load strategy info
        self._on_strategy(state.strategy)

        # Load recent trades
        for trade in reversed(state.recent_trades):
            self._on_trade(trade)

    def _get_card_for_symbol(self, symbol: str) -> SymbolCard | None:
        """Get the card slot displaying a symbol, if on current page."""
        page_symbols = self._page_symbols
        if symbol in page_symbols:
            slot_index = page_symbols.index(symbol)
            if slot_index < len(self._card_slots):
                return self._card_slots[slot_index]
        return None

    # --- Event Handlers ---

    def _on_ticker(self, update: TickerUpdate) -> None:
        """Handle ticker update."""
        card = self._get_card_for_symbol(update.symbol)
        if card:
            self._call_safe(card.update_ticker, update)

    def _on_position(self, update: PositionUpdate) -> None:
        """Handle position update."""
        card = self._get_card_for_symbol(update.symbol)
        if card:
            self._call_safe(card.update_position, update)

    def _on_trade(self, alert: TradeAlert) -> None:
        """Handle trade alert."""
        try:
            log = self.query_one("#signal-log", SignalLog)
            self._call_safe(log.add_trade, alert)
        except Exception:
            pass

    def _on_stats(self, stats: SessionStats) -> None:
        """Handle stats update."""
        try:
            bar = self.query_one("#stats-bar", StatsBar)
            self._call_safe(bar.update_stats, stats)
        except Exception:
            pass

    def _on_account(self, account: AccountSnapshot) -> None:
        """Handle account update."""
        try:
            bar = self.query_one("#stats-bar", StatsBar)
            self._call_safe(bar.update_account, account)
        except Exception:
            pass

    def _on_risk(self, risk: RiskStatus) -> None:
        """Handle risk update."""
        try:
            bar = self.query_one("#stats-bar", StatsBar)
            self._call_safe(bar.update_risk, risk)
        except Exception:
            pass

    def _on_status(self, status: SystemStatus) -> None:
        """Handle status update."""
        # Track replay mode for title
        self._is_replay = status.is_replay
        if status.replay_time:
            self._replay_time_str = status.replay_time.strftime("%Y-%m-%d %H:%M")
        else:
            self._replay_time_str = ""
        self._call_safe(self._update_page_indicator)

        try:
            status_bar = self.query_one("#status-bar", StatusBar)
            self._call_safe(status_bar.update_status, status)
        except Exception:
            pass

    def _on_strategy(self, strategy: StrategyInfo) -> None:
        """Handle strategy info (called once at startup)."""
        try:
            bar = self.query_one("#stats-bar", StatsBar)
            self._call_safe(bar.update_strategy, strategy)
        except Exception:
            pass

    # --- Actions ---

    def action_cycle_view(self) -> None:
        """Cycle through view modes."""
        self._view_mode = next_mode(self._view_mode)
        self._apply_view_mode()

    def action_select_page(self, page: int) -> None:
        """Select a page by index (0-8)."""
        if 0 <= page < self._total_pages:
            self._switch_to_page(page)

    def action_prev_page(self) -> None:
        """Go to previous page."""
        if self._current_page > 0:
            self._switch_to_page(self._current_page - 1)

    def action_next_page(self) -> None:
        """Go to next page."""
        if self._current_page < self._total_pages - 1:
            self._switch_to_page(self._current_page + 1)

    def _switch_to_page(self, page: int) -> None:
        """Switch to a different page of symbols."""
        if page == self._current_page:
            return

        self._current_page = page
        page_symbols = self._page_symbols

        # Update each card slot with new symbol
        for i, card in enumerate(self._card_slots):
            if i < len(page_symbols):
                card.set_symbol(page_symbols[i])
                card.display = True
            else:
                card.set_symbol("---")
                card.display = False

        # Load data for new page symbols from hub state
        state = self.hub.get_state()
        for symbol in page_symbols:
            symbol_card = self._get_card_for_symbol(symbol)
            if symbol_card:
                if symbol in state.tickers:
                    symbol_card.update_ticker(state.tickers[symbol])
                if symbol in state.positions:
                    symbol_card.update_position(state.positions[symbol])

        self._update_page_indicator()
        self._apply_view_mode()

    def _update_page_indicator(self) -> None:
        """Update page indicator in header title."""
        parts = ["TRADINGBOT"]

        # Add replay mode indicator
        if self._is_replay:
            if self._replay_time_str:
                parts.append(f"REPLAY {self._replay_time_str}")
            else:
                parts.append("REPLAY")

        # Add page indicator
        if self._total_pages > 1:
            parts.append(f"[{self._current_page + 1}/{self._total_pages}]")

        self.title = " | ".join(parts)

    def action_focus_grid(self) -> None:
        """Focus the symbol grid."""
        try:
            if self._card_slots:
                self._card_slots[0].focus()
        except Exception:
            pass

    def _apply_view_mode(self) -> None:
        """Apply current view mode to all widgets."""
        config = get_config(self._view_mode)

        # Update cards
        for card in self._card_slots:
            card.set_view_mode(
                show_sparkline=config.show_sparkline,
                show_position=config.show_position,
            )

        # Update stats bar visibility
        try:
            stats_bar = self.query_one("#stats-bar", StatsBar)
            stats_bar.display = config.show_stats_bar
        except Exception:
            pass

        # Update status bar view mode indicator
        try:
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.set_view_mode(self._view_mode)
        except Exception:
            pass

    @property
    def view_mode(self) -> ViewMode:
        """Get current view mode."""
        return self._view_mode

"""Symbol Card widget - Stock card with price, chart, and position."""

import contextlib

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from tradingbot._components.hub.types import PositionUpdate, StrategyInfo, TickerUpdate

from ..theme import THEME
from .position_panel import PositionPanel
from .sparkline import Sparkline


class SymbolCard(Widget):
    """Stock card with price, sparkline chart, and position display.

    Layout (Price View):
        +-- AAPL [preset] -------------+
        |  $185.42  ^ +2.15 (+1.2%)    |
        |  [sparkline chart]          |
        |  ^ BULLISH        * BUY     |
        |  -------------------------  |
        |  ^ LONG  $183.20  50 sh     |
        |  SL $181.50  TP $188.00     |
        |  P&L: +$111.00 (+1.2%)      |
        +-----------------------------+

    Layout (Strategy View - press Enter):
        +-- AAPL [preset] -------------+
        |  Entry: swing_break         |
        |  Exit:  swing               |
        |  Risk:  1.0%   R:R: 1:2.0   |
        |  Indicators: adx            |
        |       [Enter to flip back]  |
        +-----------------------------+
    """

    can_focus = True

    BINDINGS = [
        Binding("enter", "toggle_view", "Flip", show=False),
        Binding("space", "toggle_view", "Flip", show=False),
    ]

    DEFAULT_CSS = """
    SymbolCard {
        border: round #2a2a3a;
        background: #12121a;
        padding: 0 1;
        height: auto;
        min-height: 10;
    }

    SymbolCard:focus {
        border: round #00ff88;
    }

    SymbolCard:hover {
        border: round #00d4ff;
    }

    SymbolCard .card-header {
        height: 1;
        margin-bottom: 0;
    }

    SymbolCard .symbol-name {
        text-style: bold;
        color: #ffaa00;
    }

    SymbolCard .price-row {
        height: 1;
    }

    SymbolCard .trend-signal-row {
        height: 1;
        margin-top: 0;
    }

    SymbolCard .signal-buy {
        color: #00ff88;
        text-style: bold;
    }

    SymbolCard .signal-sell {
        color: #ff3366;
        text-style: bold;
    }

    SymbolCard .signal-hold {
        color: #5a5a6a;
    }

    SymbolCard Sparkline {
        margin: 0;
    }

    SymbolCard PositionPanel {
        margin-top: 0;
    }

    SymbolCard .strategy-view {
        height: auto;
    }

    SymbolCard .strategy-row {
        height: 1;
    }

    SymbolCard .strategy-hint {
        height: 1;
        color: #5a5a6a;
        text-align: center;
    }
    """

    symbol: reactive[str] = reactive("")
    strategy_name: reactive[str] = reactive("")
    show_strategy: reactive[bool] = reactive(False)
    price: reactive[float] = reactive(0.0)
    change: reactive[float] = reactive(0.0)
    change_pct: reactive[float] = reactive(0.0)
    trend: reactive[str] = reactive("NEUTRAL")
    signal: reactive[str] = reactive("HOLD")
    position: reactive[PositionUpdate | None] = reactive(None)
    show_sparkline: reactive[bool] = reactive(True)
    show_position: reactive[bool] = reactive(True)

    def __init__(
        self,
        symbol: str,
        strategy_name: str = "",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.symbol = symbol
        self.strategy_name = strategy_name
        self._price_history: list[float] = []
        self._last_price = 0.0
        self._strategy_info: StrategyInfo | None = None

    def compose(self) -> ComposeResult:
        """Compose the card."""
        with Vertical():
            yield Static(self._format_header(), classes="card-header symbol-name")
            # Price view (default)
            yield Static("", id="price-row", classes="price-row")
            yield Sparkline(id="sparkline")
            yield Static("", id="trend-signal", classes="trend-signal-row")
            yield PositionPanel(id="position-panel")
            # Strategy view (hidden by default)
            with Vertical(id="strategy-view", classes="strategy-view"):
                yield Static("", id="strategy-entry", classes="strategy-row")
                yield Static("", id="strategy-exit", classes="strategy-row")
                yield Static("", id="strategy-risk", classes="strategy-row")
                yield Static("", id="strategy-indicators", classes="strategy-row")
                yield Static("", id="strategy-badges", classes="strategy-row")
                yield Static("[Enter] flip back", classes="strategy-hint")

    def _format_header(self) -> Text:
        """Format the header with symbol and optional strategy name."""
        text = Text()
        text.append(self.symbol, style="bold #ffaa00")
        if self.strategy_name:
            text.append(f" [{self.strategy_name}]", style="#5a5a6a")
        return text

    def on_mount(self) -> None:
        """Initialize display on mount."""
        self._update_price_display()
        self._update_trend_signal_display()
        # Hide strategy view by default
        self._update_view_visibility()

    def watch_price(self, old: float, new: float) -> None:
        """React to price changes."""
        self._last_price = old
        self._price_history.append(new)
        self._price_history = self._price_history[-60:]
        self._update_price_display()
        self._update_sparkline()

    def watch_change(self) -> None:
        self._update_price_display()

    def watch_change_pct(self) -> None:
        self._update_price_display()

    def watch_trend(self) -> None:
        self._update_trend_signal_display()

    def watch_signal(self) -> None:
        self._update_trend_signal_display()

    def watch_position(self, position: PositionUpdate | None) -> None:
        try:
            panel = self.query_one("#position-panel", PositionPanel)
            panel.update_position(position)
        except NoMatches:
            pass

    def watch_show_sparkline(self, show: bool) -> None:
        try:
            sparkline = self.query_one("#sparkline", Sparkline)
            sparkline.display = show
        except NoMatches:
            pass

    def watch_show_position(self, show: bool) -> None:
        try:
            panel = self.query_one("#position-panel", PositionPanel)
            panel.display = show
        except NoMatches:
            pass

    def _update_price_display(self) -> None:
        """Update the price row."""
        try:
            row = self.query_one("#price-row", Static)
        except NoMatches:
            return

        text = Text()

        # Show waiting message if no price data yet
        if self.price == 0:
            text.append("Waiting for data...", style=THEME.text_dim)
            row.update(text)
            return

        # Price with flash effect indication
        price_color = THEME.text
        if self._last_price > 0:
            if self.price > self._last_price:
                price_color = THEME.positive
            elif self.price < self._last_price:
                price_color = THEME.negative

        text.append(f"${self.price:.2f}", style=f"bold {price_color}")

        # Change arrow and values
        if self.change != 0:
            arrow = "\u25b2" if self.change > 0 else "\u25bc"
            change_color = THEME.positive if self.change > 0 else THEME.negative
            sign = "+" if self.change > 0 else ""
            text.append(f"  {arrow} ", style=change_color)
            text.append(
                f"{sign}{self.change:.2f} ({sign}{self.change_pct:.1f}%)",
                style=change_color,
            )

        row.update(text)

    def _update_trend_signal_display(self) -> None:
        """Update the trend/signal row."""
        try:
            row = self.query_one("#trend-signal", Static)
        except NoMatches:
            return

        text = Text()

        # Trend indicator
        if self.trend == "BULLISH":
            text.append("\u2191 ", style=THEME.positive)
            text.append("BULLISH", style=THEME.positive)
        elif self.trend == "BEARISH":
            text.append("\u2193 ", style=THEME.negative)
            text.append("BEARISH", style=THEME.negative)
        else:
            text.append("\u2500 ", style=THEME.text_dim)
            text.append("NEUTRAL", style=THEME.text_dim)

        # Signal indicator (right-aligned with padding)
        text.append("        ")

        if self.signal == "BUY":
            text.append("\u25cf ", style=THEME.positive)
            text.append("BUY", style=f"bold {THEME.positive}")
        elif self.signal == "SELL":
            text.append("\u25cf ", style=THEME.negative)
            text.append("SELL", style=f"bold {THEME.negative}")
        else:
            text.append("\u25cb ", style=THEME.text_dim)
            text.append("HOLD", style=THEME.text_dim)

        row.update(text)

    def _update_sparkline(self) -> None:
        """Update sparkline with price history."""
        try:
            sparkline = self.query_one("#sparkline", Sparkline)
            # Set trend color for sparkline
            if self.trend == "BULLISH":
                sparkline.trend_color = THEME.positive
            elif self.trend == "BEARISH":
                sparkline.trend_color = THEME.negative
            else:
                sparkline.trend_color = None
            sparkline.data = self._price_history
        except NoMatches:
            pass

    def update_ticker(self, update: TickerUpdate) -> None:
        """Update from a TickerUpdate message."""
        self.price = update.price
        self.change = update.change
        self.change_pct = update.change_pct
        self.trend = update.trend
        self.signal = update.signal

    def update_position(self, update: PositionUpdate | None) -> None:
        """Update position display."""
        self.position = update

    def set_view_mode(self, show_sparkline: bool, show_position: bool) -> None:
        """Configure visibility based on view mode."""
        self.show_sparkline = show_sparkline
        self.show_position = show_position

    def watch_strategy_name(self) -> None:
        """React to strategy name changes."""
        self._update_header()

    def _update_header(self) -> None:
        """Update the header with symbol and strategy name."""
        try:
            header = self.query_one(".symbol-name", Static)
            header.update(self._format_header())
        except NoMatches:
            pass

    def set_symbol(self, symbol: str, strategy_name: str = "") -> None:
        """Change the symbol displayed by this card."""
        self.symbol = symbol
        self.strategy_name = strategy_name
        self._price_history = []
        self._last_price = 0.0
        self.price = 0.0
        self.change = 0.0
        self.change_pct = 0.0
        self.trend = "NEUTRAL"
        self.signal = "HOLD"
        self.position = None

        # Update header
        self._update_header()

        # Clear sparkline
        try:
            sparkline = self.query_one("#sparkline", Sparkline)
            sparkline.data = []
        except NoMatches:
            pass

        # Reset to price view
        self.show_strategy = False

    def set_strategy_info(self, strategy: StrategyInfo) -> None:
        """Set the strategy info for this card."""
        self._strategy_info = strategy
        self._update_strategy_display()

    def action_toggle_view(self) -> None:
        """Toggle between price view and strategy view."""
        self.show_strategy = not self.show_strategy

    def watch_show_strategy(self, show: bool) -> None:
        """React to show_strategy changes."""
        self._update_view_visibility()
        if show:
            self._update_strategy_display()

    def _update_view_visibility(self) -> None:
        """Update which view is visible."""
        show_strat = self.show_strategy

        # Toggle price view elements
        try:
            self.query_one("#price-row", Static).display = not show_strat
            self.query_one("#sparkline", Sparkline).display = not show_strat
            self.query_one("#trend-signal", Static).display = not show_strat
            self.query_one("#position-panel", PositionPanel).display = not show_strat
        except NoMatches:
            pass

        # Toggle strategy view
        with contextlib.suppress(NoMatches):
            self.query_one("#strategy-view", Vertical).display = show_strat

    def _update_strategy_display(self) -> None:
        """Update the strategy view content."""
        strategy = self._strategy_info
        if not strategy:
            return

        try:
            entry = self.query_one("#strategy-entry", Static)
            exit_row = self.query_one("#strategy-exit", Static)
            risk = self.query_one("#strategy-risk", Static)
            indicators = self.query_one("#strategy-indicators", Static)
            badges = self.query_one("#strategy-badges", Static)
        except NoMatches:
            return

        # Get per-symbol config (falls back to global if not found)
        symbol_cfg = strategy.get_symbol_config(self.symbol)

        # Entry strategy
        entry_text = Text()
        entry_text.append("Entry  ", style=THEME.text_dim)
        entry_text.append(symbol_cfg.entry_strategy, style=f"bold {THEME.text}")
        entry.update(entry_text)

        # Exit strategy
        exit_text = Text()
        exit_text.append("Exit   ", style=THEME.text_dim)
        exit_text.append(symbol_cfg.exit_strategy, style=f"bold {THEME.text}")
        exit_row.update(exit_text)

        # Risk and R:R
        risk_text = Text()
        risk_text.append("Risk ", style=THEME.text_dim)
        risk_text.append(f"{symbol_cfg.risk_pct * 100:.1f}%", style=THEME.neutral)
        risk_text.append("    R:R ", style=THEME.text_dim)
        risk_text.append(f"1:{symbol_cfg.rr_ratio:.1f}", style=THEME.neutral)
        risk.update(risk_text)

        # Indicators with filter mode
        if symbol_cfg.indicators:
            ind_text = Text()
            ind_text.append("Indicators ", style=THEME.text_dim)
            ind_text.append(", ".join(symbol_cfg.indicators), style=THEME.text_secondary)
            ind_text.append(f" ({symbol_cfg.filter_mode})", style=THEME.text_dim)
            indicators.update(ind_text)
        else:
            indicators.update("")

        # Badges row: EOD exit and partial exits
        badge_parts = []
        if symbol_cfg.eod_exit:
            badge_parts.append(("EOD", THEME.warning))
        else:
            badge_parts.append(("Swing", THEME.positive))
        if symbol_cfg.partial_exits:
            badge_parts.append((f"Partial: {symbol_cfg.partial_exits}", THEME.neutral))

        if badge_parts:
            badge_text = Text()
            for i, (label, color) in enumerate(badge_parts):
                if i > 0:
                    badge_text.append("  ", style=THEME.text_dim)
                badge_text.append(f"[{label}]", style=color)
            badges.update(badge_text)
        else:
            badges.update("")

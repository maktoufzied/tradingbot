"""Symbol Card widget - Stock card with price, chart, and position."""

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from tradingbot._components.hub.types import PositionUpdate, TickerUpdate

from ..theme import THEME
from .position_panel import PositionPanel
from .sparkline import Sparkline


class SymbolCard(Widget):
    """Stock card with price, sparkline chart, and position display.

    Layout:
        +-- AAPL ----------------------+
        |  $185.42  ^ +2.15 (+1.2%)    |
        |  [sparkline chart]          |
        |  ^ BULLISH        * BUY     |
        |  -------------------------  |
        |  ^ LONG  $183.20  50 sh     |
        |  SL $181.50  TP $188.00     |
        |  P&L: +$111.00 (+1.2%)      |
        +-----------------------------+
    """

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
    """

    symbol: reactive[str] = reactive("")
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
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.symbol = symbol
        self._price_history: list[float] = []
        self._last_price = 0.0

    def compose(self) -> ComposeResult:
        """Compose the card."""
        with Vertical():
            yield Static(self.symbol, classes="card-header symbol-name")
            yield Static("", id="price-row", classes="price-row")
            yield Sparkline(id="sparkline")
            yield Static("", id="trend-signal", classes="trend-signal-row")
            yield PositionPanel(id="position-panel")

    def on_mount(self) -> None:
        """Initialize display on mount."""
        self._update_price_display()
        self._update_trend_signal_display()

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
        except Exception:
            pass

    def watch_show_sparkline(self, show: bool) -> None:
        try:
            sparkline = self.query_one("#sparkline", Sparkline)
            sparkline.display = show
        except Exception:
            pass

    def watch_show_position(self, show: bool) -> None:
        try:
            panel = self.query_one("#position-panel", PositionPanel)
            panel.display = show
        except Exception:
            pass

    def _update_price_display(self) -> None:
        """Update the price row."""
        try:
            row = self.query_one("#price-row", Static)
        except Exception:
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
        except Exception:
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
        except Exception:
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

    def set_symbol(self, symbol: str) -> None:
        """Change the symbol displayed by this card."""
        self.symbol = symbol
        self._price_history = []
        self._last_price = 0.0
        self.price = 0.0
        self.change = 0.0
        self.change_pct = 0.0
        self.trend = "NEUTRAL"
        self.signal = "HOLD"
        self.position = None

        # Update header
        try:
            header = self.query_one(".symbol-name", Static)
            header.update(symbol)
        except Exception:
            pass

        # Clear sparkline
        try:
            sparkline = self.query_one("#sparkline", Sparkline)
            sparkline.data = []
        except Exception:
            pass

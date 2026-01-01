"""Signal Log widget - Scrollable trade history."""

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from tradingbot._components.hub.types import TradeAlert

from ..theme import THEME


class SignalLogEntry(Static):
    """Single entry in the signal log."""

    DEFAULT_CSS = """
    SignalLogEntry {
        height: 1;
        width: 100%;
    }

    SignalLogEntry.entry {
        background: transparent;
    }

    SignalLogEntry.exit-win {
        background: #00ff88 10%;
    }

    SignalLogEntry.exit-loss {
        background: #ff3366 10%;
    }

    SignalLogEntry.blocked {
        background: #ffaa00 10%;
    }
    """

    def __init__(self, alert: TradeAlert) -> None:
        # Determine class based on alert type
        classes = "entry"
        if alert.type == "EXIT":
            classes = "exit-win" if alert.is_winner else "exit-loss"
        elif alert.type == "BLOCKED":
            classes = "blocked"

        # Build the content text
        text = self._build_content(alert)
        super().__init__(text, classes=classes)
        self._alert = alert

    def _build_content(self, alert: TradeAlert) -> Text:
        """Build the alert content as rich text."""
        text = Text()

        # Timestamp
        time_str = alert.timestamp.strftime("%H:%M")
        text.append(f"{time_str}  ", style=THEME.text_dim)

        # Direction arrow
        dir_arrow = "\u25b2" if alert.direction == "LONG" else "\u25bc"
        dir_color = THEME.positive if alert.direction == "LONG" else THEME.negative
        text.append(f"{dir_arrow} ", style=dir_color)

        # Symbol
        text.append(f"{alert.symbol}  ", style=f"bold {THEME.text}")

        if alert.type == "ENTRY":
            self._render_entry(text, alert)
        elif alert.type == "EXIT":
            self._render_exit(text, alert)
        elif alert.type == "BLOCKED":
            self._render_blocked(text, alert)

        return text

    def _render_entry(self, text: Text, alert: TradeAlert) -> None:
        """Render entry alert."""
        text.append("ENTRY  ", style=THEME.neutral)
        text.append(f"${alert.price:.2f}  ", style=THEME.text)
        text.append(f"{alert.size:.0f}sh  ", style=THEME.text_secondary)

        if alert.stop_loss:
            text.append("SL ", style=THEME.text_dim)
            text.append(f"${alert.stop_loss:.2f}  ", style=THEME.negative_dim)

        if alert.take_profit:
            text.append("TP ", style=THEME.text_dim)
            text.append(f"${alert.take_profit:.2f}", style=THEME.positive_dim)

    def _render_exit(self, text: Text, alert: TradeAlert) -> None:
        """Render exit alert."""
        text.append("EXIT   ", style=THEME.primary)

        # Price with arrow
        text.append(f"${alert.price:.2f}  ", style=THEME.text)

        # P&L
        if alert.pnl is not None:
            pnl_color = THEME.positive if alert.pnl >= 0 else THEME.negative
            pnl_sign = "+" if alert.pnl >= 0 else ""
            text.append(f"{pnl_sign}${alert.pnl:.2f}", style=f"bold {pnl_color}")

            if alert.pnl_pct is not None:
                text.append(f" ({pnl_sign}{alert.pnl_pct:.1f}%)", style=pnl_color)

        # Reason
        if alert.reason:
            text.append(f"  {alert.reason}", style=THEME.text_secondary)

        # Win/Loss indicator
        text.append("  ")
        if alert.is_winner:
            text.append("\u2713 WIN", style=f"bold {THEME.positive}")
        else:
            text.append("\u2717 LOSS", style=f"bold {THEME.negative}")

    def _render_blocked(self, text: Text, alert: TradeAlert) -> None:
        """Render blocked signal alert."""
        text.append("BLOCKED  ", style=THEME.warning)
        text.append(f"${alert.price:.2f}  ", style=THEME.text_dim)

        if alert.reason:
            text.append(alert.reason, style=THEME.warning)


class SignalLog(Widget):
    """Scrollable signal and trade log."""

    DEFAULT_CSS = """
    SignalLog {
        height: 8;
        width: 100%;
        border: round #2a2a3a;
        background: #12121a;
    }

    SignalLog .log-title {
        height: 1;
        padding: 0 1;
        color: #ffaa00;
        text-style: bold;
        background: #0f0f18;
    }

    SignalLog VerticalScroll {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    """

    max_entries: reactive[int] = reactive(100)

    def __init__(
        self,
        max_entries: int = 100,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.max_entries = max_entries
        self._entries: list[TradeAlert] = []

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS & TRADES", classes="log-title")
        yield VerticalScroll(id="log-scroll")

    def add_trade(self, alert: TradeAlert) -> None:
        """Add a trade alert to the log."""
        # Deduplicate: skip if identical to most recent entry
        if self._entries:
            last = self._entries[0]
            if (
                last.symbol == alert.symbol
                and last.type == alert.type
                and last.timestamp == alert.timestamp
                and last.price == alert.price
            ):
                return

        self._entries.insert(0, alert)
        self._entries = self._entries[: self.max_entries]

        try:
            scroll = self.query_one("#log-scroll", VerticalScroll)
            entry = SignalLogEntry(alert)
            scroll.mount(entry, before=0)

            # Remove excess entries
            children = list(scroll.children)
            if len(children) > self.max_entries:
                for child in children[self.max_entries :]:
                    child.remove()
        except NoMatches:
            pass

    def clear_log(self) -> None:
        """Clear all log entries."""
        self._entries.clear()
        try:
            scroll = self.query_one("#log-scroll", VerticalScroll)
            scroll.remove_children()
        except NoMatches:
            pass

    @property
    def entries(self) -> list[TradeAlert]:
        """Get all entries."""
        return self._entries.copy()

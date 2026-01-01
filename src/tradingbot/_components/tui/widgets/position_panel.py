"""Position Panel widget - Displays open position details."""

from rich.text import Text
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from tradingbot._components.hub.types import PositionUpdate

from ..theme import THEME


class PositionPanel(Widget):
    """Displays open position details.

    Shows direction, entry price, size, stop loss, take profit,
    and unrealized P&L when a position is open.
    """

    DEFAULT_CSS = """
    PositionPanel {
        height: auto;
        width: 100%;
        padding: 0 1;
    }

    PositionPanel.hidden {
        display: none;
    }

    PositionPanel .separator {
        color: #4a4a5a;
        height: 1;
    }

    PositionPanel .position-header {
        height: 1;
    }

    PositionPanel .position-details {
        height: 1;
    }

    PositionPanel .position-pnl {
        height: 1;
    }

    PositionPanel .no-position {
        color: #5a5a6a;
        text-style: italic;
        height: 1;
    }
    """

    position: reactive[PositionUpdate | None] = reactive(None)

    def __init__(
        self,
        position: PositionUpdate | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.position = position

    def compose(self) -> ComposeResult:
        """Compose the panel."""
        yield Static("\u2500" * 30, classes="separator")
        yield Static("", id="header", classes="position-header")
        yield Static("", id="details", classes="position-details")
        yield Static("", id="pnl", classes="position-pnl")

    def watch_position(self, position: PositionUpdate | None) -> None:
        """Update display when position changes."""
        self._update_display(position)

    def _update_display(self, position: PositionUpdate | None) -> None:
        """Update all position display elements."""
        try:
            header = self.query_one("#header", Static)
            details = self.query_one("#details", Static)
            pnl_display = self.query_one("#pnl", Static)
        except NoMatches:
            return

        if not position or not position.is_open:
            header.update(Text("No Position", style=f"italic {THEME.text_dim}"))
            details.update("")
            pnl_display.update("")
            return

        # Header: direction + entry + size
        dir_arrow = "\u25b2" if position.direction == "LONG" else "\u25bc"
        dir_color = THEME.positive if position.direction == "LONG" else THEME.negative

        header_text = Text()
        header_text.append(f"{dir_arrow} ", style=dir_color)
        header_text.append(f"{position.direction}", style=f"bold {dir_color}")
        header_text.append(f"  ${position.entry_price:.2f}", style=THEME.text)
        header_text.append(f"  {position.size:.0f} sh", style=THEME.text_secondary)
        header.update(header_text)

        # Details: SL + TP
        details_text = Text()
        details_text.append("SL ", style=THEME.text_dim)
        details_text.append(f"${position.stop_loss:.2f}", style=THEME.negative_dim)
        details_text.append("  TP ", style=THEME.text_dim)
        details_text.append(f"${position.take_profit:.2f}", style=THEME.positive_dim)
        details.update(details_text)

        # P&L
        pnl = position.unrealized_pnl
        pnl_pct = position.unrealized_pnl_pct
        pnl_color = THEME.positive if pnl >= 0 else THEME.negative
        pnl_sign = "+" if pnl >= 0 else ""

        pnl_text = Text()
        pnl_text.append("P&L: ", style=THEME.text_dim)
        pnl_text.append(
            f"{pnl_sign}${pnl:.2f} ({pnl_sign}{pnl_pct:.1f}%)",
            style=f"bold {pnl_color}",
        )

        # Add hold time if significant
        if position.holding_minutes > 0:
            hours = position.holding_minutes // 60
            mins = position.holding_minutes % 60
            if hours > 0:
                pnl_text.append(f"  {hours}h{mins}m", style=THEME.text_dim)
            else:
                pnl_text.append(f"  {mins}m", style=THEME.text_dim)

        pnl_display.update(pnl_text)

    def update_position(self, position: PositionUpdate | None) -> None:
        """Public method to update position."""
        self.position = position

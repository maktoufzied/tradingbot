"""Status Bar widget - Connection status and system info."""

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from tradingbot._components.hub.types import ConnectionStateEnum, SystemStatus

from ..theme import THEME
from ..views import ViewMode, mode_name


class StatusBar(Widget):
    """Status bar showing connection status and system info."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        width: 100%;
        background: #0f0f18;
        dock: bottom;
    }

    StatusBar Horizontal {
        height: 1;
        width: 100%;
    }

    StatusBar .replay-badge {
        width: auto;
        padding: 0 1;
    }

    StatusBar .status-indicators {
        width: 1fr;
        padding: 0 1;
    }

    StatusBar .view-mode {
        width: auto;
        padding: 0 1;
        color: #ffaa00;
    }
    """

    status: reactive[SystemStatus | None] = reactive(None)
    view_mode: reactive[ViewMode] = reactive(ViewMode.DETAILED)

    def __init__(
        self,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static("", id="replay-badge", classes="replay-badge")
            yield Static("", id="indicators", classes="status-indicators")
            yield Static("", id="view-mode", classes="view-mode")

    def on_mount(self) -> None:
        """Initialize displays."""
        self._update_replay_badge()
        self._update_indicators()
        self._update_view_mode()

    def watch_status(self, status: SystemStatus | None) -> None:
        self._update_replay_badge()
        self._update_indicators()

    def watch_view_mode(self, mode: ViewMode) -> None:
        self._update_view_mode()

    def _update_replay_badge(self) -> None:
        """Update replay mode badge."""
        try:
            badge = self.query_one("#replay-badge", Static)
        except NoMatches:
            return

        status = self.status
        if not status or not status.is_replay:
            badge.update("")
            return

        text = Text()
        text.append(" REPLAY ", style=f"bold reverse {THEME.warning}")
        if status.replay_time:
            replay_str = status.replay_time.strftime("%Y-%m-%d %H:%M")
            text.append(f" {replay_str} ", style=f"bold {THEME.warning}")
        badge.update(text)

    def _update_indicators(self) -> None:
        """Update status indicators."""
        try:
            indicators = self.query_one("#indicators", Static)
        except NoMatches:
            return

        text = Text()

        status = self.status
        if not status:
            text.append("\u25cf Alpaca ", style=THEME.text_dim)
            text.append("\u25cf Market", style=THEME.text_dim)
            indicators.update(text)
            return

        # Provider status (uses feed connection state - broker is REST/stateless)
        provider_indicator = self._get_connection_indicator(
            status.feed_state,
            status.feed_retry_count,
            status.provider,
        )
        text.append_text(provider_indicator)

        # Market status
        market_color = THEME.connected if status.market_open else THEME.warning
        market_status = "Open" if status.market_open else "Closed"
        text.append("\u25cf ", style=market_color)
        text.append(f"Market {market_status} ", style=THEME.text_secondary)

        # Additional stats
        if status.bars_received > 0:
            text.append(f" | {status.bars_received} bars", style=THEME.text_dim)

        if status.errors_count > 0:
            text.append(f" | {status.errors_count} errors", style=THEME.negative)

        if status.uptime_seconds > 0:
            hours = status.uptime_seconds // 3600
            mins = (status.uptime_seconds % 3600) // 60
            if hours > 0:
                text.append(f" | {hours}h{mins}m", style=THEME.text_dim)
            else:
                text.append(f" | {mins}m", style=THEME.text_dim)

        indicators.update(text)

    def _get_connection_indicator(
        self,
        state: ConnectionStateEnum,
        retry_count: int,
        label: str,
    ) -> Text:
        """Get connection indicator text with appropriate styling.

        Args:
            state: Current connection state
            retry_count: Number of retry attempts (for reconnecting state)
            label: Label to show (e.g., "Feed", "Broker")

        Returns:
            Text with styled indicator
        """
        text = Text()

        if state == ConnectionStateEnum.CONNECTED:
            text.append("\u25cf ", style=THEME.connected)
            text.append(f"{label} ", style=THEME.text_secondary)
        elif state == ConnectionStateEnum.RECONNECTING:
            # Yellow blinking indicator with retry count
            text.append("\u25cf ", style=f"bold blink {THEME.warning}")
            text.append(f"{label} ", style=THEME.text_secondary)
            text.append(f"(retry {retry_count}) ", style=f"bold {THEME.warning}")
        elif state == ConnectionStateEnum.FAILED:
            # Red indicator with error
            text.append("\u25cf ", style=f"bold {THEME.disconnected}")
            text.append(f"{label} ", style=THEME.text_secondary)
            text.append("FAILED ", style=f"bold {THEME.disconnected}")
        else:  # DISCONNECTED
            text.append("\u25cf ", style=THEME.disconnected)
            text.append(f"{label} ", style=THEME.text_secondary)

        return text

    def _update_view_mode(self) -> None:
        """Update view mode display."""
        try:
            vm = self.query_one("#view-mode", Static)
            vm.update(f"[{mode_name(self.view_mode)}]")
        except NoMatches:
            pass

    def update_status(self, status: SystemStatus) -> None:
        """Update system status."""
        self.status = status

    def set_view_mode(self, mode: ViewMode) -> None:
        """Set current view mode."""
        self.view_mode = mode

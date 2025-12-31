"""Log Panel widget - Scrollable message log for INFO, WARNING, ERROR."""

from dataclasses import dataclass
from datetime import datetime

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from ..theme import THEME


@dataclass
class LogEntry:
    """A log entry with timestamp, level, and message."""

    timestamp: datetime
    level: str
    message: str


class LogEntryWidget(Static):
    """Single entry in the log panel."""

    def __init__(self, entry: LogEntry) -> None:
        level_lower = entry.level.lower()
        classes = f"level-{level_lower}" if level_lower in ("error", "warning", "success") else ""
        text = self._build_content(entry)
        super().__init__(text, classes=classes)
        self._entry = entry

    def _build_content(self, entry: LogEntry) -> Text:
        """Build the log entry as rich text."""
        text = Text()

        # Timestamp
        time_str = entry.timestamp.strftime("%H:%M:%S")
        text.append(f"{time_str}  ", style=THEME.text_dim)

        # Level with color
        level_styles = {
            "DEBUG": THEME.text_dim,
            "INFO": THEME.primary,
            "SUCCESS": THEME.positive,
            "WARNING": THEME.warning,
            "ERROR": THEME.negative,
        }
        level_style = level_styles.get(entry.level.upper(), THEME.text_secondary)
        text.append(f"[{entry.level.upper():7}]  ", style=level_style)

        # Message
        text.append(entry.message, style=THEME.text)

        return text


class LogPanel(Widget):
    """Scrollable log panel for system messages."""

    max_entries: reactive[int] = reactive(50)

    def __init__(
        self,
        max_entries: int = 50,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.max_entries = max_entries
        self._entries: list[LogEntry] = []

    def compose(self) -> ComposeResult:
        yield Static("MESSAGES", classes="log-title")
        yield VerticalScroll(id="log-scroll")

    def add_log(self, log_data: dict[str, str]) -> None:
        """Add a log entry from hub data."""
        # Parse timestamp
        ts_str = log_data.get("timestamp", "")
        try:
            # Handle ISO format with timezone
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            timestamp = datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            timestamp = datetime.now()

        entry = LogEntry(
            timestamp=timestamp,
            level=log_data.get("level", "INFO"),
            message=log_data.get("message", ""),
        )

        self._entries.insert(0, entry)
        self._entries = self._entries[: self.max_entries]

        try:
            scroll = self.query_one("#log-scroll", VerticalScroll)
            widget = LogEntryWidget(entry)
            scroll.mount(widget, before=0)

            # Remove excess entries
            children = list(scroll.children)
            if len(children) > self.max_entries:
                for child in children[self.max_entries :]:
                    child.remove()
        except Exception:
            pass

    def clear_log(self) -> None:
        """Clear all log entries."""
        self._entries.clear()
        try:
            scroll = self.query_one("#log-scroll", VerticalScroll)
            scroll.remove_children()
        except Exception:
            pass

    @property
    def entries(self) -> list[LogEntry]:
        """Get all entries."""
        return self._entries.copy()

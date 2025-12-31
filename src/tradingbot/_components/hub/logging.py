"""Logging module with file and hub streaming support.

Provides a configured logger that writes to:
1. File: ~/.tradingbot/live.log (always)
2. Hub: streams to WebSocket clients via the event hub (when connected)
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .hub import EventHub

LOG_DIR = Path.home() / ".tradingbot"
LOG_FILE = LOG_DIR / "live.log"

# Module-level references
_hub: EventHub | None = None
_file_handler: logging.FileHandler | None = None


class HubLogHandler(logging.Handler):
    """Log handler that streams records to the event hub."""

    def emit(self, record: logging.LogRecord) -> None:
        if _hub is None:
            return

        try:
            import asyncio

            log_entry = {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "source": record.name,
                "message": self.format(record),
            }

            # Try to broadcast asynchronously
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_hub.broadcast_log(log_entry))
            except RuntimeError:
                # No running loop, skip WebSocket broadcast
                pass
        except Exception:
            # Never let logging errors crash the app
            pass


def setup_logging(hub: EventHub | None = None) -> logging.Logger:
    """Configure and return the trading bot logger.

    Args:
        hub: Optional EventHub for WebSocket streaming

    Returns:
        Configured logger for the feed module
    """
    global _hub, _file_handler
    _hub = hub

    # Ensure log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Get root logger for tradingbot
    logger = logging.getLogger("tradingbot.feed")
    logger.setLevel(logging.DEBUG)

    # Clear existing handlers to avoid duplicates on re-setup
    logger.handlers.clear()

    # File handler - always write to file
    _file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    _file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _file_handler.setFormatter(file_formatter)
    logger.addHandler(_file_handler)

    # Hub handler - stream to WebSocket clients
    if hub is not None:
        hub_handler = HubLogHandler()
        hub_handler.setLevel(logging.INFO)
        hub_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(hub_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_feed_logger() -> logging.Logger:
    """Get the feed logger (must call setup_logging first)."""
    return logging.getLogger("tradingbot.feed")


def log_engine_message(level: str, message: str) -> None:
    """Log an engine message directly to file.

    This is called by the adapter to ensure engine messages (like order
    rejections) are captured in the log file, not just the hub.

    Args:
        level: Log level (DEBUG, INFO, SUCCESS, WARNING, ERROR)
        message: The message to log
    """
    if _file_handler is None:
        return

    # Create a log record and emit directly to file handler
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"{timestamp} [{level.upper()}] {message}\n"

    try:
        _file_handler.stream.write(formatted)
        _file_handler.stream.flush()
    except Exception:
        pass

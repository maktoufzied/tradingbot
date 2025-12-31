"""Structured logging configuration using structlog.

Provides consistent, structured logging across all components with:
- JSON output for production (machine-parseable)
- Console output for development (human-readable)
- Correlation IDs for request tracing
- Automatic context enrichment
"""

import logging
import sys
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Final, Literal

import structlog
from structlog.typing import EventDict, WrappedLogger

# Correlation ID for tracing requests across components
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")

# Log directory
LOG_DIR: Final = Path.home() / ".tradingbot" / "logs"

LogFormat = Literal["console", "json"]


def add_correlation_id(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Add correlation ID to log events if set."""
    cid = correlation_id.get()
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def configure_logging(
    level: str = "INFO",
    log_format: LogFormat = "console",
    log_file: str | Path | None = None,
    enable_colors: bool = True,
) -> None:
    """Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Output format - "console" for development, "json" for production
        log_file: Optional file path for log output
        enable_colors: Enable colored output for console format
    """
    # Ensure log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Convert level string to logging constant
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Common processors for all formats
    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        add_correlation_id,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "json":
        # JSON format for production - machine-parseable
        processors = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Console format for development - human-readable
        processors = [
            *shared_processors,
            structlog.processors.ExceptionPrettyPrinter(),
            structlog.dev.ConsoleRenderer(colors=enable_colors),
        ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Also configure standard library logging for third-party libraries
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=log_level,
        handlers=[logging.StreamHandler(sys.stderr)],
    )

    # Reduce noise from third-party libraries
    logging.getLogger("alpaca").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)

    # Set up file logging if requested
    if log_file:
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logging.getLogger().addHandler(file_handler)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger for a module.

    Args:
        name: Logger name, typically __name__

    Returns:
        Bound structlog logger with module context

    Example:
        logger = get_logger(__name__)
        logger.info("order_submitted", symbol="AAPL", qty=100, side="buy")
    """
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID for the current context.

    Use this at the start of a request/operation to enable tracing.
    """
    correlation_id.set(cid)


def clear_correlation_id() -> None:
    """Clear the correlation ID for the current context."""
    correlation_id.set("")


def bind_context(**kwargs: Any) -> None:
    """Bind context variables to all subsequent log calls.

    Example:
        bind_context(symbol="AAPL", session_id="abc123")
        logger.info("processing")  # Will include symbol and session_id
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()

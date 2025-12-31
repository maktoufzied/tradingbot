"""Typed exception hierarchy for the trading bot.

All exceptions inherit from TradingBotError, enabling targeted
exception handling and clear error categorization.
"""

from typing import Any


class TradingBotError(Exception):
    """Base exception for all trading bot errors."""

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.context = context or {}


# --- Configuration Errors ---


class ConfigurationError(TradingBotError):
    """Invalid configuration."""


class MissingConfigError(ConfigurationError):
    """Required configuration is missing."""


# --- Data Errors ---


class DataError(TradingBotError):
    """Data-related errors (feeds, cache)."""


class FeedError(DataError):
    """Feed connection/data errors."""


class FeedConnectionError(FeedError):
    """Failed to connect to feed."""


class FeedDataError(FeedError):
    """Invalid or corrupt feed data."""


class CacheError(DataError):
    """Cache read/write errors."""


class ValidationError(DataError):
    """Data validation failed."""


# --- Broker Errors ---


class BrokerError(TradingBotError):
    """Broker-related errors."""


class BrokerConnectionError(BrokerError):
    """Failed to connect to broker."""


class OrderError(BrokerError):
    """Order submission/execution errors."""


class OrderRejectedError(OrderError):
    """Order was rejected by broker."""


class InsufficientFundsError(OrderError):
    """Not enough buying power."""


class PositionError(BrokerError):
    """Position-related errors."""


# --- Risk Errors ---


class RiskError(TradingBotError):
    """Risk management errors."""


class RiskLimitError(RiskError):
    """Risk limit exceeded."""


class CircuitBreakerError(RiskError):
    """Circuit breaker triggered."""


class DailyLossLimitError(RiskError):
    """Daily loss limit exceeded."""


# --- Retry/Recovery Errors ---


class RetryableError(TradingBotError):
    """Errors that can be retried.

    Use this for transient failures that may succeed on retry:
    - Network timeouts
    - Rate limiting
    - Temporary service unavailability
    """


class FatalError(TradingBotError):
    """Errors requiring immediate shutdown.

    Use this for unrecoverable situations:
    - Critical data corruption
    - Authentication failures
    - Regulatory violations
    """


# --- State Errors ---


class StateError(TradingBotError):
    """State management errors."""


class StateReconciliationError(StateError):
    """Local state doesn't match broker state."""


class StatePersistenceError(StateError):
    """Failed to persist state."""

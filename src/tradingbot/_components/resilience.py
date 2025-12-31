"""Resilience utilities for connection management and recovery.

Provides exponential backoff reconnection, connection state tracking,
retry decorators, and callbacks for UI notification.
"""

import asyncio
import functools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Final, ParamSpec, TypeVar

from .exceptions import RetryableError
from .logging import get_logger

logger = get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class ConnectionState(Enum):
    """Connection state for feeds and brokers."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"  # After max retries exhausted


@dataclass(frozen=True)
class ReconnectionConfig:
    """Configuration for exponential backoff reconnection."""

    max_retries: int = 5
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0


# Default configuration
DEFAULT_RECONNECTION_CONFIG: Final = ReconnectionConfig()


@dataclass
class ConnectionStatus:
    """Current connection status with metadata."""

    state: ConnectionState
    component: str  # "feed" or "broker"
    retry_count: int = 0
    last_error: str | None = None
    last_connected: datetime | None = None
    next_retry_at: datetime | None = None

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "state": self.state.value,
            "component": self.component,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
            "last_connected": self.last_connected.isoformat() if self.last_connected else None,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
        }


# Type alias for state change callback
StateChangeCallback = Callable[[ConnectionStatus], None]


async def reconnect_with_backoff(
    connect_fn: Callable[[], Awaitable[None]],
    component: str,
    config: ReconnectionConfig = DEFAULT_RECONNECTION_CONFIG,
    on_state_change: StateChangeCallback | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> bool:
    """Attempt reconnection with exponential backoff.

    Args:
        connect_fn: Async function that establishes the connection.
        component: Name of the component ("feed" or "broker").
        config: Reconnection configuration.
        on_state_change: Callback invoked on each state change.
        should_stop: Optional function that returns True if reconnection should abort.

    Returns:
        True if reconnection succeeded, False if max retries exhausted or stopped.
    """
    delay = config.base_delay

    for attempt in range(config.max_retries):
        # Check if we should abort
        if should_stop and should_stop():
            logger.info("reconnection_aborted", component=component, reason="stop_signal")
            return False

        # Notify: reconnecting
        if on_state_change:
            status = ConnectionStatus(
                state=ConnectionState.RECONNECTING,
                component=component,
                retry_count=attempt + 1,
                next_retry_at=datetime.now(),
            )
            on_state_change(status)

        logger.info(
            "reconnection_attempt",
            component=component,
            attempt=attempt + 1,
            max_retries=config.max_retries,
        )

        try:
            await connect_fn()

            # Notify: connected
            if on_state_change:
                status = ConnectionStatus(
                    state=ConnectionState.CONNECTED,
                    component=component,
                    retry_count=0,
                    last_connected=datetime.now(),
                )
                on_state_change(status)

            logger.info("reconnection_success", component=component)
            return True

        except Exception as e:
            error_msg = str(e)
            logger.warning(
                "reconnection_attempt_failed",
                component=component,
                attempt=attempt + 1,
                error=error_msg,
            )

            # Check if this was the last attempt
            if attempt == config.max_retries - 1:
                # Notify: failed
                if on_state_change:
                    status = ConnectionStatus(
                        state=ConnectionState.FAILED,
                        component=component,
                        retry_count=attempt + 1,
                        last_error=error_msg,
                    )
                    on_state_change(status)

                logger.error(
                    "reconnection_exhausted",
                    component=component,
                    max_retries=config.max_retries,
                )
                return False

            # Wait before next attempt
            logger.info("reconnection_waiting", component=component, delay_seconds=delay)
            await asyncio.sleep(delay)

            # Increase delay for next attempt (exponential backoff)
            delay = min(delay * config.backoff_factor, config.max_delay)

    return False


class ConnectionMonitor:
    """Monitors connection health and triggers reconnection.

    This class can be used to wrap a feed or broker and provide
    automatic reconnection with UI notifications.
    """

    def __init__(
        self,
        component: str,
        config: ReconnectionConfig = DEFAULT_RECONNECTION_CONFIG,
        on_state_change: StateChangeCallback | None = None,
    ) -> None:
        self.component = component
        self.config = config
        self.on_state_change = on_state_change
        self._state = ConnectionState.DISCONNECTED
        self._retry_count = 0
        self._last_connected: datetime | None = None
        self._last_error: str | None = None
        self._running = False

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    @property
    def is_reconnecting(self) -> bool:
        return self._state == ConnectionState.RECONNECTING

    def _notify_state_change(self) -> None:
        """Notify callback of current state."""
        if self.on_state_change:
            status = ConnectionStatus(
                state=self._state,
                component=self.component,
                retry_count=self._retry_count,
                last_error=self._last_error,
                last_connected=self._last_connected,
            )
            self.on_state_change(status)

    def set_connected(self) -> None:
        """Mark as connected (called when connection established)."""
        self._state = ConnectionState.CONNECTED
        self._retry_count = 0
        self._last_connected = datetime.now()
        self._last_error = None
        self._notify_state_change()
        logger.info("component_connected", component=self.component)

    def set_disconnected(self, error: str | None = None) -> None:
        """Mark as disconnected (called when connection lost)."""
        self._state = ConnectionState.DISCONNECTED
        self._last_error = error
        self._notify_state_change()
        logger.warning("component_disconnected", component=self.component, error=error or "unknown")

    def set_reconnecting(self, attempt: int) -> None:
        """Mark as reconnecting (called during reconnection attempts)."""
        self._state = ConnectionState.RECONNECTING
        self._retry_count = attempt
        self._notify_state_change()

    def set_failed(self, error: str | None = None) -> None:
        """Mark as failed (called when max retries exhausted)."""
        self._state = ConnectionState.FAILED
        self._last_error = error
        self._notify_state_change()
        logger.error("component_connection_failed", component=self.component, error=error or "unknown")

    async def reconnect(
        self,
        connect_fn: Callable[[], Awaitable[None]],
        should_stop: Callable[[], bool] | None = None,
    ) -> bool:
        """Attempt reconnection with backoff.

        Args:
            connect_fn: Async function to establish connection.
            should_stop: Optional function returning True to abort.

        Returns:
            True if reconnection succeeded.
        """

        def state_change_handler(status: ConnectionStatus) -> None:
            self._state = status.state
            self._retry_count = status.retry_count
            self._last_error = status.last_error
            if status.last_connected:
                self._last_connected = status.last_connected
            self._notify_state_change()

        return await reconnect_with_backoff(
            connect_fn=connect_fn,
            component=self.component,
            config=self.config,
            on_state_change=state_change_handler,
            should_stop=should_stop,
        )


# --- Retry Decorator ---


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for retry decorator."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    backoff_factor: float = 2.0
    exceptions: tuple[type[Exception], ...] = (RetryableError,)


DEFAULT_RETRY_CONFIG: Final = RetryConfig()


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (RetryableError,),
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Retry decorator with exponential backoff for async functions.

    Args:
        max_attempts: Maximum number of retry attempts.
        base_delay: Initial delay between retries in seconds.
        max_delay: Maximum delay between retries.
        backoff_factor: Multiplier for delay after each retry.
        exceptions: Tuple of exception types that trigger a retry.

    Example:
        @retry(max_attempts=3, exceptions=(RetryableError, TimeoutError))
        async def fetch_data():
            ...
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            delay = base_delay
            last_exception: Exception | None = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts - 1:
                        logger.error(
                            "retry_exhausted",
                            function=func.__name__,
                            max_attempts=max_attempts,
                            error=str(e),
                        )
                        raise

                    logger.warning(
                        "retry_attempt_failed",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                        error=str(e),
                        retry_delay=delay,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)

            # Should never reach here, but satisfy type checker
            if last_exception:
                raise last_exception
            raise RuntimeError("Retry loop completed without success or exception")

        return wrapper

    return decorator


def retry_sync(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (RetryableError,),
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Retry decorator with exponential backoff for sync functions.

    Args:
        max_attempts: Maximum number of retry attempts.
        base_delay: Initial delay between retries in seconds.
        max_delay: Maximum delay between retries.
        backoff_factor: Multiplier for delay after each retry.
        exceptions: Tuple of exception types that trigger a retry.
    """
    import time

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            delay = base_delay
            last_exception: Exception | None = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts - 1:
                        logger.error(
                            "retry_exhausted",
                            function=func.__name__,
                            max_attempts=max_attempts,
                            error=str(e),
                        )
                        raise

                    logger.warning(
                        "retry_attempt_failed",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                        error=str(e),
                        retry_delay=delay,
                    )
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)

            if last_exception:
                raise last_exception
            raise RuntimeError("Retry loop completed without success or exception")

        return wrapper

    return decorator


async def retry_async_call[T](
    func: Callable[[], Awaitable[T]],
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (RetryableError,),
    operation_name: str | None = None,
) -> T:
    """Execute an async callable with retry logic.

    Useful when you can't use the decorator directly.

    Args:
        func: Async callable to execute.
        max_attempts: Maximum number of retry attempts.
        base_delay: Initial delay between retries in seconds.
        max_delay: Maximum delay between retries.
        backoff_factor: Multiplier for delay after each retry.
        exceptions: Tuple of exception types that trigger a retry.
        operation_name: Name for logging (defaults to 'operation').

    Returns:
        The result of the callable.

    Example:
        result = await retry_async_call(
            lambda: client.fetch_data(symbol),
            max_attempts=3,
            exceptions=(TimeoutError, ConnectionError),
            operation_name="fetch_data",
        )
    """
    name = operation_name or "operation"
    delay = base_delay
    last_exception: Exception | None = None

    for attempt in range(max_attempts):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            if attempt == max_attempts - 1:
                logger.error("retry_exhausted", operation=name, max_attempts=max_attempts, error=str(e))
                raise

            logger.warning(
                "retry_attempt_failed",
                operation=name,
                attempt=attempt + 1,
                max_attempts=max_attempts,
                error=str(e),
                retry_delay=delay,
            )
            await asyncio.sleep(delay)
            delay = min(delay * backoff_factor, max_delay)

    if last_exception:
        raise last_exception
    raise RuntimeError("Retry loop completed without success or exception")

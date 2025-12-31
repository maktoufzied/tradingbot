"""Resilience utilities for connection management and recovery.

Provides exponential backoff reconnection, connection state tracking,
and callbacks for UI notification.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Final

logger = logging.getLogger(__name__)


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
            logger.info("%s reconnection aborted by stop signal", component)
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
            "%s reconnection attempt %d/%d",
            component,
            attempt + 1,
            config.max_retries,
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

            logger.info("%s reconnected successfully", component)
            return True

        except Exception as e:
            error_msg = str(e)
            logger.warning(
                "%s reconnection attempt %d failed: %s",
                component,
                attempt + 1,
                error_msg,
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
                    "%s reconnection failed after %d attempts",
                    component,
                    config.max_retries,
                )
                return False

            # Wait before next attempt
            logger.info("%s waiting %.1fs before next attempt", component, delay)
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
        logger.info("%s connected", self.component)

    def set_disconnected(self, error: str | None = None) -> None:
        """Mark as disconnected (called when connection lost)."""
        self._state = ConnectionState.DISCONNECTED
        self._last_error = error
        self._notify_state_change()
        logger.warning("%s disconnected: %s", self.component, error or "unknown")

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
        logger.error("%s connection failed: %s", self.component, error or "unknown")

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

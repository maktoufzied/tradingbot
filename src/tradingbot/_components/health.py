"""Health check for monitoring trading engine status.

Periodically logs system health metrics for debugging and monitoring.
"""

import asyncio
import contextlib
import resource
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from tradingbot.config import HealthConfig

from .logging import get_logger

logger = get_logger(__name__)


def get_memory_mb() -> float:
    """Get current process memory usage in MB."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # maxrss units differ by platform: kilobytes on macOS, bytes on Linux
    if sys.platform == "darwin":
        return usage.ru_maxrss / 1024  # KB to MB
    return usage.ru_maxrss / 1024 / 1024  # bytes to MB (Linux)


class HealthChecker:
    """Periodically logs health metrics for the trading engine."""

    def __init__(
        self,
        config: HealthConfig,
        broker: Any,
        feed: Any,
        risk_manager: Any,
        get_positions_count: Callable[[], int],
        get_last_bar_time: Callable[[], datetime | None],
    ) -> None:
        self._config = config
        self._broker = broker
        self._feed = feed
        self._risk = risk_manager
        self._get_positions_count = get_positions_count
        self._get_last_bar_time = get_last_bar_time
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        """Start the health check background task."""
        if not self._config.enabled:
            logger.debug("health_check_disabled")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("health_checker_started", interval_minutes=self._config.interval_minutes)

    async def stop(self) -> None:
        """Stop the health check background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.debug("health_checker_stopped")

    async def _run_loop(self) -> None:
        """Main health check loop."""
        interval_seconds = self._config.interval_minutes * 60

        while self._running:
            try:
                await self._emit_health()
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("health_check_error", error=str(e))

    async def _emit_health(self) -> None:
        """Emit health metrics."""
        now = datetime.now(UTC)

        # Connection status (default False for safety if attribute missing)
        feed_connected = getattr(self._feed, "is_connected", False)
        broker_connected = getattr(self._broker, "is_connected", False)

        # Last bar age
        last_bar_time = self._get_last_bar_time()
        last_bar_age_seconds: float | None = None
        if last_bar_time:
            # Ensure last_bar_time is timezone-aware
            if last_bar_time.tzinfo is None:
                last_bar_time = last_bar_time.replace(tzinfo=UTC)
            last_bar_age_seconds = (now - last_bar_time).total_seconds()

        # Position and risk info
        open_positions = self._get_positions_count()

        logger.info(
            "health_check",
            feed_connected=feed_connected,
            broker_connected=broker_connected,
            last_bar_age_seconds=last_bar_age_seconds,
            open_positions=open_positions,
            session_trades=self._risk.session_trades,
            session_pnl=round(self._risk.session_pnl, 2),
            session_win_rate=round(self._risk.session_win_rate, 2),
            memory_mb=round(get_memory_mb(), 1),
        )

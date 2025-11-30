"""Polling-based data feed using existing DataFetcher."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Final

import polars as pl

from ..._fetchers import DataFetcher
from ...models import Bar
from ..protocol import DataFeedProtocol

POLL_INTERVAL_SECONDS: Final[int] = 60


class PollingFeed(DataFeedProtocol):
    """Data feed that polls historical data at regular intervals.

    This is a fallback for when real-time WebSocket feeds aren't available.
    It fetches the latest bar from the data fetcher periodically.
    """

    def __init__(self, interval_seconds: int = POLL_INTERVAL_SECONDS) -> None:
        self._interval: int = interval_seconds
        self._symbols: list[str] = []
        self._callback: Callable[[Bar], Awaitable[None] | None] | None = None
        self._running: bool = False
        self._task: asyncio.Task[None] | None = None
        self._last_bar_times: dict[str, datetime] = {}

    @property
    def name(self) -> str:
        return "polling"

    @property
    def is_connected(self) -> bool:
        return self._running

    async def subscribe(self, symbols: list[str], on_bar: Callable[[Bar], Awaitable[None] | None]) -> None:
        """Subscribe to symbols."""
        self._symbols = symbols
        self._callback = on_bar

    async def unsubscribe(self, symbols: list[str]) -> None:
        """Unsubscribe from symbols."""
        for sym in symbols:
            if sym in self._symbols:
                self._symbols.remove(sym)
            self._last_bar_times.pop(sym, None)

    async def start(self) -> None:
        """Start the polling loop."""
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            await self._fetch_and_emit()
            await asyncio.sleep(self._interval)

    async def _fetch_and_emit(self) -> None:
        """Fetch latest data and emit new bars."""
        if not self._callback:
            return

        for symbol in self._symbols:
            try:
                df: pl.DataFrame = DataFetcher.fetch(
                    symbol,
                    period="5d",
                    interval="1d",
                    use_cache=False,
                )

                if df.is_empty():
                    continue

                last_row = df.row(-1, named=True)
                bar_time: datetime = last_row["datetime"]

                # Only emit if this is a new bar
                if symbol not in self._last_bar_times or bar_time > self._last_bar_times[symbol]:
                    self._last_bar_times[symbol] = bar_time

                    bar = Bar(
                        symbol=symbol,
                        datetime=bar_time,
                        open=float(last_row["open"]),
                        high=float(last_row["high"]),
                        low=float(last_row["low"]),
                        close=float(last_row["close"]),
                        volume=int(last_row["volume"]),
                    )

                    result = self._callback(bar)
                    if asyncio.iscoroutine(result):
                        await result

            except Exception as e:
                print(f"[POLL] Error fetching {symbol}: {e}")

"""Replay feed - Streams historical bars for testing."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Collection
from datetime import datetime, timedelta

import polars as pl

from tradingbot.config import get_engine_config
from tradingbot.interfaces import DataFeedProtocol
from tradingbot.types import Bar

from ...cache.cached_feed import CachedFeed


class ReplayFeed(DataFeedProtocol):
    """Replay historical bars as a simulated real-time feed.

    Fetches historical bars from cache and streams them with configurable delay.
    Useful for testing TUI and strategies without needing live market data.

    Usage:
        feed = ReplayFeed(delay=0.5)  # 500ms between bars
        await feed.subscribe(["AAPL", "MSFT"], on_bar_callback)
        await feed.start()
    """

    def __init__(self, delay: float = 0.5, days: int = 5) -> None:
        """Initialize replay feed.

        Args:
            delay: Seconds between bar emissions (default 0.5s)
            days: Days of historical data to replay (default 5)
        """
        self._delay = delay
        self._days = days
        self._symbols: list[str] = []
        self._callback: Callable[[Bar], Awaitable[None] | None] | None = None
        self._running = False
        self._connected = False
        self._cached_feed = CachedFeed()
        self._task: asyncio.Task[None] | None = None

    @property
    def name(self) -> str:
        """Feed name."""
        return "replay"

    @property
    def is_connected(self) -> bool:
        """Whether feed is connected."""
        return self._connected

    async def subscribe(self, symbols: Collection[str], on_bar: Callable[[Bar], Awaitable[None] | None]) -> None:
        """Subscribe to symbols."""
        self._symbols = list(symbols)
        self._callback = on_bar

    async def unsubscribe(self, symbols: Collection[str]) -> None:
        """Unsubscribe from symbols."""
        for sym in symbols:
            if sym in self._symbols:
                self._symbols.remove(sym)

    async def start(self) -> None:
        """Start streaming historical bars."""
        self._connected = True
        self._running = True
        self._task = asyncio.create_task(self._stream_bars())

    async def stop(self) -> None:
        """Stop streaming."""
        self._running = False
        self._connected = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _stream_bars(self) -> None:
        """Stream historical bars to callback."""
        interval = get_engine_config().bar_interval

        # Collect all bars from all symbols
        all_bars: list[Bar] = []

        for symbol in self._symbols:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self._days)

            df = self._cached_feed.history(
                symbol,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                interval=interval,
            )

            if df.is_empty():
                continue

            # Convert dataframe rows to Bar objects
            for row in df.iter_rows(named=True):
                bar = Bar(
                    symbol=symbol,
                    datetime=row["datetime"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                )
                all_bars.append(bar)

        # Sort by datetime to interleave symbols
        all_bars.sort(key=lambda b: b.datetime)

        # Group bars by timestamp so all stocks update together
        bars_by_time: dict[datetime, list[Bar]] = {}
        for bar in all_bars:
            if bar.datetime not in bars_by_time:
                bars_by_time[bar.datetime] = []
            bars_by_time[bar.datetime].append(bar)

        # Stream bars grouped by timestamp
        for timestamp in sorted(bars_by_time.keys()):
            if not self._running:
                break

            # Emit all bars for this timestamp together
            for bar in bars_by_time[timestamp]:
                if self._callback:
                    result = self._callback(bar)
                    if asyncio.iscoroutine(result):
                        await result

            # Delay between timestamps, not between individual bars
            await asyncio.sleep(self._delay)

        self._running = False
        self._connected = False

    def history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        period: str = "1y",
        interval: str = "1h",
        debug: bool = False,  # noqa: ARG002
    ) -> pl.DataFrame:
        """Get historical data from cache."""
        return self._cached_feed.history(symbol, start_date, end_date, period, interval)

"""Replay feed that simulates real-time trading using historical data."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Collection
from datetime import date, datetime
from typing import Final

import polars as pl

from tradingbot.interfaces import DataFeedProtocol
from tradingbot.types import Bar

from .yahoo import YahooFeed

DEFAULT_SPEED: Final[float] = 1.0  # 1 bar per second


class ReplayFeed(DataFeedProtocol):
    """Data feed that replays historical bars as if they were live.

    Useful for testing the live trading engine with historical data
    before deploying to real markets.
    """

    def __init__(
        self,
        speed: float = DEFAULT_SPEED,
        start_date: date | None = None,
        end_date: date | None = None,
        period: str = "2y",
        interval: str = "1d",
    ) -> None:
        """Initialize replay feed.

        Args:
            speed: Bars per second (1.0 = 1 bar/sec, 10.0 = 10 bars/sec, 0 = instant)
            start_date: Start replaying from this date (inclusive)
            end_date: Stop replaying at this date (inclusive)
            period: Historical period to fetch if no start_date
            interval: Bar interval (1d, 1h, etc.)
        """
        self._speed = speed
        self._start_date = start_date
        self._end_date = end_date
        self._period = period
        self._interval = interval

        self._symbols: list[str] = []
        self._callback: Callable[[Bar], Awaitable[None] | None] | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._data: dict[str, pl.DataFrame] = {}
        self._paused = False

    @property
    def name(self) -> str:
        return "replay"

    @property
    def is_connected(self) -> bool:
        return self._running

    async def subscribe(self, symbols: Collection[str], on_bar: Callable[[Bar], Awaitable[None] | None]) -> None:
        """Subscribe to symbols and load historical data."""
        self._symbols = list(symbols)
        self._callback = on_bar

        # Pre-fetch all historical data using YahooFeed
        yahoo = YahooFeed()
        for symbol in self._symbols:
            df = yahoo.history(symbol, period=self._period, interval=self._interval)

            # Filter by date range if specified
            if self._start_date:
                df = df.filter(pl.col("datetime") >= datetime.combine(self._start_date, datetime.min.time()))
            if self._end_date:
                df = df.filter(pl.col("datetime") <= datetime.combine(self._end_date, datetime.max.time()))

            self._data[symbol] = df

    async def unsubscribe(self, symbols: Collection[str]) -> None:
        """Unsubscribe from symbols."""
        for sym in symbols:
            if sym in self._symbols:
                self._symbols.remove(sym)
            self._data.pop(sym, None)

    async def start(self) -> None:
        """Start the replay."""
        self._running = True
        self._task = asyncio.create_task(self._replay_loop())

    async def stop(self) -> None:
        """Stop the replay."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def pause(self) -> None:
        """Pause the replay."""
        self._paused = True

    def resume(self) -> None:
        """Resume the replay."""
        self._paused = False

    async def _replay_loop(self) -> None:
        """Main replay loop - emit bars chronologically across all symbols."""
        if not self._callback:
            return

        # Merge all symbol data and sort by datetime
        all_bars: list[tuple[datetime, str, dict[str, float | int]]] = []

        for symbol, df in self._data.items():
            for row in df.iter_rows(named=True):
                all_bars.append((row["datetime"], symbol, row))

        # Sort by datetime
        all_bars.sort(key=lambda x: x[0])

        total_bars = len(all_bars)
        if total_bars == 0:
            print("[REPLAY] No bars to replay")
            return

        print(f"[REPLAY] Starting replay of {total_bars} bars")
        print(f"[REPLAY] Date range: {all_bars[0][0].date()} to {all_bars[-1][0].date()}")
        print(f"[REPLAY] Speed: {self._speed} bars/second" if self._speed > 0 else "[REPLAY] Speed: instant")

        for i, (dt, symbol, row) in enumerate(all_bars):
            if not self._running:
                break

            # Handle pause
            while self._paused and self._running:
                await asyncio.sleep(0.1)

            bar = Bar(
                symbol=symbol,
                datetime=dt,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
            )

            result = self._callback(bar)
            if asyncio.iscoroutine(result):
                await result

            # Progress indicator every 50 bars
            if (i + 1) % 50 == 0 or i == total_bars - 1:
                pct = (i + 1) / total_bars * 100
                print(f"[REPLAY] Progress: {i + 1}/{total_bars} ({pct:.1f}%)")

            # Delay between bars (unless speed is 0 for instant replay)
            if self._speed > 0 and self._running:
                await asyncio.sleep(1.0 / self._speed)

        print("[REPLAY] Replay complete")
        self._running = False

"""Alpaca real-time data feed using WebSocket streaming."""

import asyncio
import contextlib
import os
from collections.abc import Awaitable, Callable, Collection
from datetime import datetime
from typing import Any, Final

import polars as pl
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from tradingbot.config import get_live_config
from tradingbot.interfaces import DataFeedProtocol
from tradingbot.types import Bar

ALPACA_API_KEY_ENV: Final = "ALPACA_API_KEY"
ALPACA_SECRET_KEY_ENV: Final = "ALPACA_SECRET_KEY"
RECONNECT_DELAY_SECONDS: Final = 5
MAX_RECONNECT_ATTEMPTS: Final = 10


class AlpacaFeed(DataFeedProtocol):
    """Real-time data feed from Alpaca WebSocket stream."""

    def __init__(self) -> None:
        self._api_key: str | None = None
        self._secret_key: str | None = None
        self._stream: StockDataStream | None = None
        self._symbols: list[str] = []
        self._callback: Callable[[Bar], Awaitable[None] | None] | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._reconnect_attempts = 0

    def _ensure_credentials(self) -> tuple[str, str]:
        """Get credentials, raising if not available (lazy initialization)."""
        if self._api_key is not None and self._secret_key is not None:
            return self._api_key, self._secret_key

        config = get_live_config().alpaca

        # Environment variables take priority over config file
        api_key = os.environ.get(ALPACA_API_KEY_ENV) or config.api_key
        secret_key = os.environ.get(ALPACA_SECRET_KEY_ENV) or config.secret_key

        if not api_key or not secret_key:
            raise ValueError(
                f"Alpaca API credentials not found. "
                f"Set {ALPACA_API_KEY_ENV} and {ALPACA_SECRET_KEY_ENV} environment variables, "
                f"or configure in tradingbot.toml under [tradingbot.live.alpaca]."
            )

        self._api_key = api_key
        self._secret_key = secret_key
        return api_key, secret_key

    @property
    def name(self) -> str:
        return "alpaca"

    @property
    def is_connected(self) -> bool:
        return self._running

    async def subscribe(self, symbols: Collection[str], on_bar: Callable[[Bar], Awaitable[None] | None]) -> None:
        """Subscribe to real-time bars for the given symbols."""
        self._symbols = list(symbols)
        self._callback = on_bar

    async def unsubscribe(self, symbols: Collection[str]) -> None:
        """Unsubscribe from the given symbols."""
        for sym in symbols:
            if sym in self._symbols:
                self._symbols.remove(sym)

        if self._stream and self._running:
            with contextlib.suppress(Exception):
                self._stream.unsubscribe_bars(*symbols)

    async def start(self) -> None:
        """Start the WebSocket connection."""
        self._running = True
        self._task = asyncio.create_task(self._run_stream())

    async def stop(self) -> None:
        """Stop the WebSocket connection."""
        self._running = False

        if self._stream:
            with contextlib.suppress(Exception):
                self._stream.stop()
            self._stream = None

        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run_stream(self) -> None:
        """Run the WebSocket stream with reconnection logic."""
        api_key, secret_key = self._ensure_credentials()
        while self._running:
            try:
                self._stream = StockDataStream(api_key, secret_key)

                # Subscribe to bars with async handler
                self._stream.subscribe_bars(self._handle_bar_async, *self._symbols)

                self._reconnect_attempts = 0
                print(f"[ALPACA] Connected to WebSocket. Subscribed to: {', '.join(self._symbols)}")
                print(
                    "[ALPACA] Waiting for market data (bars only arrive during market hours: 9:30 AM - 4:00 PM ET)..."
                )

                # Run in a thread since StockDataStream.run() is blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._stream.run)

            except Exception as e:
                if not self._running:
                    break

                self._reconnect_attempts += 1
                if self._reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
                    print(f"[ALPACA] Max reconnection attempts reached. Last error: {e}")
                    self._running = False
                    break

                print(f"[ALPACA] Connection lost: {e}. Reconnecting in {RECONNECT_DELAY_SECONDS}s...")
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)

    async def _handle_bar_async(self, alpaca_bar: Any) -> None:
        """Handle incoming bar data from Alpaca (async handler for SDK)."""
        if not self._callback:
            return

        # Convert Alpaca bar to our Bar model
        bar = Bar(
            symbol=alpaca_bar.symbol,
            datetime=alpaca_bar.timestamp.replace(tzinfo=None) if alpaca_bar.timestamp.tzinfo else alpaca_bar.timestamp,
            open=float(alpaca_bar.open),
            high=float(alpaca_bar.high),
            low=float(alpaca_bar.low),
            close=float(alpaca_bar.close),
            volume=int(alpaca_bar.volume),
        )

        result = self._callback(bar)

        # If callback returns a coroutine, await it
        if asyncio.iscoroutine(result):
            await result

    def _handle_bar_sync(self, alpaca_bar: Any) -> None:
        """Handle incoming bar data from Alpaca (sync handler for testing)."""
        if not self._callback:
            return

        # Convert Alpaca bar to our Bar model
        bar = Bar(
            symbol=alpaca_bar.symbol,
            datetime=alpaca_bar.timestamp.replace(tzinfo=None) if alpaca_bar.timestamp.tzinfo else alpaca_bar.timestamp,
            open=float(alpaca_bar.open),
            high=float(alpaca_bar.high),
            low=float(alpaca_bar.low),
            close=float(alpaca_bar.close),
            volume=int(alpaca_bar.volume),
        )

        result = self._callback(bar)

        # If callback returns a coroutine, schedule it
        if asyncio.iscoroutine(result):
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(result, loop)
            else:
                loop.run_until_complete(result)

    def history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        period: str = "2y",
        interval: str = "1d",
    ) -> pl.DataFrame:
        """Fetch historical bar data from Alpaca."""
        api_key, secret_key = self._ensure_credentials()
        client = StockHistoricalDataClient(api_key, secret_key)

        timeframe = self._parse_interval(interval)

        # Build request
        if start_date and end_date:
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=timeframe,
                start=datetime.fromisoformat(start_date),
                end=datetime.fromisoformat(end_date),
            )
        else:
            # Convert period to start date
            start = self._period_to_start(period)
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=timeframe,
                start=start,
            )

        bars = client.get_stock_bars(request)

        # Convert to DataFrame
        data: list[dict[str, Any]] = []
        for bar in bars[symbol]:
            data.append(
                {
                    "datetime": bar.timestamp.replace(tzinfo=None) if bar.timestamp.tzinfo else bar.timestamp,
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": int(bar.volume),
                }
            )

        if not data:
            raise ValueError(f"No data found for {symbol}")

        return pl.DataFrame(data)

    def _parse_interval(self, interval: str) -> TimeFrame:
        """Convert interval string to Alpaca TimeFrame."""
        unit_map: dict[str, TimeFrameUnit] = {
            "m": TimeFrameUnit.Minute,
            "h": TimeFrameUnit.Hour,
            "d": TimeFrameUnit.Day,
            "w": TimeFrameUnit.Week,
            "M": TimeFrameUnit.Month,
        }

        # Parse interval like "1d", "5m", "1h"
        amount = int(interval[:-1])
        unit_char = interval[-1]

        if unit_char in unit_map:
            return TimeFrame(amount, unit_map[unit_char])
        return TimeFrame(amount, TimeFrameUnit.Day)

    def _period_to_start(self, period: str) -> datetime:
        """Convert period string to start datetime.

        Supports formats like: 2y, 1mo, 3mo, 5d, 1w
        """
        from datetime import timedelta

        now = datetime.now()

        # Handle "mo" suffix for months (e.g., "3mo")
        if period.endswith("mo"):
            amount = int(period[:-2])
            return now - timedelta(days=amount * 30)

        amount = int(period[:-1])
        unit = period[-1]

        if unit == "d":
            return now - timedelta(days=amount)
        elif unit == "w":
            return now - timedelta(weeks=amount)
        elif unit == "y":
            return now - timedelta(days=amount * 365)
        else:
            return now - timedelta(days=730)  # Default 2 years

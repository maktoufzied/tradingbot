"""Alpaca real-time data feed using WebSocket streaming."""

import asyncio
import contextlib
import os
from collections.abc import Awaitable, Callable
from typing import Any, Final

from alpaca.data.live import StockDataStream

from ...config import get_live_config
from ...models import Bar
from ..protocol import DataFeedProtocol

ALPACA_API_KEY_ENV: Final = "ALPACA_API_KEY"
ALPACA_SECRET_KEY_ENV: Final = "ALPACA_SECRET_KEY"
RECONNECT_DELAY_SECONDS: Final = 5
MAX_RECONNECT_ATTEMPTS: Final = 10


class AlpacaFeed(DataFeedProtocol):
    """Real-time data feed from Alpaca WebSocket stream."""

    def __init__(self) -> None:
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
        self._stream: StockDataStream | None = None
        self._symbols: list[str] = []
        self._callback: Callable[[Bar], Awaitable[None] | None] | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._reconnect_attempts = 0

    @property
    def name(self) -> str:
        return "alpaca"

    @property
    def is_connected(self) -> bool:
        return self._running

    async def subscribe(self, symbols: list[str], on_bar: Callable[[Bar], Awaitable[None] | None]) -> None:
        """Subscribe to real-time bars for the given symbols."""
        self._symbols = symbols
        self._callback = on_bar

    async def unsubscribe(self, symbols: list[str]) -> None:
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
        while self._running:
            try:
                self._stream = StockDataStream(self._api_key, self._secret_key)

                # Subscribe to bars - use sync handler since stream runs in executor thread
                self._stream.subscribe_bars(self._handle_bar_sync, *self._symbols)

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

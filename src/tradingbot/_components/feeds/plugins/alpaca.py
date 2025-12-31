"""Alpaca real-time data feed using WebSocket streaming."""

import asyncio
import contextlib
import logging
import os
from collections.abc import Awaitable, Callable, Collection
from datetime import datetime, timedelta
from typing import Any, Final

import polars as pl
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.models.bars import BarSet
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from tradingbot.config import get_cache_config, get_engine_config
from tradingbot.interfaces import DataFeedProtocol
from tradingbot.types import Bar, BarOrigin

from ...cache.db import insert_bars
from ...resilience import (
    ConnectionMonitor,
    ConnectionState,
    ConnectionStatus,
    ReconnectionConfig,
)

logger = logging.getLogger("tradingbot.feed")

ALPACA_API_KEY_ENV: Final = "ALPACA_API_KEY"
ALPACA_SECRET_KEY_ENV: Final = "ALPACA_SECRET_KEY"

# Watchdog: if no bars for this long during market hours, assume connection is stale
STALE_CONNECTION_SECONDS: Final = 180  # 3 minutes

# Reconnection configuration
DEFAULT_FEED_RECONNECTION_CONFIG: Final = ReconnectionConfig(
    max_retries=10,
    base_delay=5.0,
    max_delay=60.0,
    backoff_factor=2.0,
)

# Type alias for connection state callback
ConnectionStateCallback = Callable[[ConnectionStatus], None]


class AlpacaFeed(DataFeedProtocol):
    """Real-time data feed from Alpaca WebSocket stream.

    Alpaca streams 1-minute bars. If bar_interval is set to a larger timeframe
    (e.g., 5m), we aggregate 1m bars into the configured interval.
    """

    def __init__(
        self,
        on_connection_state: ConnectionStateCallback | None = None,
        reconnection_config: ReconnectionConfig | None = None,
    ) -> None:
        """Initialize Alpaca feed.

        Args:
            on_connection_state: Optional callback invoked on connection state changes.
            reconnection_config: Optional custom reconnection configuration.
        """
        self._api_key: str | None = None
        self._secret_key: str | None = None
        self._data_feed: DataFeed | None = None
        self._stream: StockDataStream | None = None
        self._symbols: list[str] = []
        self._callback: Callable[[Bar], Awaitable[None] | None] | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._watchdog_task: asyncio.Task[None] | None = None
        # Bar aggregation state per symbol
        self._pending_bars: dict[str, list[Bar]] = {}
        self._bars_needed: dict[str, int] = {}  # Target bars for current interval per symbol
        self._bar_interval_minutes = self._parse_interval_minutes()
        # Watchdog state
        self._last_bar_time: datetime | None = None
        # Connection monitoring
        self._connection_monitor = ConnectionMonitor(
            component="feed",
            config=reconnection_config or DEFAULT_FEED_RECONNECTION_CONFIG,
            on_state_change=on_connection_state,
        )

    def _parse_interval_minutes(self) -> int:
        """Parse bar_interval config into minutes."""
        interval = get_engine_config().bar_interval
        if interval.endswith("m"):
            return int(interval[:-1])
        elif interval.endswith("h"):
            return int(interval[:-1]) * 60
        return 1  # Default to 1 minute

    def _ensure_credentials(self) -> tuple[str, str, DataFeed]:
        """Get credentials and data feed, raising if not available (lazy initialization)."""
        if self._api_key is not None and self._secret_key is not None and self._data_feed is not None:
            return self._api_key, self._secret_key, self._data_feed

        config = get_engine_config().alpaca

        # Environment variables take priority over config file
        api_key = os.environ.get(ALPACA_API_KEY_ENV) or config.api_key
        secret_key = os.environ.get(ALPACA_SECRET_KEY_ENV) or config.secret_key

        if not api_key or not secret_key:
            raise ValueError(
                f"Alpaca API credentials not found. "
                f"Set {ALPACA_API_KEY_ENV} and {ALPACA_SECRET_KEY_ENV} environment variables, "
                f"or configure in tradingbot.toml under [tradingbot.engine.alpaca]."
            )

        # Parse data feed from config
        data_feed = DataFeed.SIP if config.data_feed.lower() == "sip" else DataFeed.IEX

        self._api_key = api_key
        self._secret_key = secret_key
        self._data_feed = data_feed
        return api_key, secret_key, data_feed

    @property
    def name(self) -> str:
        return "alpaca"

    @property
    def is_connected(self) -> bool:
        # Keep backward compatibility: return True when running
        # Use connection_state property for detailed state
        return self._running

    @property
    def connection_state(self) -> ConnectionState:
        """Get current connection state."""
        return self._connection_monitor.state

    @property
    def is_reconnecting(self) -> bool:
        """Check if feed is currently reconnecting."""
        return self._connection_monitor.is_reconnecting

    def set_connection_callback(self, callback: ConnectionStateCallback) -> None:
        """Set the connection state callback after instantiation.

        This allows wiring the callback to a hub after the feed is created
        via the registry (which doesn't pass constructor arguments).
        """
        self._connection_monitor.on_state_change = callback

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
        self._last_bar_time = datetime.now()  # Initialize to avoid immediate stale detection
        self._task = asyncio.create_task(self._run_stream())
        self._watchdog_task = asyncio.create_task(self._run_watchdog())

    async def stop(self) -> None:
        """Stop the WebSocket connection."""
        self._running = False

        if self._watchdog_task:
            self._watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watchdog_task
            self._watchdog_task = None

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
        api_key, secret_key, data_feed = self._ensure_credentials()

        # Backfill missing 1m bars for current interval before starting stream
        if self._bar_interval_minutes > 1:
            await self._backfill_current_interval()

        while self._running:
            try:
                self._stream = StockDataStream(api_key, secret_key, feed=data_feed)

                # Subscribe to bars with async handler
                self._stream.subscribe_bars(self._handle_bar_async, *self._symbols)

                # Mark as connected
                self._connection_monitor.set_connected()

                interval = get_engine_config().bar_interval
                feed_name = "SIP" if data_feed == DataFeed.SIP else "IEX"
                logger.info(
                    f"Connected to Alpaca WebSocket ({feed_name} feed). Subscribed: {', '.join(self._symbols)} (1m bars → {interval})"
                )
                logger.info("Waiting for market data (bars arrive during market hours: 9:30 AM - 4:00 PM ET)")

                # Run in a thread since StockDataStream.run() is blocking
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._stream.run)

            except Exception as e:
                if not self._running:
                    break

                error_msg = str(e)
                self._connection_monitor.set_disconnected(error_msg)
                logger.warning(f"Connection lost: {error_msg}")

                # Attempt reconnection with exponential backoff
                # Note: connect() only sets up the stream; the main loop runs it
                async def connect() -> None:
                    nonlocal api_key, secret_key, data_feed
                    # Create and configure the stream
                    self._stream = StockDataStream(api_key, secret_key, feed=data_feed)
                    self._stream.subscribe_bars(self._handle_bar_async, *self._symbols)
                    # Connection test: alpaca-py validates on subscribe
                    # The actual run() will happen in the main loop after reconnect succeeds

                reconnected = await self._connection_monitor.reconnect(
                    connect_fn=connect,
                    should_stop=lambda: not self._running,
                )

                if not reconnected:
                    logger.error("Feed reconnection failed after max attempts")
                    self._running = False
                    break

                # Reconnection successful - mark as connected and run the stream
                self._connection_monitor.set_connected()
                interval = get_engine_config().bar_interval
                feed_name = "SIP" if data_feed == DataFeed.SIP else "IEX"
                logger.info(
                    f"Reconnected to Alpaca WebSocket ({feed_name} feed). Subscribed: {', '.join(self._symbols)} (1m bars → {interval})"
                )
                # Run the reconnected stream (blocking call in executor)
                # Stream was set in connect(), assert for type safety
                assert self._stream is not None
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._stream.run)

    async def _run_watchdog(self) -> None:
        """Monitor connection health and force reconnect if stale.

        During market hours, we expect bars every minute. If no bars arrive
        for STALE_CONNECTION_SECONDS, the connection is likely dead and we
        force a reconnect by stopping the stream.
        """
        while self._running:
            await asyncio.sleep(30)  # Check every 30 seconds

            if not self._running or not self._connection_monitor.is_connected:
                continue

            if self._last_bar_time is None:
                continue

            # Only check during US market hours (9:30 AM - 4:00 PM ET)
            from zoneinfo import ZoneInfo

            et_tz = ZoneInfo("America/New_York")
            now_et = datetime.now(et_tz)
            market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)

            if not (market_open <= now_et <= market_close):
                continue

            if now_et.weekday() >= 5:
                continue

            seconds_since_bar = (datetime.now() - self._last_bar_time).total_seconds()

            if seconds_since_bar > STALE_CONNECTION_SECONDS:
                logger.warning(
                    f"No bars received for {seconds_since_bar:.0f}s during market hours - connection may be stale"
                )

                # Force disconnect to trigger reconnection
                self._connection_monitor.set_disconnected("Stale connection (no data)")

                if self._stream:
                    logger.info("Stopping stale stream to force reconnection...")
                    with contextlib.suppress(Exception):
                        self._stream.stop()

    async def _backfill_current_interval(self) -> None:
        """Fetch historical 1m bars to complete the current interval.

        If we start at 9:32 with a 5m interval, we need bars for :30, :31
        to have a complete 5m bar when :34 arrives.
        """
        from datetime import UTC

        api_key, secret_key, data_feed = self._ensure_credentials()
        interval = self._bar_interval_minutes

        # Get current time in UTC
        now = datetime.now(UTC)
        current_minute = now.minute
        position_in_interval = current_minute % interval

        # If at interval boundary, no backfill needed
        if position_in_interval == 0:
            return

        # Calculate how many bars we need to backfill
        bars_to_fetch = position_in_interval

        # Calculate start time for the interval (aligned to boundary)
        interval_start_minute = current_minute - position_in_interval
        start_time = now.replace(minute=interval_start_minute, second=0, microsecond=0)
        # End time is just before current minute (we'll get live bar for current)
        end_time = now.replace(second=0, microsecond=0)

        logger.info(f"Backfilling {bars_to_fetch} bar(s) for current {interval}m interval...")

        try:
            # Fetch 1m bars for each symbol
            loop = asyncio.get_running_loop()
            client = await loop.run_in_executor(None, lambda: StockHistoricalDataClient(api_key, secret_key))

            for symbol in self._symbols:
                request = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=TimeFrame(1, TimeFrameUnit.Minute),
                    start=start_time,
                    end=end_time,
                    feed=data_feed,
                )

                def fetch_bars(req: StockBarsRequest = request) -> Any:
                    return client.get_stock_bars(req)

                response = await loop.run_in_executor(None, fetch_bars)
                # Cast to BarSet for proper typing
                bars_response: BarSet = response

                # Note: BarSet's __contains__ doesn't work correctly, access via .data dict
                symbol_bars = bars_response.data.get(symbol, []) if bars_response.data else []
                if not symbol_bars:
                    logger.warning(f"No historical bars available for {symbol}")
                    continue

                # Pre-populate pending bars
                self._pending_bars[symbol] = []
                for alpaca_bar in symbol_bars:
                    bar = Bar(
                        symbol=symbol,
                        datetime=alpaca_bar.timestamp.replace(tzinfo=None)
                        if alpaca_bar.timestamp.tzinfo
                        else alpaca_bar.timestamp,
                        open=float(alpaca_bar.open),
                        high=float(alpaca_bar.high),
                        low=float(alpaca_bar.low),
                        close=float(alpaca_bar.close),
                        volume=int(alpaca_bar.volume),
                    )
                    self._pending_bars[symbol].append(bar)

                # Set bars_needed to full interval since we're backfilling from start
                self._bars_needed[symbol] = interval

                fetched = len(self._pending_bars[symbol])
                logger.info(f"Backfilled {fetched}/{bars_to_fetch} bar(s) for {symbol}")

        except Exception as e:
            logger.warning(f"Backfill failed: {e}. Starting fresh.")
            # Clear any partial state on failure
            self._pending_bars.clear()
            self._bars_needed.clear()

    async def _handle_bar_async(self, alpaca_bar: Any) -> None:
        """Handle incoming bar data from Alpaca (async handler for SDK).

        If bar_interval > 1m, aggregates bars before emitting.
        """
        if not self._callback:
            return

        from datetime import UTC

        # Log bar arrival with wall clock time for debugging latency
        now = datetime.now(UTC)
        bar_time = alpaca_bar.timestamp.replace(tzinfo=None) if alpaca_bar.timestamp.tzinfo else alpaca_bar.timestamp
        latency_sec = (now.replace(tzinfo=None) - bar_time).total_seconds()
        logger.info(
            f"1m bar: {alpaca_bar.symbol} {bar_time.strftime('%H:%M')} @ ${alpaca_bar.close:.2f} (latency: {latency_sec:.0f}s)"
        )

        # Update watchdog timestamp
        self._last_bar_time = datetime.now()

        # Convert Alpaca bar to our Bar model (realtime 1m bar)
        bar = Bar(
            symbol=alpaca_bar.symbol,
            datetime=bar_time,
            open=float(alpaca_bar.open),
            high=float(alpaca_bar.high),
            low=float(alpaca_bar.low),
            close=float(alpaca_bar.close),
            volume=int(alpaca_bar.volume),
            origin=BarOrigin.REALTIME,
        )

        # Emit 1m realtime bar for chart updates
        result = self._callback(bar)
        if asyncio.iscoroutine(result):
            await result

        # If 1m interval, realtime bar is also the aggregated bar
        if self._bar_interval_minutes == 1:
            self._persist_bar(bar)
            return

        # Aggregate bars for larger intervals
        aggregated = self._aggregate_bar(bar)
        if aggregated:
            logger.info(
                f"{self._bar_interval_minutes}m bar: {aggregated.symbol} {aggregated.datetime.strftime('%H:%M')} @ ${aggregated.close:.2f}"
            )
            self._persist_bar(aggregated)
            result = self._callback(aggregated)
            if asyncio.iscoroutine(result):
                await result

    def _aggregate_bar(self, bar: Bar) -> Bar | None:
        """Aggregate 1m bars into configured interval using time alignment.

        Bars are aggregated at natural time boundaries (e.g., 5m bars emit at
        :00, :05, :10...). Returns aggregated bar when interval completes, None otherwise.

        Time alignment example for 5m bars:
        - 5m boundaries are :00, :05, :10, :15... (intervals end at :04, :09, :14...)
        - If we start at 9:32, we need bars for :32, :33, :34 (3 bars) to complete at :34
        - Progress shows "collected / bars_needed_for_this_interval"
        """
        symbol = bar.symbol
        interval = self._bar_interval_minutes
        bar_minute = bar.datetime.minute

        # Calculate position within the current interval (0-indexed)
        # For 5m: minute 32 -> position 2 (32 % 5 = 2), meaning 3rd bar of interval
        position_in_interval = bar_minute % interval

        # Check if this bar completes the interval (last position)
        is_complete = position_in_interval == interval - 1

        # Initialize or reset pending bars at interval start
        if symbol not in self._pending_bars or not self._pending_bars[symbol]:
            self._pending_bars[symbol] = []
            # Calculate how many bars we need from this starting position
            # Position 0 -> need 5 bars, Position 2 -> need 3 bars
            self._bars_needed[symbol] = interval - position_in_interval

        pending = self._pending_bars[symbol]
        pending.append(bar)

        if not is_complete:
            return None

        # Calculate aligned start time for the interval
        interval_start_minute = bar_minute - (interval - 1)
        aligned_start = bar.datetime.replace(minute=interval_start_minute, second=0, microsecond=0)

        # Only use bars that belong to this interval (filter out any from previous partial interval)
        valid_bars = [b for b in pending if b.datetime.minute >= interval_start_minute]
        if not valid_bars:
            valid_bars = pending  # Fallback if filtering removes everything

        # Aggregate OHLCV
        aggregated = Bar(
            symbol=symbol,
            datetime=aligned_start,
            open=valid_bars[0].open,
            high=max(b.high for b in valid_bars),
            low=min(b.low for b in valid_bars),
            close=valid_bars[-1].close,
            volume=sum(b.volume for b in valid_bars),
            origin=BarOrigin.AGGREGATED,
        )

        # Clear pending bars for next interval
        self._pending_bars[symbol] = []
        self._bars_needed.pop(symbol, None)
        return aggregated

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

        # Persist to cache (non-blocking)
        self._persist_bar(bar)

        result = self._callback(bar)

        # If callback returns a coroutine, schedule it
        if asyncio.iscoroutine(result):
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(result, loop)
            else:
                loop.run_until_complete(result)

    def _persist_bar(self, bar: Bar) -> None:
        """Persist bar to cache asynchronously (non-blocking)."""
        if not get_cache_config().enabled:
            return

        interval = get_engine_config().bar_interval
        df = pl.DataFrame(
            {
                "datetime": [bar.datetime],
                "open": [bar.open],
                "high": [bar.high],
                "low": [bar.low],
                "close": [bar.close],
                "volume": [bar.volume],
            }
        )

        # Run in background to not block trading
        try:
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, lambda: insert_bars(df, bar.symbol, interval, "alpaca"))
        except RuntimeError:
            # No event loop running, persist synchronously
            insert_bars(df, bar.symbol, interval, "alpaca")

    def history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        period: str = "1y",
        interval: str = "1h",
        debug: bool = False,
    ) -> pl.DataFrame:
        """Fetch historical bar data from Alpaca."""
        api_key, secret_key, data_feed = self._ensure_credentials()
        client = StockHistoricalDataClient(api_key, secret_key)

        timeframe = self._parse_interval(interval)

        # Build request using configured data feed
        if start_date and end_date:
            start_dt = datetime.fromisoformat(start_date)
            end_dt = datetime.fromisoformat(end_date)
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=timeframe,
                start=start_dt,
                end=end_dt,
                feed=data_feed,
            )
        else:
            # Convert period to start date
            start_dt = self._period_to_start(period)
            end_dt = None
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=timeframe,
                start=start_dt,
                feed=data_feed,
            )

        logger.debug(
            f"Requesting {symbol} {interval} from {start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d') if end_dt else 'now'}"
        )

        response = client.get_stock_bars(request)
        # Cast to BarSet for proper typing (API can return RawData but we always get BarSet)
        bars: BarSet = response  # type: ignore[assignment]

        if debug:
            logger.debug(f"Response type: {type(bars).__name__}")
            logger.debug(f"Available symbols: {list(bars.data.keys()) if bars.data else []}")
            symbol_bars_debug = bars.data.get(symbol, []) if bars.data else []
            logger.debug(f"Bars for {symbol}: {len(symbol_bars_debug)}")
            if symbol_bars_debug:
                first = symbol_bars_debug[0]
                last = symbol_bars_debug[-1]
                logger.debug(
                    f"First: {first.timestamp} O={first.open} H={first.high} L={first.low} C={first.close} V={first.volume}"
                )
                logger.debug(
                    f"Last:  {last.timestamp} O={last.open} H={last.high} L={last.low} C={last.close} V={last.volume}"
                )

        # Convert to DataFrame
        # Note: BarSet's __contains__ doesn't work correctly, access via .data dict
        data: list[dict[str, Any]] = []
        symbol_bars = bars.data.get(symbol, []) if bars.data else []
        for bar in symbol_bars:
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

        Supports formats like: 2y, 1mo, 3mo, 3m, 5d, 1w
        """
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
        elif unit == "m":
            # Treat "m" as months (not minutes - use interval for that)
            return now - timedelta(days=amount * 30)
        elif unit == "y":
            return now - timedelta(days=amount * 365)
        else:
            return now - timedelta(days=365)  # Default 1 year

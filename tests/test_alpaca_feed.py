"""Tests for Alpaca data feed integration."""

import asyncio
import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from tradingbot._components.feeds.plugins.alpaca import AlpacaFeed
from tradingbot.types import Bar


@pytest.fixture
def mock_env():
    """Set up mock environment variables."""
    with patch.dict(
        os.environ,
        {
            "ALPACA_API_KEY": "test_key",
            "ALPACA_SECRET_KEY": "test_secret",
        },
    ):
        yield


class TestAlpacaFeedInit:
    def test_raises_without_credentials(self):
        """Missing credentials should raise ValueError on first use."""
        with patch.dict(os.environ, {}, clear=True), pytest.raises(ValueError, match="credentials not found"):
            feed = AlpacaFeed()
            feed._ensure_credentials()  # Trigger lazy initialization

    def test_raises_without_api_key(self):
        """Missing API key should raise ValueError on first use."""
        with (
            patch.dict(os.environ, {"ALPACA_SECRET_KEY": "secret"}, clear=True),
            pytest.raises(ValueError, match="credentials not found"),
        ):
            feed = AlpacaFeed()
            feed._ensure_credentials()  # Trigger lazy initialization

    def test_raises_without_secret_key(self):
        """Missing secret key should raise ValueError on first use."""
        with (
            patch.dict(os.environ, {"ALPACA_API_KEY": "key"}, clear=True),
            pytest.raises(ValueError, match="credentials not found"),
        ):
            feed = AlpacaFeed()
            feed._ensure_credentials()  # Trigger lazy initialization

    def test_initializes_with_credentials(self, mock_env):
        """Successful initialization with credentials."""
        feed = AlpacaFeed()
        assert feed.name == "alpaca"
        assert feed.is_connected is False


class TestAlpacaFeedSubscription:
    def test_subscribe(self, mock_env):
        """Subscribe to symbols."""
        feed = AlpacaFeed()
        received_bars: list[Bar] = []

        def callback(bar: Bar) -> None:
            received_bars.append(bar)

        asyncio.run(feed.subscribe(["SPY", "QQQ"], callback))

        assert feed._symbols == ["SPY", "QQQ"]
        assert feed._callback is callback

    def test_subscribe_single_symbol(self, mock_env):
        """Subscribe to a single symbol."""
        feed = AlpacaFeed()

        def callback(bar: Bar) -> None:
            pass

        asyncio.run(feed.subscribe(["AAPL"], callback))

        assert feed._symbols == ["AAPL"]

    def test_unsubscribe(self, mock_env):
        """Unsubscribe from symbols."""
        feed = AlpacaFeed()

        def callback(bar: Bar) -> None:
            pass

        async def run_test() -> None:
            await feed.subscribe(["SPY", "QQQ", "AAPL"], callback)
            await feed.unsubscribe(["QQQ"])

        asyncio.run(run_test())

        assert feed._symbols == ["SPY", "AAPL"]

    def test_unsubscribe_all(self, mock_env):
        """Unsubscribe from all symbols."""
        feed = AlpacaFeed()

        def callback(bar: Bar) -> None:
            pass

        async def run_test() -> None:
            await feed.subscribe(["SPY", "QQQ"], callback)
            await feed.unsubscribe(["SPY", "QQQ"])

        asyncio.run(run_test())

        assert feed._symbols == []


class TestAlpacaFeedBarConversion:
    def test_bar_conversion(self, mock_env):
        """Alpaca bars should be correctly converted to internal Bar model."""
        feed = AlpacaFeed()
        received_bars: list[Bar] = []

        def capture_bar(bar: Bar) -> None:
            received_bars.append(bar)

        asyncio.run(feed.subscribe(["SPY"], capture_bar))

        # Create mock Alpaca bar
        mock_alpaca_bar = MagicMock()
        mock_alpaca_bar.symbol = "SPY"
        mock_alpaca_bar.timestamp = datetime(2024, 1, 15, 10, 30, 0)
        mock_alpaca_bar.open = 450.00
        mock_alpaca_bar.high = 452.00
        mock_alpaca_bar.low = 449.00
        mock_alpaca_bar.close = 451.50
        mock_alpaca_bar.volume = 1000000

        feed._handle_bar_sync(mock_alpaca_bar)

        assert len(received_bars) == 1
        bar = received_bars[0]
        assert bar.symbol == "SPY"
        assert bar.open == 450.00
        assert bar.high == 452.00
        assert bar.low == 449.00
        assert bar.close == 451.50
        assert bar.volume == 1000000

    def test_bar_conversion_with_timezone(self, mock_env):
        """Handle timezone-aware timestamps."""
        feed = AlpacaFeed()
        received_bars: list[Bar] = []

        def capture_bar(bar: Bar) -> None:
            received_bars.append(bar)

        asyncio.run(feed.subscribe(["SPY"], capture_bar))

        mock_alpaca_bar = MagicMock()
        mock_alpaca_bar.symbol = "SPY"
        mock_alpaca_bar.timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_alpaca_bar.open = 450.00
        mock_alpaca_bar.high = 452.00
        mock_alpaca_bar.low = 449.00
        mock_alpaca_bar.close = 451.50
        mock_alpaca_bar.volume = 1000000

        feed._handle_bar_sync(mock_alpaca_bar)

        assert len(received_bars) == 1
        bar = received_bars[0]
        # Timezone should be stripped
        assert bar.datetime.tzinfo is None

    def test_bar_no_callback(self, mock_env):
        """Handle bar when no callback is registered."""
        feed = AlpacaFeed()

        mock_alpaca_bar = MagicMock()
        mock_alpaca_bar.symbol = "SPY"
        mock_alpaca_bar.timestamp = datetime(2024, 1, 15, 10, 30, 0)
        mock_alpaca_bar.open = 450.00
        mock_alpaca_bar.high = 452.00
        mock_alpaca_bar.low = 449.00
        mock_alpaca_bar.close = 451.50
        mock_alpaca_bar.volume = 1000000

        # Should not raise
        feed._handle_bar_sync(mock_alpaca_bar)


class TestAlpacaFeedLifecycle:
    def test_stop_not_started(self, mock_env):
        """Stop should handle not started state."""
        feed = AlpacaFeed()
        # Should not raise
        asyncio.run(feed.stop())

    def test_is_connected_false_when_stopped(self, mock_env):
        """is_connected should be False when not running."""
        feed = AlpacaFeed()
        assert feed.is_connected is False


class TestAlpacaFeedProperties:
    def test_name(self, mock_env):
        """Name property returns 'alpaca'."""
        feed = AlpacaFeed()
        assert feed.name == "alpaca"

    def test_is_connected_default(self, mock_env):
        """is_connected is False by default."""
        feed = AlpacaFeed()
        assert feed.is_connected is False

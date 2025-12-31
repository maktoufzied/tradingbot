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
    """Set up mock environment variables and disable cache."""
    with (
        patch.dict(
            os.environ,
            {
                "ALPACA_API_KEY": "test_key",
                "ALPACA_SECRET_KEY": "test_secret",
            },
        ),
        patch("tradingbot._components.feeds.plugins.alpaca.get_cache_config") as mock_cache,
    ):
        mock_cache.return_value.enabled = False
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

        asyncio.run(feed.subscribe(["MSFT", "QQQ"], callback))

        assert feed._symbols == ["MSFT", "QQQ"]
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
            await feed.subscribe(["MSFT", "QQQ", "AAPL"], callback)
            await feed.unsubscribe(["QQQ"])

        asyncio.run(run_test())

        assert feed._symbols == ["MSFT", "AAPL"]

    def test_unsubscribe_all(self, mock_env):
        """Unsubscribe from all symbols."""
        feed = AlpacaFeed()

        def callback(bar: Bar) -> None:
            pass

        async def run_test() -> None:
            await feed.subscribe(["MSFT", "QQQ"], callback)
            await feed.unsubscribe(["MSFT", "QQQ"])

        asyncio.run(run_test())

        assert feed._symbols == []


class TestAlpacaFeedBarConversion:
    def test_bar_conversion(self, mock_env):
        """Alpaca bars should be correctly converted to internal Bar model."""
        feed = AlpacaFeed()
        received_bars: list[Bar] = []

        def capture_bar(bar: Bar) -> None:
            received_bars.append(bar)

        asyncio.run(feed.subscribe(["MSFT"], capture_bar))

        # Create mock Alpaca bar
        mock_alpaca_bar = MagicMock()
        mock_alpaca_bar.symbol = "MSFT"
        mock_alpaca_bar.timestamp = datetime(2024, 1, 15, 10, 30, 0)
        mock_alpaca_bar.open = 450.00
        mock_alpaca_bar.high = 452.00
        mock_alpaca_bar.low = 449.00
        mock_alpaca_bar.close = 451.50
        mock_alpaca_bar.volume = 1000000

        feed._handle_bar_sync(mock_alpaca_bar)

        assert len(received_bars) == 1
        bar = received_bars[0]
        assert bar.symbol == "MSFT"
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

        asyncio.run(feed.subscribe(["MSFT"], capture_bar))

        mock_alpaca_bar = MagicMock()
        mock_alpaca_bar.symbol = "MSFT"
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
        mock_alpaca_bar.symbol = "MSFT"
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


class TestAlpacaFeedBarAggregation:
    """Tests for time-aligned bar aggregation."""

    def _make_bar(self, symbol: str, minute: int, price: float) -> MagicMock:
        """Create a mock Alpaca bar at a given minute."""
        bar = MagicMock()
        bar.symbol = symbol
        bar.timestamp = datetime(2024, 1, 15, 9, minute, 0)
        bar.open = price
        bar.high = price + 0.5
        bar.low = price - 0.5
        bar.close = price
        bar.volume = 1000
        return bar

    def test_aggregation_starting_at_boundary(self, mock_env):
        """Starting at :30 should need 5 bars to complete at :34."""
        with patch("tradingbot._components.feeds.plugins.alpaca.get_engine_config") as mock_cfg:
            mock_cfg.return_value.bar_interval = "5m"

            feed = AlpacaFeed()
            aggregated_bars: list[Bar] = []

            def on_bar(bar: Bar) -> None:
                aggregated_bars.append(bar)

            asyncio.run(feed.subscribe(["MSFT"], on_bar))

            # Send bars for minutes 30, 31, 32, 33, 34
            for minute in range(30, 35):
                bar = self._make_bar("MSFT", minute, 450.0 + minute - 30)
                result = feed._aggregate_bar(
                    Bar(
                        symbol=bar.symbol,
                        datetime=bar.timestamp,
                        open=float(bar.open),
                        high=float(bar.high),
                        low=float(bar.low),
                        close=float(bar.close),
                        volume=int(bar.volume),
                    )
                )
                if result:
                    aggregated_bars.append(result)

            # Should have aggregated one 5m bar
            assert len(aggregated_bars) == 1
            assert aggregated_bars[0].datetime.minute == 30  # Aligned start

    def test_aggregation_starting_mid_interval(self, mock_env):
        """Starting at :32 should need 3 bars to complete at :34."""
        with patch("tradingbot._components.feeds.plugins.alpaca.get_engine_config") as mock_cfg:
            mock_cfg.return_value.bar_interval = "5m"

            feed = AlpacaFeed()

            # Send bars for minutes 32, 33, 34 (starting mid-interval)
            aggregated = None
            for minute in range(32, 35):
                bar = Bar(
                    symbol="MSFT",
                    datetime=datetime(2024, 1, 15, 9, minute, 0),
                    open=450.0,
                    high=451.0,
                    low=449.0,
                    close=450.0 + minute - 32,
                    volume=1000,
                )
                result = feed._aggregate_bar(bar)
                if result:
                    aggregated = result

            # Should have aggregated one bar at :34
            assert aggregated is not None
            assert aggregated.datetime.minute == 30  # Aligned to interval start

    def test_aggregation_single_bar_at_boundary(self, mock_env):
        """Starting at :34 should only need 1 bar."""
        with patch("tradingbot._components.feeds.plugins.alpaca.get_engine_config") as mock_cfg:
            mock_cfg.return_value.bar_interval = "5m"

            feed = AlpacaFeed()

            bar = Bar(
                symbol="MSFT",
                datetime=datetime(2024, 1, 15, 9, 34, 0),
                open=450.0,
                high=451.0,
                low=449.0,
                close=450.5,
                volume=1000,
            )
            result = feed._aggregate_bar(bar)

            # Should emit immediately since :34 is end of 5m interval
            assert result is not None
            assert result.datetime.minute == 30  # Aligned to interval start

    def test_aggregation_multiple_intervals(self, mock_env):
        """Test aggregation across multiple 5m intervals."""
        with patch("tradingbot._components.feeds.plugins.alpaca.get_engine_config") as mock_cfg:
            mock_cfg.return_value.bar_interval = "5m"

            feed = AlpacaFeed()
            aggregated_bars: list[Bar] = []

            # Send bars for minutes 30-39 (two complete intervals)
            for minute in range(30, 40):
                bar = Bar(
                    symbol="MSFT",
                    datetime=datetime(2024, 1, 15, 9, minute, 0),
                    open=450.0,
                    high=451.0,
                    low=449.0,
                    close=450.0,
                    volume=1000,
                )
                result = feed._aggregate_bar(bar)
                if result:
                    aggregated_bars.append(result)

            # Should have two 5m bars
            assert len(aggregated_bars) == 2
            assert aggregated_bars[0].datetime.minute == 30
            assert aggregated_bars[1].datetime.minute == 35

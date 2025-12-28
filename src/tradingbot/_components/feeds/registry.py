"""Registry for data feed implementations."""

from typing import TYPE_CHECKING

import polars as pl

from tradingbot.interfaces import DataFeedProtocol, Registry

if TYPE_CHECKING:
    from ..cache import CachedFeed


class FeedRegistry(Registry[DataFeedProtocol]):
    """Registry for data feed implementations."""


class DataFeed:
    """Facade for accessing data feeds."""

    _cached_feed: CachedFeed | None = None

    @staticmethod
    def get(name: str | None = None) -> DataFeedProtocol:
        """Get a feed by name, or the default feed."""
        return FeedRegistry().get(name)

    @classmethod
    def history(
        cls,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        period: str = "1y",
        interval: str = "1h",
        feed: str | None = None,
        refresh: bool = False,
    ) -> pl.DataFrame:
        """Fetch historical data, using cache by default.

        Args:
            symbol: Stock symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            period: Data period if dates not specified
            interval: Bar interval
            feed: Override feed (bypasses cache)
            refresh: Force re-fetch from API
        """
        # Bypass cache if specific feed requested
        if feed is not None:
            return FeedRegistry().get(feed).history(symbol, start_date, end_date, period, interval)

        # Use cached feed
        if cls._cached_feed is None:
            from ..cache import CachedFeed

            cls._cached_feed = CachedFeed()

        return cls._cached_feed.history(symbol, start_date, end_date, period, interval, refresh=refresh)


def get_registry() -> FeedRegistry:
    """Get the feed registry singleton."""
    return FeedRegistry()

"""Registry for data feed implementations."""

import polars as pl

from tradingbot.interfaces import DataFeedProtocol, Registry


class FeedRegistry(Registry[DataFeedProtocol]):
    """Registry for data feed implementations."""


class DataFeed:
    """Facade for accessing data feeds."""

    @staticmethod
    def get(name: str | None = None) -> DataFeedProtocol:
        """Get a feed by name, or the default feed."""
        return FeedRegistry().get(name)

    @staticmethod
    def history(
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        period: str = "2y",
        interval: str = "1d",
        feed: str | None = None,
    ) -> pl.DataFrame:
        """Fetch historical data using the specified feed."""
        return FeedRegistry().get(feed).history(symbol, start_date, end_date, period, interval)


def get_registry() -> FeedRegistry:
    """Get the feed registry singleton."""
    return FeedRegistry()

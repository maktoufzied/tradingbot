"""Cached wrapper for data feeds."""

from datetime import datetime, timedelta

import polars as pl

from tradingbot.config import get_cache_config
from tradingbot.interfaces import DataFeedProtocol

from .db import get_date_range, insert_bars, query_bars


class CachedFeed:
    """Feed wrapper that caches historical data in DuckDB."""

    def __init__(self, upstream: DataFeedProtocol | None = None) -> None:
        config = get_cache_config()

        if not config.enabled:
            self._cache_enabled = False
        else:
            self._cache_enabled = True

        # Use configured source or provided upstream
        if upstream:
            self._upstream = upstream
        elif config.source == "alpaca":
            # Lazy import to avoid circular dependency
            from ..feeds.plugins.alpaca import AlpacaFeed

            self._upstream = AlpacaFeed()
        else:
            from ..feeds.plugins.yahoo import YahooFeed

            self._upstream = YahooFeed()

    def history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        period: str = "2y",
        interval: str = "1d",
        refresh: bool = False,
    ) -> pl.DataFrame:
        """Get historical data, fetching from upstream if not cached.

        Args:
            symbol: Stock symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            period: Data period if dates not specified (e.g., "2y", "3mo")
            interval: Bar interval (e.g., "1d", "1h", "15m")
            refresh: Force re-fetch from upstream, ignoring cache
        """
        if not self._cache_enabled:
            return self._upstream.history(symbol, start_date, end_date, period, interval)

        # Determine date range we need
        if start_date and end_date:
            need_start = datetime.fromisoformat(start_date)
            need_end = datetime.fromisoformat(end_date)
        else:
            need_end = datetime.now()
            need_start = self._period_to_start(period, need_end)

        if refresh:
            # Force fetch everything from upstream
            df = self._upstream.history(symbol, start_date, end_date, period, interval)
            insert_bars(df, symbol, interval, get_cache_config().source)
            return df

        # Check what we have cached
        cached_start, cached_end = get_date_range(symbol, interval)

        if cached_start is None:
            # No cache - fetch everything
            df = self._upstream.history(symbol, start_date, end_date, period, interval)
            insert_bars(df, symbol, interval, get_cache_config().source)
        else:
            # Fetch gaps at the beginning
            if need_start < cached_start:
                try:
                    df = self._upstream.history(
                        symbol,
                        start_date=need_start.strftime("%Y-%m-%d"),
                        end_date=cached_start.strftime("%Y-%m-%d"),
                        interval=interval,
                    )
                    if not df.is_empty():
                        insert_bars(df, symbol, interval, get_cache_config().source)
                except ValueError:
                    pass  # No data for this range

            # Fetch gaps at the end (new data since last fetch)
            if cached_end is not None and need_end > cached_end:
                try:
                    df = self._upstream.history(
                        symbol,
                        start_date=cached_end.strftime("%Y-%m-%d"),
                        end_date=need_end.strftime("%Y-%m-%d"),
                        interval=interval,
                    )
                    if not df.is_empty():
                        insert_bars(df, symbol, interval, get_cache_config().source)
                except ValueError:
                    pass  # No new data

        # Return from cache
        return query_bars(symbol, interval, need_start, need_end)

    def _period_to_start(self, period: str, end: datetime) -> datetime:
        """Convert period string to start datetime.

        Supports formats: 2y, 1mo, 3mo, 5d, 1w
        """
        # Handle "mo" suffix for months
        if period.endswith("mo"):
            months = int(period[:-2])
            return end - timedelta(days=months * 30)

        amount = int(period[:-1])
        unit = period[-1]

        if unit == "d":
            return end - timedelta(days=amount)
        elif unit == "w":
            return end - timedelta(weeks=amount)
        elif unit == "y":
            return end - timedelta(days=amount * 365)
        else:
            return end - timedelta(days=730)  # Default 2 years

"""Cached wrapper for data feeds."""

from datetime import UTC, datetime, timedelta

import polars as pl

from tradingbot._components.logging import get_logger
from tradingbot.config import get_cache_config, get_engine_config
from tradingbot.interfaces import DataFeedProtocol

from .db import get_date_range, insert_bars, query_bars

logger = get_logger(__name__)


class CachedFeed:
    """Feed wrapper that caches historical data in DuckDB."""

    def __init__(self, upstream: DataFeedProtocol | None = None) -> None:
        cache_config = get_cache_config()
        engine_config = get_engine_config()

        if not cache_config.enabled:
            self._cache_enabled = False
        else:
            self._cache_enabled = True

        # Derive data source from provider: alpaca -> alpaca, paper -> yahoo
        self._source = "alpaca" if engine_config.provider == "alpaca" else "yahoo"

        # Use provided upstream or create from provider
        if upstream:
            self._upstream = upstream
        elif engine_config.provider == "alpaca":
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
        period: str = "1y",
        interval: str = "1h",
        refresh: bool = False,
        *,
        debug: bool = False,
    ) -> pl.DataFrame:
        """Get historical data, fetching from upstream if not cached.

        Args:
            symbol: Stock symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            period: Data period if dates not specified (e.g., "2y", "3mo")
            interval: Bar interval (e.g., "1d", "1h", "15m")
            refresh: Force re-fetch from upstream, ignoring cache
            debug: Print debug info from upstream feed
        """
        if not self._cache_enabled:
            return self._upstream.history(symbol, start_date, end_date, period, interval)

        # Determine date range we need (all datetimes are naive UTC)
        if start_date and end_date:
            need_start = datetime.fromisoformat(start_date)
            need_end = datetime.fromisoformat(end_date)
        else:
            need_end = datetime.now(UTC).replace(tzinfo=None)
            need_start = self._period_to_start(period, need_end)

        source = self._source

        if refresh:
            # Force fetch everything from upstream
            logger.debug("cache_refresh", symbol=symbol, interval=interval, source=source)
            df = self._upstream.history(symbol, start_date, end_date, period, interval, debug=debug)
            insert_bars(df, symbol, interval, source)
            return df

        # Check what we have cached
        cached_start, cached_end = get_date_range(symbol, interval)

        if cached_start is None:
            # No cache - fetch everything
            logger.debug("cache_miss", symbol=symbol, interval=interval, source=source)
            df = self._upstream.history(symbol, start_date, end_date, period, interval, debug=debug)
            insert_bars(df, symbol, interval, source)
        else:
            # Log cache hit
            logger.debug(
                "cache_hit",
                symbol=symbol,
                interval=interval,
                need_start=need_start.isoformat(),
                need_end=need_end.isoformat(),
                cached_start=cached_start.isoformat(),
                cached_end=cached_end.isoformat() if cached_end else None,
            )

            # For intraday intervals, compare timestamps; for daily+, compare dates
            is_intraday = interval in ("1m", "5m", "15m", "30m", "1h")

            # Fetch gaps at the beginning
            need_backfill = need_start < cached_start if is_intraday else need_start.date() < cached_start.date()
            if need_backfill:
                # Use ISO format for intraday to preserve time
                start_str = need_start.isoformat() if is_intraday else need_start.strftime("%Y-%m-%d")
                end_str = cached_start.isoformat() if is_intraday else cached_start.strftime("%Y-%m-%d")
                logger.debug("cache_backfill", symbol=symbol, start=start_str, end=end_str, source=source)
                try:
                    df = self._upstream.history(
                        symbol,
                        start_date=start_str,
                        end_date=end_str,
                        interval=interval,
                        debug=debug,
                    )
                    if not df.is_empty():
                        insert_bars(df, symbol, interval, source)
                        logger.debug("cache_backfill_complete", symbol=symbol, bars=len(df))
                except ValueError:
                    logger.debug("cache_backfill_empty", symbol=symbol)

            # Fetch gaps at the end (new data since last fetch)
            need_update = cached_end is not None and (
                need_end > cached_end if is_intraday else need_end.date() > cached_end.date()
            )
            if need_update and cached_end is not None:
                start_str = cached_end.isoformat() if is_intraday else cached_end.strftime("%Y-%m-%d")
                end_str = need_end.isoformat() if is_intraday else need_end.strftime("%Y-%m-%d")
                logger.debug("cache_update", symbol=symbol, start=start_str, end=end_str, source=source)
                try:
                    df = self._upstream.history(
                        symbol,
                        start_date=start_str,
                        end_date=end_str,
                        interval=interval,
                        debug=debug,
                    )
                    if not df.is_empty():
                        insert_bars(df, symbol, interval, source)
                        logger.debug("cache_update_complete", symbol=symbol, bars=len(df))
                except ValueError:
                    logger.debug("cache_update_empty", symbol=symbol)

        # Return from cache
        return query_bars(symbol, interval, need_start, need_end)

    def _period_to_start(self, period: str, end: datetime) -> datetime:
        """Convert period string to start datetime.

        Supports formats: 2y, 1mo, 3mo, 3m, 5d, 1w
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
        elif unit == "m":
            # Treat "m" as months (not minutes - use interval for that)
            return end - timedelta(days=amount * 30)
        elif unit == "y":
            return end - timedelta(days=amount * 365)
        else:
            return end - timedelta(days=365)  # Default 1 year

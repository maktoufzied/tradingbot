"""Smart caching layer for fetched data using Parquet format."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final

import polars as pl

if TYPE_CHECKING:
    from .protocol import DataFetcherProtocol

# Cooldown period before re-fetching (in hours)
FETCH_COOLDOWN_HOURS: Final[int] = 1


def _get_cache_dir() -> Path:
    """Get cache directory, creating if needed."""
    cache_dir = Path.home() / ".cache" / "tradingbot"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _get_cache_path(symbol: str, interval: str) -> Path:
    """Get cache file path for a symbol/interval combo."""
    safe_symbol = symbol.replace("/", "_").replace("=", "_")
    return _get_cache_dir() / f"{safe_symbol}_{interval}.parquet"


def _get_metadata_path() -> Path:
    """Get path to fetch metadata file."""
    return _get_cache_dir() / "fetch_metadata.json"


def _load_fetch_metadata() -> dict[str, str]:
    """Load fetch timestamps from metadata file."""
    path = _get_metadata_path()
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return {str(k): str(v) for k, v in data.items()}
        except Exception:
            return {}
    return {}


def _save_fetch_metadata(metadata: dict[str, str]) -> None:
    """Save fetch timestamps to metadata file."""
    path = _get_metadata_path()
    path.write_text(json.dumps(metadata, indent=2))


def _get_last_fetch_time(symbol: str, interval: str) -> datetime | None:
    """Get the last time we fetched this symbol/interval."""
    metadata = _load_fetch_metadata()
    key = f"{symbol}_{interval}"
    if key in metadata:
        try:
            return datetime.fromisoformat(metadata[key])
        except Exception:
            return None
    return None


def _set_last_fetch_time(symbol: str, interval: str) -> None:
    """Record that we just fetched this symbol/interval."""
    metadata = _load_fetch_metadata()
    key = f"{symbol}_{interval}"
    metadata[key] = datetime.now().isoformat()
    _save_fetch_metadata(metadata)


def _should_skip_fetch(symbol: str, interval: str) -> bool:
    """Check if we should skip fetching due to cooldown."""
    last_fetch = _get_last_fetch_time(symbol, interval)
    if last_fetch is None:
        return False
    cooldown = timedelta(hours=FETCH_COOLDOWN_HOURS)
    return datetime.now() - last_fetch < cooldown


def _period_to_start_date(period: str) -> datetime:
    """Convert period string (e.g., '2y', '6mo') to start date."""
    now = datetime.now()

    # Handle "mo" suffix (months)
    if period.endswith("mo"):
        value = int(period[:-2])
        return now - timedelta(days=value * 30)

    # Single char suffix
    unit = period[-1]
    value = int(period[:-1])

    if unit == "d":
        return now - timedelta(days=value)
    elif unit == "w":
        return now - timedelta(weeks=value)
    elif unit == "m":
        return now - timedelta(days=value * 30)
    elif unit == "y":
        return now - timedelta(days=value * 365)
    else:
        return now - timedelta(days=365 * 2)  # Default 2y


def load_cache(symbol: str, interval: str) -> pl.DataFrame | None:
    """Load cached data if it exists."""
    cache_path = _get_cache_path(symbol, interval)
    if cache_path.exists():
        try:
            return pl.read_parquet(cache_path)
        except Exception:
            return None
    return None


def save_cache(symbol: str, interval: str, df: pl.DataFrame) -> None:
    """Save data to cache."""
    cache_path = _get_cache_path(symbol, interval)
    df.write_parquet(cache_path, compression="snappy")


def get_missing_ranges(
    cached: pl.DataFrame | None,
    start_date: datetime,
    end_date: datetime,
) -> list[tuple[datetime, datetime]]:
    """Determine which date ranges need to be fetched.

    Returns list of (start, end) tuples for ranges not in cache.
    """
    if cached is None or cached.is_empty():
        return [(start_date, end_date)]

    cache_start_val = cached["datetime"].min()
    cache_end_val = cached["datetime"].max()
    if not isinstance(cache_start_val, datetime) or not isinstance(cache_end_val, datetime):
        return [(start_date, end_date)]
    cache_start: datetime = cache_start_val
    cache_end: datetime = cache_end_val

    missing: list[tuple[datetime, datetime]] = []

    # Need data before cache start?
    if start_date < cache_start:
        missing.append((start_date, cache_start - timedelta(days=1)))

    # Need data after cache end?
    if end_date > cache_end:
        missing.append((cache_end + timedelta(days=1), end_date))

    return missing


def merge_dataframes(existing: pl.DataFrame | None, new: pl.DataFrame) -> pl.DataFrame:
    """Merge new data with existing cache, removing duplicates."""
    if existing is None or existing.is_empty():
        return new

    combined: pl.DataFrame = pl.concat([existing, new])
    combined = combined.unique(subset=["datetime"], keep="last")
    combined = combined.sort("datetime")
    return combined


class CachedFetcher:
    """Wrapper that adds caching to any fetcher."""

    def __init__(self, fetcher: DataFetcherProtocol) -> None:
        self._fetcher = fetcher

    def fetch(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        period: str = "2y",
        interval: str = "1d",
    ) -> pl.DataFrame:
        """Fetch data with smart caching."""
        # For short intraday periods, bypass cache and fetch directly using period
        # Yahoo Finance handles period="1d" specially for intraday data
        intraday_intervals = {"1m", "5m", "15m", "30m", "1h"}
        short_periods = {"1d", "5d"}
        if interval in intraday_intervals and period in short_periods and not start_date:
            print(f"[FETCH] {symbol}: Requesting {period} of {interval} bars...")
            return self._fetcher.fetch(symbol, period=period, interval=interval)

        # Determine date range needed
        if start_date and end_date:
            req_start = datetime.strptime(start_date, "%Y-%m-%d")
            req_end = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            req_start = _period_to_start_date(period)
            req_end = datetime.now()

        # Load existing cache
        cached = load_cache(symbol, interval)

        # Find what's missing
        missing_ranges = get_missing_ranges(cached, req_start, req_end)

        result: pl.DataFrame
        if not missing_ranges and cached is not None:
            # All data in cache
            dt_min, dt_max = cached["datetime"].min(), cached["datetime"].max()
            if isinstance(dt_min, datetime) and isinstance(dt_max, datetime):
                print(f"[CACHE HIT] {symbol}: {len(cached)} bars ({dt_min.date()} to {dt_max.date()})")
            result = cached
        elif cached is not None and _should_skip_fetch(symbol, interval):
            # Have cache and recently fetched - use cache without re-fetching
            dt_min, dt_max = cached["datetime"].min(), cached["datetime"].max()
            last_fetch = _get_last_fetch_time(symbol, interval)
            mins_ago = int((datetime.now() - last_fetch).total_seconds() // 60) if last_fetch else 0
            if isinstance(dt_min, datetime) and isinstance(dt_max, datetime):
                print(
                    f"[CACHE] {symbol}: {len(cached)} bars ({dt_min.date()} to {dt_max.date()}) - checked {mins_ago}m ago"
                )
            result = cached
        else:
            # Show cache status
            if cached is not None and not cached.is_empty():
                dt_min, dt_max = cached["datetime"].min(), cached["datetime"].max()
                if isinstance(dt_min, datetime) and isinstance(dt_max, datetime):
                    print(f"[CACHE] {symbol}: {len(cached)} bars cached ({dt_min.date()} to {dt_max.date()})")
            else:
                print(f"[CACHE] {symbol}: No cached data")

            # Fetch missing ranges
            new_data: list[pl.DataFrame] = []
            for range_start, range_end in missing_ranges:
                days_needed = (range_end - range_start).days + 1
                # For small gaps, use period instead of date range (more reliable)
                if days_needed <= 7:
                    print(f"[FETCH] {symbol}: Requesting last {days_needed}d of {interval} bars...")
                    try:
                        df = self._fetcher.fetch(symbol, period=f"{days_needed}d", interval=interval)
                        if not df.is_empty():
                            new_data.append(df)
                    except ValueError:
                        pass  # No data available, continue
                else:
                    print(f"[FETCH] {symbol}: Requesting {range_start.date()} to {range_end.date()}...")
                    df = self._fetcher.fetch(
                        symbol,
                        start_date=range_start.strftime("%Y-%m-%d"),
                        end_date=range_end.strftime("%Y-%m-%d"),
                        interval=interval,
                    )
                    if not df.is_empty():
                        new_data.append(df)

            # Record that we fetched
            _set_last_fetch_time(symbol, interval)

            # Merge with cache
            if new_data:
                combined_new = pl.concat(new_data)
                result = merge_dataframes(cached, combined_new)
                save_cache(symbol, interval, result)
                print(f"[CACHE] {symbol}: Saved {len(result)} bars to cache")
            elif cached is not None:
                result = cached
            else:
                raise ValueError(f"No data found for {symbol}")

        # Filter to requested range and return
        result = result.filter((pl.col("datetime") >= req_start) & (pl.col("datetime") <= req_end))

        print(
            f"[READY] {symbol}: {len(result)} bars ({result['datetime'][0].date()} to {result['datetime'][-1].date()})"
        )
        return result

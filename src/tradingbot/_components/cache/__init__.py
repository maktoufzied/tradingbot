"""Cache module for market data storage."""

from .cached_feed import CachedFeed
from .db import (
    aggregate_all_intervals,
    aggregate_bars,
    delete_bars,
    get_date_range,
    get_db_path,
    get_latest_bar,
    get_retention_policy,
    get_storage_stats,
    get_symbols,
    insert_bars,
    purge_old_bars,
    query_bars,
    run_maintenance,
)

__all__ = [
    "CachedFeed",
    "aggregate_all_intervals",
    "aggregate_bars",
    "delete_bars",
    "get_date_range",
    "get_db_path",
    "get_latest_bar",
    "get_retention_policy",
    "get_storage_stats",
    "get_symbols",
    "insert_bars",
    "purge_old_bars",
    "query_bars",
    "run_maintenance",
]

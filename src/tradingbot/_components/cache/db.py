"""DuckDB-based market data storage."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import polars as pl

from tradingbot.config import get_cache_config


def get_db_path() -> Path:
    """Get database path from config."""
    return get_cache_config().db_path


def get_connection() -> duckdb.DuckDBPyConnection:
    """Get database connection, creating schema if needed."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    _ensure_schema(conn)
    return conn


@contextmanager
def db_connection() -> Iterator[duckdb.DuckDBPyConnection]:
    """Context manager for database connection."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def _ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bars (
            symbol VARCHAR NOT NULL,
            interval VARCHAR NOT NULL,
            datetime TIMESTAMP NOT NULL,
            open DOUBLE NOT NULL,
            high DOUBLE NOT NULL,
            low DOUBLE NOT NULL,
            close DOUBLE NOT NULL,
            volume BIGINT NOT NULL,
            source VARCHAR NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, interval, datetime)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_bars_lookup
        ON bars (symbol, interval, datetime DESC)
    """)


def insert_bars(df: pl.DataFrame, symbol: str, interval: str, source: str) -> int:
    """Insert bars into database, handling duplicates via upsert."""
    if df.is_empty():
        return 0

    # Add metadata columns
    df = df.with_columns(
        [
            pl.lit(symbol).alias("symbol"),
            pl.lit(interval).alias("interval"),
            pl.lit(source).alias("source"),
        ]
    )

    with db_connection() as conn:
        # Use INSERT OR REPLACE for upsert behavior
        conn.execute("""
            INSERT OR REPLACE INTO bars
            (symbol, interval, datetime, open, high, low, close, volume, source)
            SELECT symbol, interval, datetime, open, high, low, close, volume, source
            FROM df
        """)
        return len(df)


def query_bars(
    symbol: str,
    interval: str,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
) -> pl.DataFrame:
    """Query bars from database."""
    query = """
        SELECT datetime, open, high, low, close, volume
        FROM bars
        WHERE symbol = ? AND interval = ?
    """
    params: list[Any] = [symbol, interval]

    if start:
        query += " AND datetime >= ?"
        params.append(start)
    if end:
        query += " AND datetime <= ?"
        params.append(end)

    query += " ORDER BY datetime ASC"

    if limit:
        query += f" LIMIT {limit}"

    with db_connection() as conn:
        result: pl.DataFrame = conn.execute(query, params).pl()
        return result


def get_latest_bar(symbol: str, interval: str) -> datetime | None:
    """Get timestamp of most recent bar in database."""
    with db_connection() as conn:
        result = conn.execute(
            """
            SELECT MAX(datetime) FROM bars
            WHERE symbol = ? AND interval = ?
            """,
            [symbol, interval],
        ).fetchone()
        return result[0] if result and result[0] else None


def get_date_range(symbol: str, interval: str) -> tuple[datetime | None, datetime | None]:
    """Get earliest and latest bar timestamps."""
    with db_connection() as conn:
        result = conn.execute(
            """
            SELECT MIN(datetime), MAX(datetime) FROM bars
            WHERE symbol = ? AND interval = ?
            """,
            [symbol, interval],
        ).fetchone()
        if result:
            return result[0], result[1]
        return None, None


def delete_bars(symbol: str, interval: str | None = None) -> int:
    """Delete bars for a symbol (optionally filtered by interval).

    Returns number of deleted rows.
    """
    with db_connection() as conn:
        # Count before delete (DuckDB doesn't reliably report rowcount)
        if interval:
            count_result = conn.execute(
                "SELECT COUNT(*) FROM bars WHERE symbol = ? AND interval = ?",
                [symbol, interval],
            ).fetchone()
            conn.execute(
                "DELETE FROM bars WHERE symbol = ? AND interval = ?",
                [symbol, interval],
            )
        else:
            count_result = conn.execute(
                "SELECT COUNT(*) FROM bars WHERE symbol = ?",
                [symbol],
            ).fetchone()
            conn.execute(
                "DELETE FROM bars WHERE symbol = ?",
                [symbol],
            )
        return count_result[0] if count_result else 0


def get_storage_stats() -> dict[str, Any]:
    """Get storage statistics for monitoring."""
    with db_connection() as conn:
        stats: dict[str, Any] = {}

        rows = conn.execute("""
            SELECT interval, COUNT(*) as count,
                   MIN(datetime) as earliest,
                   MAX(datetime) as latest
            FROM bars
            GROUP BY interval
        """).fetchall()

        stats["intervals"] = {row[0]: {"count": row[1], "earliest": row[2], "latest": row[3]} for row in rows}

        stats["total_rows"] = sum(r[1] for r in rows) if rows else 0

        db_path = get_db_path()
        if db_path.exists():
            stats["file_size_mb"] = db_path.stat().st_size / (1024 * 1024)
        else:
            stats["file_size_mb"] = 0

        return stats


def get_retention_policy() -> dict[str, int]:
    """Get retention policy from config."""
    return get_cache_config().retention.as_dict()


# Interval to minutes mapping
INTERVAL_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "1d": 1440,
}


def get_symbols() -> list[str]:
    """Get list of all symbols in database."""
    with db_connection() as conn:
        result = conn.execute("SELECT DISTINCT symbol FROM bars").fetchall()
        return [row[0] for row in result]


def aggregate_bars(symbol: str, source_interval: str, target_interval: str) -> int:
    """Aggregate bars from finer to coarser interval.

    Uses DuckDB's time_bucket for OHLCV aggregation:
    - Open: first value in bucket
    - High: max value in bucket
    - Low: min value in bucket
    - Close: last value in bucket
    - Volume: sum of all values in bucket

    Args:
        symbol: Stock symbol
        source_interval: Source interval (e.g., "1m")
        target_interval: Target interval (e.g., "5m")

    Returns:
        Number of aggregated bars created

    Example:
        aggregate_bars("SPY", "1m", "5m")
    """
    source_mins = INTERVAL_MINUTES.get(source_interval)
    target_mins = INTERVAL_MINUTES.get(target_interval)

    if source_mins is None:
        raise ValueError(f"Unknown source interval: {source_interval}")
    if target_mins is None:
        raise ValueError(f"Unknown target interval: {target_interval}")
    if target_mins <= source_mins:
        raise ValueError(f"Target interval ({target_interval}) must be larger than source ({source_interval})")

    with db_connection() as conn:
        # Check if source data exists
        source_count = conn.execute(
            "SELECT COUNT(*) FROM bars WHERE symbol = ? AND interval = ?",
            [symbol, source_interval],
        ).fetchone()

        if not source_count or source_count[0] == 0:
            return 0

        # Count existing bars before aggregation
        before_count = conn.execute(
            "SELECT COUNT(*) FROM bars WHERE symbol = ? AND interval = ?",
            [symbol, target_interval],
        ).fetchone()
        before = before_count[0] if before_count else 0

        # Use DuckDB's time_bucket for aggregation
        # FIRST_VALUE and LAST_VALUE with ORDER BY to get open/close correctly
        conn.execute(
            f"""
            INSERT OR REPLACE INTO bars
            (symbol, interval, datetime, open, high, low, close, volume, source)
            SELECT
                symbol,
                '{target_interval}' as interval,
                time_bucket(INTERVAL '{target_mins} minutes', datetime) as datetime,
                FIRST(open ORDER BY datetime) as open,
                MAX(high) as high,
                MIN(low) as low,
                LAST(close ORDER BY datetime) as close,
                SUM(volume) as volume,
                'aggregated' as source
            FROM bars
            WHERE symbol = ? AND interval = ?
            GROUP BY symbol, time_bucket(INTERVAL '{target_mins} minutes', datetime)
            """,
            [symbol, source_interval],
        )

        # Count after aggregation to get actual new bars
        after_count = conn.execute(
            "SELECT COUNT(*) FROM bars WHERE symbol = ? AND interval = ?",
            [symbol, target_interval],
        ).fetchone()
        after = after_count[0] if after_count else 0

        return after - before


def aggregate_all_intervals(symbol: str) -> dict[str, int]:
    """Aggregate 1m bars to all coarser intervals for a symbol.

    Aggregation chain: 1m → 5m → 15m → 1h → 1d

    Returns:
        Dict of {interval: bars_created}
    """
    results: dict[str, int] = {}

    # Check if we have 1m data
    with db_connection() as conn:
        has_1m = conn.execute(
            "SELECT 1 FROM bars WHERE symbol = ? AND interval = '1m' LIMIT 1",
            [symbol],
        ).fetchone()

    if not has_1m:
        return results

    # Aggregate in chain: 1m → 5m → 15m → 1h → 1d
    for target in ["5m", "15m", "1h", "1d"]:
        count = aggregate_bars(symbol, "1m", target)
        if count > 0:
            results[target] = count

    return results


def purge_old_bars(symbol: str | None = None) -> dict[str, int]:
    """Purge old bars according to retention policy.

    Args:
        symbol: Optional symbol to purge (default: all symbols)

    Returns:
        Dict of {interval: rows_deleted}
    """
    retention = get_retention_policy()
    deleted: dict[str, int] = {}

    with db_connection() as conn:
        for interval, days in retention.items():
            if days < 0:
                # Keep forever
                continue

            # Use UTC since all stored datetimes are naive UTC
            cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)

            # Count before delete
            if symbol:
                count_result = conn.execute(
                    "SELECT COUNT(*) FROM bars WHERE symbol = ? AND interval = ? AND datetime < ?",
                    [symbol, interval, cutoff],
                ).fetchone()
            else:
                count_result = conn.execute(
                    "SELECT COUNT(*) FROM bars WHERE interval = ? AND datetime < ?",
                    [interval, cutoff],
                ).fetchone()

            count = count_result[0] if count_result else 0

            if count > 0:
                # Delete old bars
                if symbol:
                    conn.execute(
                        "DELETE FROM bars WHERE symbol = ? AND interval = ? AND datetime < ?",
                        [symbol, interval, cutoff],
                    )
                else:
                    conn.execute(
                        "DELETE FROM bars WHERE interval = ? AND datetime < ?",
                        [interval, cutoff],
                    )
                deleted[interval] = count

    return deleted


def run_maintenance(
    symbol: str | None = None,
    aggregate: bool = True,
    purge: bool = True,
) -> dict[str, Any]:
    """Run cache maintenance: aggregate and purge old data.

    Args:
        symbol: Optional symbol to maintain (default: all symbols)
        aggregate: Whether to aggregate 1m bars to coarser intervals
        purge: Whether to purge old data per retention policy

    Returns:
        Dict with 'aggregated' and 'purged' results
    """
    results: dict[str, Any] = {
        "aggregated": {},
        "purged": {},
    }

    symbols = [symbol] if symbol else get_symbols()

    # Aggregate 1m bars to coarser intervals
    if aggregate:
        for sym in symbols:
            agg_results = aggregate_all_intervals(sym)
            if agg_results:
                results["aggregated"][sym] = agg_results

    # Purge old data per retention policy
    if purge:
        results["purged"] = purge_old_bars(symbol)

    return results

"""DuckDB-based market data storage."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
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

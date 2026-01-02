"""State persistence for crash recovery and trade history.

Persists positions to DuckDB for recovery after restarts, tracks session
boundaries, and stores trade history for analytics.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import duckdb

from tradingbot._components.cache.db import get_db_path
from tradingbot._components.logging import get_logger
from tradingbot.types import Direction, ExitReason, PartialExit, Position

logger = get_logger(__name__)


class StatsGroupBy(Enum):
    """Grouping options for trade statistics."""

    LIFETIME = "lifetime"
    DAILY = "daily"
    MONTHLY = "monthly"
    SYMBOL = "symbol"
    STRATEGY = "strategy"


@dataclass
class TradeRecord:
    """Trade record for persistence."""

    id: int | None
    symbol: str
    direction: Direction
    entered_at: datetime
    exited_at: datetime
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    exit_reason: ExitReason
    strategy: str | None = None
    preset: str | None = None


@dataclass
class TradeStats:
    """Aggregated trade statistics."""

    total_trades: int
    winners: int
    losers: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    avg_winner: float
    avg_loser: float
    profit_factor: float
    group_key: str | None = None  # e.g., date, month, symbol


# --- Connection Management ---


@contextmanager
def state_connection() -> Iterator[duckdb.DuckDBPyConnection]:
    """Context manager for state database connection."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    try:
        _ensure_state_schema(conn)
        yield conn
    finally:
        conn.close()


def _ensure_state_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create state tables if they don't exist."""
    # Positions table for crash recovery
    conn.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            symbol VARCHAR PRIMARY KEY,
            entry_price DOUBLE NOT NULL,
            entry_index INTEGER NOT NULL,
            entry_time TIMESTAMP NOT NULL,
            direction VARCHAR NOT NULL,
            size DOUBLE NOT NULL,
            stop_loss DOUBLE NOT NULL,
            take_profit DOUBLE NOT NULL,
            initial_stop_loss DOUBLE,
            remaining_size DOUBLE,
            partial_exits JSON,
            triggered_levels JSON,
            high_water_mark DOUBLE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Sessions table for tracking session boundaries
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY,
            started_at TIMESTAMP NOT NULL,
            ended_at TIMESTAMP,
            circuit_breaker_triggered BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create sequence for sessions if not exists
    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS sessions_id_seq START 1
    """)

    # Trades table for history and analytics
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY,
            symbol VARCHAR NOT NULL,
            direction VARCHAR NOT NULL,
            entered_at TIMESTAMP NOT NULL,
            exited_at TIMESTAMP NOT NULL,
            entry_price DOUBLE NOT NULL,
            exit_price DOUBLE NOT NULL,
            size DOUBLE NOT NULL,
            pnl DOUBLE NOT NULL,
            pnl_pct DOUBLE NOT NULL,
            exit_reason VARCHAR NOT NULL,
            strategy VARCHAR,
            preset VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create sequence for trades if not exists
    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS trades_id_seq START 1
    """)

    # Index for trade queries
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_trades_exited_at
        ON trades (exited_at DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_trades_symbol
        ON trades (symbol)
    """)


# --- Serialization Helpers ---


def _serialize_partial_exits(exits: list[PartialExit] | None) -> str | None:
    """Serialize partial exits to JSON."""
    if not exits:
        return None
    return json.dumps(
        [
            {
                "r_multiple": e.r_multiple,
                "exit_price": e.exit_price,
                "exit_size": e.exit_size,
                "pnl": e.pnl,
                "exit_time": e.exit_time.isoformat(),
            }
            for e in exits
        ]
    )


def _deserialize_partial_exits(data: str | None) -> list[PartialExit] | None:
    """Deserialize partial exits from JSON."""
    if not data:
        return None
    items = json.loads(data)
    return [
        PartialExit(
            r_multiple=item["r_multiple"],
            exit_price=item["exit_price"],
            exit_size=item["exit_size"],
            pnl=item["pnl"],
            exit_time=datetime.fromisoformat(item["exit_time"]),
        )
        for item in items
    ]


def _serialize_triggered_levels(levels: set[float] | None) -> str | None:
    """Serialize triggered levels to JSON."""
    if not levels:
        return None
    return json.dumps(list(levels))


def _deserialize_triggered_levels(data: str | None) -> set[float] | None:
    """Deserialize triggered levels from JSON."""
    if not data:
        return None
    return set(json.loads(data))


# --- Position CRUD ---


def save_position(symbol: str, position: Position) -> None:
    """Save or update a position in the database."""
    with state_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO positions
            (symbol, entry_price, entry_index, entry_time, direction, size,
             stop_loss, take_profit, initial_stop_loss, remaining_size,
             partial_exits, triggered_levels, high_water_mark, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                symbol,
                position.entry_price,
                position.entry_index,
                position.entry_time,
                position.direction,
                position.size,
                position.stop_loss,
                position.take_profit,
                position.initial_stop_loss,
                position.remaining_size,
                _serialize_partial_exits(position.partial_exits),
                _serialize_triggered_levels(position.triggered_levels),
                position.high_water_mark,
            ],
        )
    logger.debug("Saved position for %s", symbol)


def load_positions() -> dict[str, Position]:
    """Load all positions from the database."""
    with state_connection() as conn:
        rows = conn.execute("""
            SELECT symbol, entry_price, entry_index, entry_time, direction,
                   size, stop_loss, take_profit, initial_stop_loss,
                   remaining_size, partial_exits, triggered_levels, high_water_mark
            FROM positions
        """).fetchall()

    positions: dict[str, Position] = {}
    for row in rows:
        symbol = row[0]
        positions[symbol] = Position(
            entry_price=row[1],
            entry_index=row[2],
            entry_time=row[3],
            direction=row[4],
            size=row[5],
            stop_loss=row[6],
            take_profit=row[7],
            initial_stop_loss=row[8],
            remaining_size=row[9],
            partial_exits=_deserialize_partial_exits(row[10]),
            triggered_levels=_deserialize_triggered_levels(row[11]),
            high_water_mark=row[12],
        )
    return positions


def delete_position(symbol: str) -> None:
    """Delete a position from the database."""
    with state_connection() as conn:
        conn.execute("DELETE FROM positions WHERE symbol = ?", [symbol])
    logger.debug("Deleted position for %s", symbol)


def clear_all_positions() -> int:
    """Clear all positions. Returns count deleted."""
    with state_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM positions").fetchone()
        conn.execute("DELETE FROM positions")
        return count[0] if count else 0


# --- Session Management ---


def start_session() -> int:
    """Start a new session. Returns session ID."""
    with state_connection() as conn:
        result = conn.execute("""
            INSERT INTO sessions (id, started_at)
            VALUES (nextval('sessions_id_seq'), CURRENT_TIMESTAMP)
            RETURNING id
        """).fetchone()
        session_id = result[0] if result else 0
    logger.info("Started session %d", session_id)
    return session_id


def end_session(session_id: int) -> None:
    """End a session by setting ended_at."""
    with state_connection() as conn:
        conn.execute(
            "UPDATE sessions SET ended_at = CURRENT_TIMESTAMP WHERE id = ?",
            [session_id],
        )
    logger.info("Ended session %d", session_id)


def get_active_session() -> int | None:
    """Get ID of active session (ended_at IS NULL)."""
    with state_connection() as conn:
        result = conn.execute("""
            SELECT id FROM sessions
            WHERE ended_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1
        """).fetchone()
        return result[0] if result else None


def set_circuit_breaker(session_id: int) -> None:
    """Mark circuit breaker triggered for a session."""
    with state_connection() as conn:
        conn.execute(
            "UPDATE sessions SET circuit_breaker_triggered = TRUE WHERE id = ?",
            [session_id],
        )
    logger.warning("Circuit breaker triggered for session %d", session_id)


def was_circuit_breaker_triggered(session_id: int) -> bool:
    """Check if circuit breaker was triggered for a session."""
    with state_connection() as conn:
        result = conn.execute(
            "SELECT circuit_breaker_triggered FROM sessions WHERE id = ?",
            [session_id],
        ).fetchone()
        return bool(result[0]) if result else False


def get_last_session_info() -> dict[str, Any] | None:
    """Get info about the most recent session."""
    with state_connection() as conn:
        result = conn.execute("""
            SELECT id, started_at, ended_at, circuit_breaker_triggered
            FROM sessions
            ORDER BY started_at DESC
            LIMIT 1
        """).fetchone()
        if not result:
            return None
        return {
            "id": result[0],
            "started_at": result[1],
            "ended_at": result[2],
            "circuit_breaker_triggered": result[3],
            "ended_gracefully": result[2] is not None,
        }


# --- Trade History ---


def record_trade(
    symbol: str,
    direction: Direction,
    entered_at: datetime,
    exited_at: datetime,
    entry_price: float,
    exit_price: float,
    size: float,
    pnl: float,
    pnl_pct: float,
    exit_reason: ExitReason,
    strategy: str | None = None,
    preset: str | None = None,
) -> int:
    """Record a completed trade. Returns trade ID."""
    with state_connection() as conn:
        result = conn.execute(
            """
            INSERT INTO trades
            (id, symbol, direction, entered_at, exited_at, entry_price, exit_price,
             size, pnl, pnl_pct, exit_reason, strategy, preset)
            VALUES (nextval('trades_id_seq'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            [
                symbol,
                direction,
                entered_at,
                exited_at,
                entry_price,
                exit_price,
                size,
                pnl,
                pnl_pct,
                exit_reason,
                strategy,
                preset,
            ],
        ).fetchone()
        trade_id = result[0] if result else 0
    logger.info(
        "Recorded trade #%d: %s %s %.2f P&L $%.2f",
        trade_id,
        symbol,
        direction,
        size,
        pnl,
    )
    return trade_id


def get_trades(
    start: datetime | None = None,
    end: datetime | None = None,
    symbol: str | None = None,
    strategy: str | None = None,
    limit: int | None = None,
) -> list[TradeRecord]:
    """Query trades with optional filters."""
    query = "SELECT id, symbol, direction, entered_at, exited_at, entry_price, exit_price, size, pnl, pnl_pct, exit_reason, strategy, preset FROM trades WHERE 1=1"
    params: list[Any] = []

    if start:
        query += " AND exited_at >= ?"
        params.append(start)
    if end:
        query += " AND exited_at <= ?"
        params.append(end)
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol)
    if strategy:
        query += " AND strategy = ?"
        params.append(strategy)

    query += " ORDER BY exited_at DESC"

    if limit:
        query += " LIMIT ?"
        params.append(limit)

    with state_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [
        TradeRecord(
            id=row[0],
            symbol=row[1],
            direction=row[2],
            entered_at=row[3],
            exited_at=row[4],
            entry_price=row[5],
            exit_price=row[6],
            size=row[7],
            pnl=row[8],
            pnl_pct=row[9],
            exit_reason=row[10],
            strategy=row[11],
            preset=row[12],
        )
        for row in rows
    ]


def get_stats(group_by: StatsGroupBy = StatsGroupBy.LIFETIME) -> list[TradeStats]:
    """Compute trade statistics with optional grouping."""
    if group_by == StatsGroupBy.LIFETIME:
        group_expr = "'lifetime'"
        group_clause = ""
    elif group_by == StatsGroupBy.DAILY:
        group_expr = "DATE(exited_at)"
        group_clause = "GROUP BY DATE(exited_at)"
    elif group_by == StatsGroupBy.MONTHLY:
        group_expr = "strftime('%Y-%m', exited_at)"
        group_clause = "GROUP BY strftime('%Y-%m', exited_at)"
    elif group_by == StatsGroupBy.SYMBOL:
        group_expr = "symbol"
        group_clause = "GROUP BY symbol"
    elif group_by == StatsGroupBy.STRATEGY:
        group_expr = "COALESCE(strategy, 'unknown')"
        group_clause = "GROUP BY COALESCE(strategy, 'unknown')"
    else:
        raise ValueError(f"Unknown group_by: {group_by}")

    query = f"""
        SELECT
            {group_expr} as group_key,
            COUNT(*) as total_trades,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winners,
            SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losers,
            SUM(pnl) as total_pnl,
            AVG(pnl) as avg_pnl,
            AVG(CASE WHEN pnl > 0 THEN pnl END) as avg_winner,
            AVG(CASE WHEN pnl <= 0 THEN pnl END) as avg_loser,
            SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END) as gross_profit,
            ABS(SUM(CASE WHEN pnl < 0 THEN pnl ELSE 0 END)) as gross_loss
        FROM trades
        {group_clause}
        ORDER BY group_key DESC
    """

    with state_connection() as conn:
        rows = conn.execute(query).fetchall()

    results = []
    for row in rows:
        group_key = str(row[0]) if row[0] else None
        total_trades = row[1]
        winners = row[2] or 0
        losers = row[3] or 0
        total_pnl = row[4] or 0.0
        avg_pnl = row[5] or 0.0
        avg_winner = row[6] or 0.0
        avg_loser = row[7] or 0.0
        gross_profit = row[8] or 0.0
        gross_loss = row[9] or 0.0

        win_rate = (winners / total_trades * 100) if total_trades > 0 else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

        results.append(
            TradeStats(
                total_trades=total_trades,
                winners=winners,
                losers=losers,
                win_rate=win_rate,
                total_pnl=total_pnl,
                avg_pnl=avg_pnl,
                avg_winner=avg_winner,
                avg_loser=avg_loser,
                profit_factor=profit_factor,
                group_key=group_key,
            )
        )
    return results


def get_lifetime_pnl() -> float:
    """Get total lifetime P&L."""
    with state_connection() as conn:
        result = conn.execute("SELECT COALESCE(SUM(pnl), 0) FROM trades").fetchone()
        return result[0] if result else 0.0


def get_today_pnl() -> float:
    """Get today's P&L."""
    with state_connection() as conn:
        result = conn.execute("""
            SELECT COALESCE(SUM(pnl), 0) FROM trades
            WHERE DATE(exited_at) = CURRENT_DATE
        """).fetchone()
        return result[0] if result else 0.0


def get_session_pnl(session_id: int) -> float:
    """Get P&L for a specific session."""
    with state_connection() as conn:
        # Get session start and end times
        session = conn.execute(
            "SELECT started_at, ended_at FROM sessions WHERE id = ?",
            [session_id],
        ).fetchone()
        if not session:
            return 0.0

        started_at = session[0]
        ended_at = session[1]  # Could be None for active session

        if ended_at:
            result = conn.execute(
                """
                SELECT COALESCE(SUM(pnl), 0) FROM trades
                WHERE exited_at >= ? AND exited_at <= ?
                """,
                [started_at, ended_at],
            ).fetchone()
        else:
            result = conn.execute(
                """
                SELECT COALESCE(SUM(pnl), 0) FROM trades
                WHERE exited_at >= ?
                """,
                [started_at],
            ).fetchone()
        return result[0] if result else 0.0


# --- Reconciliation ---


@dataclass
class ReconciliationResult:
    """Result of position reconciliation."""

    matched: list[str]  # Positions matching between local and broker
    closed_externally: list[str]  # Local positions not at broker (closed externally)
    adopted: list[str]  # Broker positions not in local state (adopted)
    size_mismatches: dict[str, tuple[float, float]]  # symbol -> (local_size, broker_size)


def reconcile_positions(
    local_positions: dict[str, Position],
    broker_positions: dict[str, Any],  # symbol -> BrokerPosition-like object
) -> ReconciliationResult:
    """Reconcile local positions with broker positions.

    Broker is truth for WHAT positions exist.
    Local state is truth for HOW to manage them (SL, TP, trailing).
    """
    result = ReconciliationResult(
        matched=[],
        closed_externally=[],
        adopted=[],
        size_mismatches={},
    )

    local_symbols = set(local_positions.keys())
    broker_symbols = set(broker_positions.keys())

    # Positions in both
    for symbol in local_symbols & broker_symbols:
        local_pos = local_positions[symbol]
        broker_pos = broker_positions[symbol]
        local_size = local_pos.get_remaining_size()
        broker_size = broker_pos.size

        if abs(local_size - broker_size) > 0.01:  # Size mismatch
            result.size_mismatches[symbol] = (local_size, broker_size)
        else:
            result.matched.append(symbol)

    # Local positions not at broker (closed externally)
    for symbol in local_symbols - broker_symbols:
        result.closed_externally.append(symbol)
        delete_position(symbol)
        logger.warning("Position %s closed externally, removing from local state", symbol)

    # Broker positions not in local (need to adopt)
    for symbol in broker_symbols - local_symbols:
        result.adopted.append(symbol)
        logger.warning("Broker position %s not in local state, needs adoption", symbol)

    return result

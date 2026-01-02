"""Tests for state persistence module."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from tradingbot._components.state import (
    StatsGroupBy,
    _deserialize_partial_exits,
    _deserialize_triggered_levels,
    _serialize_partial_exits,
    _serialize_triggered_levels,
    clear_all_positions,
    delete_position,
    end_session,
    get_active_session,
    get_last_session_info,
    get_lifetime_pnl,
    get_stats,
    get_trades,
    load_positions,
    reconcile_positions,
    record_trade,
    save_position,
    set_circuit_breaker,
    start_session,
    was_circuit_breaker_triggered,
)
from tradingbot.types import PartialExit, Position


@pytest.fixture
def temp_db(tmp_path: Path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_state.duckdb"
    with patch("tradingbot._components.state.get_db_path", return_value=db_path):
        yield db_path


class TestSerializationHelpers:
    """Tests for JSON serialization helpers."""

    def test_serialize_partial_exits_none(self):
        assert _serialize_partial_exits(None) is None
        assert _serialize_partial_exits([]) is None

    def test_serialize_partial_exits_roundtrip(self):
        exits = [
            PartialExit(
                r_multiple=1.0,
                exit_price=150.0,
                exit_size=10.0,
                pnl=50.0,
                exit_time=datetime(2024, 1, 15, 10, 30),
            ),
            PartialExit(
                r_multiple=2.0,
                exit_price=155.0,
                exit_size=5.0,
                pnl=75.0,
                exit_time=datetime(2024, 1, 15, 11, 0),
            ),
        ]
        serialized = _serialize_partial_exits(exits)
        assert serialized is not None

        deserialized = _deserialize_partial_exits(serialized)
        assert deserialized is not None
        assert len(deserialized) == 2
        assert deserialized[0].r_multiple == 1.0
        assert deserialized[0].exit_price == 150.0
        assert deserialized[1].pnl == 75.0

    def test_serialize_triggered_levels_none(self):
        assert _serialize_triggered_levels(None) is None
        assert _serialize_triggered_levels(set()) is None

    def test_serialize_triggered_levels_roundtrip(self):
        levels = {1.0, 2.0, 3.0}
        serialized = _serialize_triggered_levels(levels)
        assert serialized is not None

        deserialized = _deserialize_triggered_levels(serialized)
        assert deserialized == levels


class TestPositionCRUD:
    """Tests for position save/load/delete."""

    def test_save_and_load_position(self, temp_db):
        position = Position(
            entry_price=145.0,
            entry_index=100,
            entry_time=datetime(2024, 1, 15, 9, 35),
            direction="LONG",
            size=100.0,
            stop_loss=143.0,
            take_profit=150.0,
            initial_stop_loss=143.0,
        )

        save_position("SPY", position)
        loaded = load_positions()

        assert "SPY" in loaded
        pos = loaded["SPY"]
        assert pos.entry_price == 145.0
        assert pos.direction == "LONG"
        assert pos.size == 100.0
        assert pos.stop_loss == 143.0
        assert pos.take_profit == 150.0

    def test_save_position_with_complex_fields(self, temp_db):
        position = Position(
            entry_price=145.0,
            entry_index=100,
            entry_time=datetime(2024, 1, 15, 9, 35),
            direction="LONG",
            size=100.0,
            stop_loss=143.0,
            take_profit=150.0,
            initial_stop_loss=143.0,
            remaining_size=50.0,
            partial_exits=[
                PartialExit(
                    r_multiple=1.0,
                    exit_price=147.0,
                    exit_size=50.0,
                    pnl=100.0,
                    exit_time=datetime(2024, 1, 15, 10, 0),
                )
            ],
            triggered_levels={1.0},
            high_water_mark=148.0,
        )

        save_position("AAPL", position)
        loaded = load_positions()

        assert "AAPL" in loaded
        pos = loaded["AAPL"]
        assert pos.remaining_size == 50.0
        assert pos.partial_exits is not None
        assert len(pos.partial_exits) == 1
        assert pos.partial_exits[0].r_multiple == 1.0
        assert pos.triggered_levels == {1.0}
        assert pos.high_water_mark == 148.0

    def test_delete_position(self, temp_db):
        position = Position(
            entry_price=145.0,
            entry_index=100,
            entry_time=datetime.now(),
            direction="LONG",
            size=100.0,
            stop_loss=143.0,
            take_profit=150.0,
        )

        save_position("SPY", position)
        assert "SPY" in load_positions()

        delete_position("SPY")
        assert "SPY" not in load_positions()

    def test_clear_all_positions(self, temp_db):
        for symbol in ["SPY", "AAPL", "MSFT"]:
            position = Position(
                entry_price=100.0,
                entry_index=0,
                entry_time=datetime.now(),
                direction="LONG",
                size=10.0,
                stop_loss=95.0,
                take_profit=110.0,
            )
            save_position(symbol, position)

        assert len(load_positions()) == 3
        count = clear_all_positions()
        assert count == 3
        assert len(load_positions()) == 0


class TestSessionManagement:
    """Tests for session tracking."""

    def test_start_and_end_session(self, temp_db):
        session_id = start_session()
        assert session_id > 0

        info = get_last_session_info()
        assert info is not None
        assert info["id"] == session_id
        assert info["ended_at"] is None
        assert not info["ended_gracefully"]

        end_session(session_id)

        info = get_last_session_info()
        assert info["ended_at"] is not None
        assert info["ended_gracefully"]

    def test_get_active_session(self, temp_db):
        assert get_active_session() is None

        session_id = start_session()
        assert get_active_session() == session_id

        end_session(session_id)
        assert get_active_session() is None

    def test_circuit_breaker(self, temp_db):
        session_id = start_session()
        assert not was_circuit_breaker_triggered(session_id)

        set_circuit_breaker(session_id)
        assert was_circuit_breaker_triggered(session_id)

        info = get_last_session_info()
        assert info["circuit_breaker_triggered"]


class TestTradeHistory:
    """Tests for trade recording and statistics."""

    def test_record_and_get_trades(self, temp_db):
        trade_id = record_trade(
            symbol="SPY",
            direction="LONG",
            entered_at=datetime(2024, 1, 15, 9, 35),
            exited_at=datetime(2024, 1, 15, 10, 0),
            entry_price=145.0,
            exit_price=147.0,
            size=100.0,
            pnl=200.0,
            pnl_pct=1.38,
            exit_reason="TAKE_PROFIT",
            strategy="orb_fvg",
        )
        assert trade_id > 0

        trades = get_trades()
        assert len(trades) == 1
        assert trades[0].symbol == "SPY"
        assert trades[0].pnl == 200.0
        assert trades[0].strategy == "orb_fvg"

    def test_get_trades_with_filters(self, temp_db):
        # Record multiple trades
        for i, (symbol, pnl) in enumerate([("SPY", 100), ("AAPL", -50), ("SPY", 75)]):
            record_trade(
                symbol=symbol,
                direction="LONG",
                entered_at=datetime(2024, 1, 15 + i, 9, 35),
                exited_at=datetime(2024, 1, 15 + i, 10, 0),
                entry_price=100.0,
                exit_price=100.0 + pnl / 10,
                size=10.0,
                pnl=float(pnl),
                pnl_pct=float(pnl),
                exit_reason="TAKE_PROFIT" if pnl > 0 else "STOP_LOSS",
            )

        # Filter by symbol
        spy_trades = get_trades(symbol="SPY")
        assert len(spy_trades) == 2
        assert all(t.symbol == "SPY" for t in spy_trades)

        # Filter with limit
        limited = get_trades(limit=2)
        assert len(limited) == 2

    def test_get_stats_lifetime(self, temp_db):
        # Record winning and losing trades
        record_trade(
            symbol="SPY",
            direction="LONG",
            entered_at=datetime.now() - timedelta(days=1),
            exited_at=datetime.now(),
            entry_price=100.0,
            exit_price=105.0,
            size=10.0,
            pnl=50.0,
            pnl_pct=5.0,
            exit_reason="TAKE_PROFIT",
        )
        record_trade(
            symbol="AAPL",
            direction="LONG",
            entered_at=datetime.now() - timedelta(hours=2),
            exited_at=datetime.now() - timedelta(hours=1),
            entry_price=150.0,
            exit_price=147.0,
            size=10.0,
            pnl=-30.0,
            pnl_pct=-2.0,
            exit_reason="STOP_LOSS",
        )

        stats = get_stats(StatsGroupBy.LIFETIME)
        assert len(stats) == 1
        s = stats[0]
        assert s.total_trades == 2
        assert s.winners == 1
        assert s.losers == 1
        assert s.total_pnl == 20.0  # 50 - 30
        assert s.win_rate == 50.0

    def test_get_stats_by_symbol(self, temp_db):
        # Record trades for different symbols
        for symbol, pnl in [("SPY", 100), ("SPY", 50), ("AAPL", -25)]:
            record_trade(
                symbol=symbol,
                direction="LONG",
                entered_at=datetime.now() - timedelta(hours=1),
                exited_at=datetime.now(),
                entry_price=100.0,
                exit_price=100.0 + pnl / 10,
                size=10.0,
                pnl=float(pnl),
                pnl_pct=float(pnl),
                exit_reason="TAKE_PROFIT",
            )

        stats = get_stats(StatsGroupBy.SYMBOL)
        stats_dict = {s.group_key: s for s in stats}

        assert "SPY" in stats_dict
        assert stats_dict["SPY"].total_pnl == 150.0
        assert stats_dict["SPY"].total_trades == 2

        assert "AAPL" in stats_dict
        assert stats_dict["AAPL"].total_pnl == -25.0

    def test_get_lifetime_pnl(self, temp_db):
        assert get_lifetime_pnl() == 0.0

        record_trade(
            symbol="SPY",
            direction="LONG",
            entered_at=datetime.now(),
            exited_at=datetime.now(),
            entry_price=100.0,
            exit_price=105.0,
            size=10.0,
            pnl=50.0,
            pnl_pct=5.0,
            exit_reason="TAKE_PROFIT",
        )

        assert get_lifetime_pnl() == 50.0


class TestReconciliation:
    """Tests for position reconciliation logic."""

    def test_reconcile_matching_positions(self):
        local = {
            "SPY": Position(
                entry_price=145.0,
                entry_index=0,
                entry_time=datetime.now(),
                direction="LONG",
                size=100.0,
                stop_loss=143.0,
                take_profit=150.0,
            )
        }

        class MockBrokerPos:
            symbol = "SPY"
            direction = "LONG"
            size = 100.0

        broker = {"SPY": MockBrokerPos()}

        result = reconcile_positions(local, broker)

        assert "SPY" in result.matched
        assert not result.closed_externally
        assert not result.adopted
        assert not result.size_mismatches

    def test_reconcile_closed_externally(self, temp_db):
        # Save a position that won't be at broker
        position = Position(
            entry_price=145.0,
            entry_index=0,
            entry_time=datetime.now(),
            direction="LONG",
            size=100.0,
            stop_loss=143.0,
            take_profit=150.0,
        )
        save_position("SPY", position)

        local = load_positions()
        broker: dict = {}  # Empty - position was closed externally

        result = reconcile_positions(local, broker)

        assert "SPY" in result.closed_externally
        assert not result.matched

        # Position should be deleted from DB
        assert "SPY" not in load_positions()

    def test_reconcile_size_mismatch(self):
        local = {
            "SPY": Position(
                entry_price=145.0,
                entry_index=0,
                entry_time=datetime.now(),
                direction="LONG",
                size=100.0,
                stop_loss=143.0,
                take_profit=150.0,
            )
        }

        class MockBrokerPos:
            symbol = "SPY"
            direction = "LONG"
            size = 50.0  # Different size

        broker = {"SPY": MockBrokerPos()}

        result = reconcile_positions(local, broker)

        assert "SPY" in result.size_mismatches
        assert result.size_mismatches["SPY"] == (100.0, 50.0)

    def test_reconcile_adopted_position(self):
        local: dict[str, Position] = {}

        class MockBrokerPos:
            symbol = "AAPL"
            direction = "LONG"
            size = 50.0

        broker = {"AAPL": MockBrokerPos()}

        result = reconcile_positions(local, broker)

        assert "AAPL" in result.adopted
        assert not result.matched

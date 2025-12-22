"""Tests for position sizing and exit strategies."""

import polars as pl
import pytest

from tradingbot import ExitStrategy, PositionSizer, SwingPoint


@pytest.fixture
def position_sizer() -> PositionSizer:
    """Create a position sizer with default settings."""
    return PositionSizer(capital=100000, risk_pct=0.01)


@pytest.fixture
def swing_points_for_stop() -> list[SwingPoint]:
    """Create swing points for stop-loss calculation."""
    return [
        SwingPoint(0, 95.0, False),  # Low
        SwingPoint(5, 110.0, True),  # High
        SwingPoint(10, 98.0, False),  # Low
        SwingPoint(15, 108.0, True),  # High
    ]


@pytest.fixture
def sample_df() -> pl.DataFrame:
    """Create sample price DataFrame for stop calculation."""
    return pl.DataFrame(
        {
            "open": [100.0] * 20,
            "high": [105.0] * 20,
            "low": [95.0] * 20,
            "close": [102.0] * 20,
        }
    )


class TestPositionSizer:
    def test_initial_capital(self, position_sizer: PositionSizer) -> None:
        assert position_sizer.capital == 100000
        assert position_sizer.initial == 100000

    def test_risk_percentage(self, position_sizer: PositionSizer) -> None:
        assert position_sizer.risk_pct == 0.01


class TestCalcSize:
    def test_position_size_calculation(self, position_sizer: PositionSizer) -> None:
        # Risk $1000 (1% of 100k), stop is $2 away
        size = position_sizer.calc_size(entry=100.0, stop=98.0)
        # Expected: 1000 / 2 = 500 units
        assert size == 500.0

    def test_position_size_short(self, position_sizer: PositionSizer) -> None:
        # Short position, stop above entry
        size = position_sizer.calc_size(entry=100.0, stop=102.0)
        assert size == 500.0

    def test_position_size_zero_risk(self, position_sizer: PositionSizer) -> None:
        # Entry equals stop (no risk per unit)
        size = position_sizer.calc_size(entry=100.0, stop=100.0)
        assert size == 0

    def test_position_size_with_different_capital(self) -> None:
        ps = PositionSizer(capital=50000, risk_pct=0.02)
        size = ps.calc_size(entry=100.0, stop=98.0)
        # Risk $1000 (2% of 50k), stop is $2 away = 500 units
        assert size == 500.0


class TestExitStrategy:
    """Tests for ExitStrategy.calc() using the default swing strategy."""

    def test_long_stop_capped_at_max_distance(
        self, swing_points_for_stop: list[SwingPoint], sample_df: pl.DataFrame
    ) -> None:
        stop, _ = ExitStrategy.calc("LONG", 105.0, 2.0, sample_df, swing_points_for_stop)
        # Swing stop would be 98.0 * 0.998 = 97.804, but that's >5% from entry
        # Max stop distance is 5%, so: 105 * 0.95 = 99.75
        assert stop == pytest.approx(99.75, rel=0.001)

    def test_short_stop_capped_at_max_distance(
        self, swing_points_for_stop: list[SwingPoint], sample_df: pl.DataFrame
    ) -> None:
        stop, _ = ExitStrategy.calc("SHORT", 100.0, 2.0, sample_df, swing_points_for_stop)
        # Swing stop would be 108.0 * 1.002 = 108.216, but that's >5% from entry
        # Max stop distance is 5%, so: 100 * 1.05 = 105.0
        assert stop == pytest.approx(105.0, rel=0.001)

    def test_long_stop_uses_swing_when_within_cap(self, sample_df: pl.DataFrame) -> None:
        # Swing at 98.0 is within 5% of entry 100.0, so swing stop is used
        swings = [SwingPoint(5, 98.0, False)]
        stop, _ = ExitStrategy.calc("LONG", 100.0, 2.0, sample_df, swings)
        # 98.0 * 0.998 = 97.804
        assert stop == pytest.approx(97.804, rel=0.001)

    def test_short_stop_uses_swing_when_within_cap(self, sample_df: pl.DataFrame) -> None:
        # Swing at 102.0 is within 5% of entry 100.0, so swing stop is used
        swings = [SwingPoint(5, 102.0, True)]
        stop, _ = ExitStrategy.calc("SHORT", 100.0, 2.0, sample_df, swings)
        # 102.0 * 1.002 = 102.204
        assert stop == pytest.approx(102.204, rel=0.001)

    def test_long_stop_fallback_no_swings(self, sample_df: pl.DataFrame) -> None:
        stop, _ = ExitStrategy.calc("LONG", 100.0, 2.0, sample_df, [])
        # Fallback: 2% below entry
        assert stop == 98.0

    def test_short_stop_fallback_no_swings(self, sample_df: pl.DataFrame) -> None:
        stop, _ = ExitStrategy.calc("SHORT", 100.0, 2.0, sample_df, [])
        # Fallback: 2% above entry
        assert stop == 102.0

    def test_long_take_profit(self, sample_df: pl.DataFrame) -> None:
        _, tp = ExitStrategy.calc("LONG", 100.0, 2.0, sample_df, [])
        # Default swing strategy with no swings uses RR-based TP
        # Stop = 98.0, risk = $2, reward = 2x = $4, TP = 100 + 4 = 104
        assert tp == 104.0

    def test_short_take_profit(self, sample_df: pl.DataFrame) -> None:
        _, tp = ExitStrategy.calc("SHORT", 100.0, 2.0, sample_df, [])
        # Stop = 102.0, risk = $2, reward = 2x = $4, TP = 100 - 4 = 96
        assert tp == 96.0

    def test_take_profit_with_different_rr(self, sample_df: pl.DataFrame) -> None:
        _, tp = ExitStrategy.calc("LONG", 100.0, 3.0, sample_df, [])
        # Stop = 98.0, risk = $2, reward = 3x = $6, TP = 100 + 6 = 106
        assert tp == 106.0


class TestSwingTakeProfit:
    """Tests for swing-based take-profit targeting."""

    def test_long_tp_targets_swing_high(self, sample_df: pl.DataFrame) -> None:
        # Swing high at 110 should be used as TP target for LONG
        swings = [SwingPoint(5, 110.0, True), SwingPoint(10, 95.0, False)]
        _, tp = ExitStrategy.calc("LONG", 100.0, 2.0, sample_df, swings, strategy="swing")
        # With entry=100, stop uses swing low at 95, risk ~$5
        # Swing high at 110 offers >1:1 RR, so it's used
        assert tp == 110.0

    def test_short_tp_targets_swing_low(self, sample_df: pl.DataFrame) -> None:
        # Swing low at 90 should be used as TP target for SHORT
        swings = [SwingPoint(5, 110.0, True), SwingPoint(10, 90.0, False)]
        _, tp = ExitStrategy.calc("SHORT", 100.0, 2.0, sample_df, swings, strategy="swing")
        # With entry=100, stop uses swing high at 110, risk ~$10
        # Swing low at 90 offers 1:1 RR, so it's used
        assert tp == 90.0

    def test_swing_tp_fallback_to_rr_when_no_valid_swing(self, sample_df: pl.DataFrame) -> None:
        # No swing points above entry, should fall back to RR-based TP
        swings = [SwingPoint(5, 95.0, False)]  # Only swing low, no swing high
        stop, tp = ExitStrategy.calc("LONG", 100.0, 2.0, sample_df, swings, strategy="swing")
        # Stop = 95 * 0.998 = 94.81, risk ~$5.19
        # Fallback to RR: 100 + (5.19 * 2) ~= 110.38
        risk = 100.0 - stop
        expected_tp = 100.0 + risk * 2.0
        assert tp == pytest.approx(expected_tp, rel=0.001)

    def test_swing_tp_fallback_when_swing_too_close(self, sample_df: pl.DataFrame) -> None:
        # Swing high at 101 is within 1R, should fall back to RR-based TP
        swings = [SwingPoint(5, 101.0, True), SwingPoint(10, 98.0, False)]
        stop, tp = ExitStrategy.calc("LONG", 100.0, 2.0, sample_df, swings, strategy="swing")
        # Stop = 98 * 0.998 = 97.804, risk ~$2.196
        # Swing at 101 only offers ~0.45:1 RR, fallback to RR-based TP
        risk = 100.0 - stop
        expected_tp = 100.0 + risk * 2.0
        assert tp == pytest.approx(expected_tp, rel=0.001)

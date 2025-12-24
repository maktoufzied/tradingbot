"""Tests for position sizing and exit strategies."""

import polars as pl
import pytest

from tradingbot import PositionSizer, SwingPoint, get_exit_registry


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
    """Tests for exit strategies using the new registry-based architecture."""

    @pytest.fixture
    def swing_exit(self):
        """Get the swing exit strategy from registry."""
        return get_exit_registry().get("swing")

    def test_long_stop_capped_at_max_distance(
        self, swing_exit, swing_points_for_stop: list[SwingPoint], sample_df: pl.DataFrame
    ) -> None:
        result = swing_exit.calc("LONG", 105.0, sample_df, swing_points_for_stop, 2.0)
        # Swing stop would be 98.0 * 0.998 = 97.804, but that's >5% from entry
        # Max stop distance is 5%, so: 105 * 0.95 = 99.75
        assert result.stop_loss == pytest.approx(99.75, rel=0.001)

    def test_short_stop_capped_at_max_distance(
        self, swing_exit, swing_points_for_stop: list[SwingPoint], sample_df: pl.DataFrame
    ) -> None:
        result = swing_exit.calc("SHORT", 100.0, sample_df, swing_points_for_stop, 2.0)
        # Swing stop would be 108.0 * 1.002 = 108.216, but that's >5% from entry
        # Max stop distance is 5%, so: 100 * 1.05 = 105.0
        assert result.stop_loss == pytest.approx(105.0, rel=0.001)

    def test_long_stop_uses_swing_when_within_cap(self, swing_exit, sample_df: pl.DataFrame) -> None:
        # Swing at 98.0 is within 5% of entry 100.0, so swing stop is used
        swings = [SwingPoint(5, 98.0, False)]
        result = swing_exit.calc("LONG", 100.0, sample_df, swings, 2.0)
        # 98.0 * 0.998 = 97.804
        assert result.stop_loss == pytest.approx(97.804, rel=0.001)

    def test_short_stop_uses_swing_when_within_cap(self, swing_exit, sample_df: pl.DataFrame) -> None:
        # Swing at 102.0 is within 5% of entry 100.0, so swing stop is used
        swings = [SwingPoint(5, 102.0, True)]
        result = swing_exit.calc("SHORT", 100.0, sample_df, swings, 2.0)
        # 102.0 * 1.002 = 102.204
        assert result.stop_loss == pytest.approx(102.204, rel=0.001)

    def test_long_stop_fallback_no_swings(self, swing_exit, sample_df: pl.DataFrame) -> None:
        result = swing_exit.calc("LONG", 100.0, sample_df, [], 2.0)
        # Fallback: 2% below entry
        assert result.stop_loss == 98.0

    def test_short_stop_fallback_no_swings(self, swing_exit, sample_df: pl.DataFrame) -> None:
        result = swing_exit.calc("SHORT", 100.0, sample_df, [], 2.0)
        # Fallback: 2% above entry
        assert result.stop_loss == 102.0

    def test_long_take_profit(self, swing_exit, sample_df: pl.DataFrame) -> None:
        result = swing_exit.calc("LONG", 100.0, sample_df, [], 2.0)
        # Default swing strategy with no swings uses RR-based TP
        # Stop = 98.0, risk = $2, reward would be 2x = $4
        # But TP is capped at 1.5% = $1.50, so TP = 101.5
        assert result.take_profit == 101.5

    def test_short_take_profit(self, swing_exit, sample_df: pl.DataFrame) -> None:
        result = swing_exit.calc("SHORT", 100.0, sample_df, [], 2.0)
        # Stop = 102.0, risk = $2, reward would be 2x = $4
        # But TP is capped at 1.5% = $1.50, so TP = 98.5
        assert result.take_profit == 98.5

    def test_take_profit_with_different_rr(self, swing_exit, sample_df: pl.DataFrame) -> None:
        result = swing_exit.calc("LONG", 100.0, sample_df, [], 3.0)
        # Stop = 98.0, risk = $2, reward would be 3x = $6
        # But TP is capped at 1.5% = $1.50, so TP = 101.5
        assert result.take_profit == 101.5


class TestSwingTakeProfit:
    """Tests for swing-based take-profit targeting.

    Note: TP is now capped at 1.5% for realistic day trading targets.
    """

    @pytest.fixture
    def swing_exit(self):
        """Get the swing exit strategy from registry."""
        return get_exit_registry().get("swing")

    def test_long_tp_targets_swing_high_within_cap(self, swing_exit, sample_df: pl.DataFrame) -> None:
        # Swing high at 101.2 is within 1.5% cap and offers >= 1R
        # Stop: 99.5 * 0.998 = 99.301, risk = 0.699
        # Swing at 101.2: distance = 1.2 >= 0.699 (1R) and <= 1.5 (cap)
        swings = [SwingPoint(5, 101.2, True), SwingPoint(10, 99.5, False)]
        result = swing_exit.calc("LONG", 100.0, sample_df, swings, 2.0)
        assert result.take_profit == 101.2

    def test_short_tp_targets_swing_low_within_cap(self, swing_exit, sample_df: pl.DataFrame) -> None:
        # Swing low at 98.8 is within 1.5% cap and offers >= 1R
        # Stop: 100.5 * 1.002 = 100.701, risk = 0.701
        # Swing at 98.8: distance = 1.2 >= 0.701 (1R) and <= 1.5 (cap)
        swings = [SwingPoint(5, 100.5, True), SwingPoint(10, 98.8, False)]
        result = swing_exit.calc("SHORT", 100.0, sample_df, swings, 2.0)
        assert result.take_profit == 98.8

    def test_swing_tp_capped_when_swing_too_far(self, swing_exit, sample_df: pl.DataFrame) -> None:
        # Swing high at 110 is beyond 1.5% cap, should be capped
        swings = [SwingPoint(5, 110.0, True), SwingPoint(10, 95.0, False)]
        result = swing_exit.calc("LONG", 100.0, sample_df, swings, 2.0)
        # Swing at 110 is 10% away, exceeds 1.5% cap
        # TP capped at 100 * 1.015 = 101.5
        assert result.take_profit == 101.5

    def test_swing_tp_fallback_to_capped_rr(self, swing_exit, sample_df: pl.DataFrame) -> None:
        # No valid swing points, falls back to capped RR-based TP
        swings = [SwingPoint(5, 95.0, False)]  # Only swing low, no swing high
        result = swing_exit.calc("LONG", 100.0, sample_df, swings, 2.0)
        # Fallback to RR-based TP, but capped at 1.5%
        assert result.take_profit == 101.5

    def test_swing_tp_uses_capped_rr_when_swing_too_close(self, swing_exit, sample_df: pl.DataFrame) -> None:
        # Swing high at 100.5 is within 1R but very close, use capped RR
        swings = [SwingPoint(5, 100.5, True), SwingPoint(10, 98.0, False)]
        result = swing_exit.calc("LONG", 100.0, sample_df, swings, 2.0)
        # Stop at 98 * 0.998 = 97.804, risk ~$2.196
        # Swing at 100.5 only offers ~0.23:1 RR (too close)
        # Fallback to RR-based TP, capped at 1.5%
        assert result.take_profit == 101.5

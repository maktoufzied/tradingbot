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

    def test_long_stop_at_swing_low(
        self, swing_exit, swing_points_for_stop: list[SwingPoint], sample_df: pl.DataFrame
    ) -> None:
        result = swing_exit.calc("LONG", 105.0, sample_df, swing_points_for_stop, 2.0)
        # Stop at last swing low (98.0) with buffer: 98.0 * 0.998 = 97.804
        assert result.stop_loss == pytest.approx(97.804, rel=0.001)

    def test_short_stop_at_swing_high(
        self, swing_exit, swing_points_for_stop: list[SwingPoint], sample_df: pl.DataFrame
    ) -> None:
        result = swing_exit.calc("SHORT", 100.0, sample_df, swing_points_for_stop, 2.0)
        # Stop at last swing high (108.0) with buffer: 108.0 * 1.002 = 108.216
        assert result.stop_loss == pytest.approx(108.216, rel=0.001)

    def test_long_stop_uses_swing(self, swing_exit, sample_df: pl.DataFrame) -> None:
        swings = [SwingPoint(5, 98.0, False)]
        result = swing_exit.calc("LONG", 100.0, sample_df, swings, 2.0)
        # 98.0 * 0.998 = 97.804
        assert result.stop_loss == pytest.approx(97.804, rel=0.001)

    def test_short_stop_uses_swing(self, swing_exit, sample_df: pl.DataFrame) -> None:
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

    def test_long_take_profit_rr_based(self, swing_exit, sample_df: pl.DataFrame) -> None:
        result = swing_exit.calc("LONG", 100.0, sample_df, [], 2.0)
        # No swings, uses RR-based TP
        # Stop = 98.0, risk = $2, reward = 2x = $4, TP = 104.0
        assert result.take_profit == 104.0

    def test_short_take_profit_rr_based(self, swing_exit, sample_df: pl.DataFrame) -> None:
        result = swing_exit.calc("SHORT", 100.0, sample_df, [], 2.0)
        # Stop = 102.0, risk = $2, reward = 2x = $4, TP = 96.0
        assert result.take_profit == 96.0

    def test_take_profit_with_different_rr(self, swing_exit, sample_df: pl.DataFrame) -> None:
        result = swing_exit.calc("LONG", 100.0, sample_df, [], 3.0)
        # Stop = 98.0, risk = $2, reward = 3x = $6, TP = 106.0
        assert result.take_profit == 106.0


class TestSwingTakeProfit:
    """Tests for swing-based take-profit targeting."""

    @pytest.fixture
    def swing_exit(self):
        """Get the swing exit strategy from registry."""
        return get_exit_registry().get("swing")

    def test_long_tp_targets_swing_high(self, swing_exit, sample_df: pl.DataFrame) -> None:
        # Swing high at 105.0 offers >= 1R
        # Stop: 98.0 * 0.998 = 97.804, risk = 2.196
        # Swing at 105.0: distance = 5.0 >= 2.196 (1R)
        swings = [SwingPoint(5, 105.0, True), SwingPoint(10, 98.0, False)]
        result = swing_exit.calc("LONG", 100.0, sample_df, swings, 2.0)
        assert result.take_profit == 105.0

    def test_short_tp_targets_swing_low(self, swing_exit, sample_df: pl.DataFrame) -> None:
        # Swing low at 95.0 offers >= 1R
        # Stop: 102.0 * 1.002 = 102.204, risk = 2.204
        # Swing at 95.0: distance = 5.0 >= 2.204 (1R)
        swings = [SwingPoint(5, 102.0, True), SwingPoint(10, 95.0, False)]
        result = swing_exit.calc("SHORT", 100.0, sample_df, swings, 2.0)
        assert result.take_profit == 95.0

    def test_swing_tp_uses_nearest_swing(self, swing_exit, sample_df: pl.DataFrame) -> None:
        # Multiple swing highs above entry, should use nearest
        # Swing low at 98.0 gives stop at 97.804, risk ~2.196
        # Swing high at 105.0 offers 5.0 reward (>= 1R), so it's used
        swings = [SwingPoint(5, 110.0, True), SwingPoint(8, 105.0, True), SwingPoint(10, 98.0, False)]
        result = swing_exit.calc("LONG", 100.0, sample_df, swings, 2.0)
        # Nearest swing high above entry is 105.0
        assert result.take_profit == 105.0

    def test_swing_tp_fallback_to_rr(self, swing_exit, sample_df: pl.DataFrame) -> None:
        # No swing highs above entry, falls back to RR-based TP
        swings = [SwingPoint(5, 95.0, False)]  # Only swing low
        result = swing_exit.calc("LONG", 100.0, sample_df, swings, 2.0)
        # Stop: 95 * 0.998 = 94.81, risk = 5.19, RR 2x = 10.38
        # TP = 100 + 10.38 = 110.38
        assert result.take_profit == pytest.approx(110.38, rel=0.01)

    def test_swing_tp_fallback_when_swing_too_close(self, swing_exit, sample_df: pl.DataFrame) -> None:
        # Swing high at 100.5 is within 1R, fallback to RR-based
        swings = [SwingPoint(5, 100.5, True), SwingPoint(10, 98.0, False)]
        result = swing_exit.calc("LONG", 100.0, sample_df, swings, 2.0)
        # Stop at 98 * 0.998 = 97.804, risk ~$2.196
        # Swing at 100.5 only offers $0.5 (~0.23R) - less than 1R
        # Fallback to RR-based TP: 100 + 2.196 * 2 = 104.392
        assert result.take_profit == pytest.approx(104.392, rel=0.01)

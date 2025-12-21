"""Tests for risk management."""

import polars as pl
import pytest

from tradingbot import RiskManager, SwingPoint


@pytest.fixture
def risk_manager() -> RiskManager:
    """Create a risk manager with default settings."""
    return RiskManager(capital=100000, risk_pct=0.01, rr_ratio=2.0)


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


class TestRiskManager:
    def test_initial_capital(self, risk_manager):
        assert risk_manager.capital == 100000
        assert risk_manager.initial == 100000

    def test_risk_percentage(self, risk_manager):
        assert risk_manager.risk_pct == 0.01

    def test_reward_risk_ratio(self, risk_manager):
        assert risk_manager.rr_ratio == 2.0


class TestCalcSize:
    def test_position_size_calculation(self, risk_manager):
        # Risk $1000 (1% of 100k), stop is $2 away
        size = risk_manager.calc_size(entry=100.0, stop=98.0)
        # Expected: 1000 / 2 = 500 units
        assert size == 500.0

    def test_position_size_short(self, risk_manager):
        # Short position, stop above entry
        size = risk_manager.calc_size(entry=100.0, stop=102.0)
        assert size == 500.0

    def test_position_size_zero_risk(self, risk_manager):
        # Entry equals stop (no risk per unit)
        size = risk_manager.calc_size(entry=100.0, stop=100.0)
        assert size == 0

    def test_position_size_with_different_capital(self):
        rm = RiskManager(capital=50000, risk_pct=0.02)
        size = rm.calc_size(entry=100.0, stop=98.0)
        # Risk $1000 (2% of 50k), stop is $2 away = 500 units
        assert size == 500.0


class TestCalcStop:
    def test_long_stop_capped_at_max_distance(self, risk_manager, swing_points_for_stop, sample_df):
        stop = risk_manager.calc_stop("LONG", 105.0, sample_df, 15, swing_points_for_stop)
        # Swing stop would be 98.0 * 0.998 = 97.804, but that's >5% from entry
        # Max stop distance is 5%, so: 105 * 0.95 = 99.75
        assert stop == pytest.approx(99.75, rel=0.001)

    def test_short_stop_capped_at_max_distance(self, risk_manager, swing_points_for_stop, sample_df):
        stop = risk_manager.calc_stop("SHORT", 100.0, sample_df, 15, swing_points_for_stop)
        # Swing stop would be 108.0 * 1.002 = 108.216, but that's >5% from entry
        # Max stop distance is 5%, so: 100 * 1.05 = 105.0
        assert stop == pytest.approx(105.0, rel=0.001)

    def test_long_stop_uses_swing_when_within_cap(self, risk_manager, sample_df):
        # Swing at 98.0 is within 5% of entry 100.0, so swing stop is used
        swings = [SwingPoint(5, 98.0, False)]
        stop = risk_manager.calc_stop("LONG", 100.0, sample_df, 15, swings)
        # 98.0 * 0.998 = 97.804
        assert stop == pytest.approx(97.804, rel=0.001)

    def test_short_stop_uses_swing_when_within_cap(self, risk_manager, sample_df):
        # Swing at 102.0 is within 5% of entry 100.0, so swing stop is used
        swings = [SwingPoint(5, 102.0, True)]
        stop = risk_manager.calc_stop("SHORT", 100.0, sample_df, 15, swings)
        # 102.0 * 1.002 = 102.204
        assert stop == pytest.approx(102.204, rel=0.001)

    def test_long_stop_fallback_no_swings(self, risk_manager, sample_df):
        stop = risk_manager.calc_stop("LONG", 100.0, sample_df, 15, [])
        # Fallback: 2% below entry
        assert stop == 98.0

    def test_short_stop_fallback_no_swings(self, risk_manager, sample_df):
        stop = risk_manager.calc_stop("SHORT", 100.0, sample_df, 15, [])
        # Fallback: 2% above entry
        assert stop == 102.0


class TestCalcTakeProfit:
    def test_long_take_profit(self, risk_manager):
        tp = risk_manager.calc_tp("LONG", entry=100.0, stop=98.0)
        # Risk is $2, reward is 2x = $4, TP = 100 + 4 = 104
        assert tp == 104.0

    def test_short_take_profit(self, risk_manager):
        tp = risk_manager.calc_tp("SHORT", entry=100.0, stop=102.0)
        # Risk is $2, reward is 2x = $4, TP = 100 - 4 = 96
        assert tp == 96.0

    def test_take_profit_with_different_rr(self):
        rm = RiskManager(capital=100000, rr_ratio=3.0)
        tp = rm.calc_tp("LONG", entry=100.0, stop=98.0)
        # Risk is $2, reward is 3x = $6, TP = 100 + 6 = 106
        assert tp == 106.0

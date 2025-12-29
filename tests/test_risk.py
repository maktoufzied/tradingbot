"""Tests for position sizing and exit strategies."""

from datetime import datetime, timedelta

import polars as pl
import pytest

from tradingbot import PositionSizer, SwingPoint, get_exit_registry
from tradingbot._components.risk import compute_atr, compute_baseline_atr


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


class TestComputeATR:
    """Tests for ATR computation."""

    def test_compute_atr_basic(self) -> None:
        """Test basic ATR calculation with known values."""
        # Create data where True Range = high - low = 5.0 consistently
        df = pl.DataFrame(
            {
                "datetime": [datetime(2024, 1, i + 1) for i in range(20)],
                "open": [100.0] * 20,
                "high": [105.0] * 20,
                "low": [100.0] * 20,
                "close": [102.0] * 20,
            }
        )
        atr = compute_atr(df, period=14)
        assert atr is not None
        assert atr == pytest.approx(5.0, rel=0.01)

    def test_compute_atr_insufficient_data(self) -> None:
        """Test ATR returns None with insufficient data."""
        df = pl.DataFrame(
            {
                "datetime": [datetime(2024, 1, i + 1) for i in range(5)],
                "open": [100.0] * 5,
                "high": [105.0] * 5,
                "low": [100.0] * 5,
                "close": [102.0] * 5,
            }
        )
        atr = compute_atr(df, period=14)
        assert atr is None

    def test_compute_baseline_atr(self) -> None:
        """Test baseline ATR with longer period."""
        df = pl.DataFrame(
            {
                "datetime": [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(60)],
                "open": [100.0] * 60,
                "high": [108.0] * 60,
                "low": [100.0] * 60,
                "close": [104.0] * 60,
            }
        )
        baseline = compute_baseline_atr(df, period=50)
        assert baseline is not None
        assert baseline == pytest.approx(8.0, rel=0.01)


class TestATRBasedPositionSizing:
    """Tests for ATR-based volatility-adjusted position sizing."""

    @pytest.fixture
    def stable_volatility_df(self) -> pl.DataFrame:
        """Create DataFrame with stable volatility (ATR ~= baseline ATR)."""
        return pl.DataFrame(
            {
                "datetime": [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(60)],
                "open": [100.0] * 60,
                "high": [105.0] * 60,
                "low": [100.0] * 60,
                "close": [102.0] * 60,
            }
        )

    @pytest.fixture
    def high_volatility_df(self) -> pl.DataFrame:
        """Create DataFrame where recent volatility is higher than baseline."""
        # First 45 bars: low volatility (TR = 3)
        # Last 15 bars: high volatility (TR = 10)
        high_vals = [103.0] * 45 + [110.0] * 15
        low_vals = [100.0] * 45 + [100.0] * 15
        return pl.DataFrame(
            {
                "datetime": [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(60)],
                "open": [100.0] * 60,
                "high": high_vals,
                "low": low_vals,
                "close": [102.0] * 60,
            }
        )

    @pytest.fixture
    def low_volatility_df(self) -> pl.DataFrame:
        """Create DataFrame where recent volatility is lower than baseline."""
        # First 45 bars: high volatility (TR = 10)
        # Last 15 bars: low volatility (TR = 2)
        high_vals = [110.0] * 45 + [102.0] * 15
        low_vals = [100.0] * 45 + [100.0] * 15
        return pl.DataFrame(
            {
                "datetime": [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(60)],
                "open": [100.0] * 60,
                "high": high_vals,
                "low": low_vals,
                "close": [102.0] * 60,
            }
        )

    def test_atr_sizing_disabled_by_default(self, stable_volatility_df: pl.DataFrame) -> None:
        """Test that ATR sizing is disabled by default."""
        ps = PositionSizer(capital=100000, risk_pct=0.01)
        assert ps.use_atr_sizing is False

    def test_atr_sizing_enabled(self, stable_volatility_df: pl.DataFrame) -> None:
        """Test that ATR sizing can be enabled."""
        ps = PositionSizer(capital=100000, risk_pct=0.01, use_atr_sizing=True)
        assert ps.use_atr_sizing is True

    def test_stable_volatility_no_adjustment(self, stable_volatility_df: pl.DataFrame) -> None:
        """Test position size unchanged when current ATR ≈ baseline ATR."""
        ps = PositionSizer(capital=100000, risk_pct=0.01, use_atr_sizing=True)
        # Without ATR: 1000 / 2 = 500 shares
        size = ps.calc_size(entry=100.0, stop=98.0, df=stable_volatility_df)
        # Scale should be ~1.0, so size ~500
        assert size == pytest.approx(500, abs=50)

    def test_high_volatility_reduces_position(self, high_volatility_df: pl.DataFrame) -> None:
        """Test position size reduced when current ATR > baseline ATR."""
        ps_no_atr = PositionSizer(capital=100000, risk_pct=0.01, use_atr_sizing=False)
        ps_with_atr = PositionSizer(capital=100000, risk_pct=0.01, use_atr_sizing=True)

        base_size = ps_no_atr.calc_size(entry=100.0, stop=98.0)
        atr_size = ps_with_atr.calc_size(entry=100.0, stop=98.0, df=high_volatility_df)

        # High volatility should reduce position size
        assert atr_size < base_size

    def test_low_volatility_increases_position(self, low_volatility_df: pl.DataFrame) -> None:
        """Test position size increased when current ATR < baseline ATR."""
        ps_no_atr = PositionSizer(capital=100000, risk_pct=0.01, use_atr_sizing=False)
        ps_with_atr = PositionSizer(capital=100000, risk_pct=0.01, use_atr_sizing=True)

        base_size = ps_no_atr.calc_size(entry=100.0, stop=98.0)
        atr_size = ps_with_atr.calc_size(entry=100.0, stop=98.0, df=low_volatility_df)

        # Low volatility should increase position size (up to cap)
        assert atr_size >= base_size

    def test_no_df_provided_no_adjustment(self) -> None:
        """Test no adjustment when DataFrame not provided."""
        ps = PositionSizer(capital=100000, risk_pct=0.01, use_atr_sizing=True)
        size = ps.calc_size(entry=100.0, stop=98.0, df=None)
        # Should be base size without adjustment
        assert size == 500.0

    def test_scale_factor_capped_at_max(self, low_volatility_df: pl.DataFrame) -> None:
        """Test scale factor is capped at 1.5x maximum."""
        ps = PositionSizer(capital=100000, risk_pct=0.01, use_atr_sizing=True)
        atr_size = ps.calc_size(entry=100.0, stop=98.0, df=low_volatility_df)
        # Maximum increase is 1.5x base (500 * 1.5 = 750)
        assert atr_size <= 750

    def test_scale_factor_floored_at_min(self) -> None:
        """Test scale factor is floored at 0.25x minimum."""
        # Create extremely high volatility scenario
        high_vals = [100.0] * 45 + [200.0] * 15  # TR = 100 recent vs 0 baseline
        low_vals = [100.0] * 60
        extreme_df = pl.DataFrame(
            {
                "datetime": [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(60)],
                "open": [100.0] * 60,
                "high": high_vals,
                "low": low_vals,
                "close": [100.0] * 60,
            }
        )
        ps = PositionSizer(capital=100000, risk_pct=0.01, use_atr_sizing=True)
        atr_size = ps.calc_size(entry=100.0, stop=98.0, df=extreme_df)
        # Minimum is 0.25x base (500 * 0.25 = 125)
        assert atr_size >= 125


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

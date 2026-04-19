"""Tests for Power Hour Reversal entry strategy."""

from datetime import datetime, timedelta

import polars as pl
import pytest

from tradingbot._components.strategies.entry.power_hour_reversal import (
    PowerHourReversalRelaxedStrategy,
    PowerHourReversalStrategy,
)
from tradingbot.types import Signal


@pytest.fixture
def strategy() -> PowerHourReversalStrategy:
    """Create Power Hour Reversal strategy with default settings."""
    return PowerHourReversalStrategy()


@pytest.fixture
def relaxed_strategy() -> PowerHourReversalRelaxedStrategy:
    """Create relaxed variant of strategy."""
    return PowerHourReversalRelaxedStrategy()


def create_power_hour_data(
    start_price: float = 100.0,
    trend: str = "down",
    num_bars: int = 50,
    high_volume: bool = True,
) -> pl.DataFrame:
    """Create sample data during power hour (20:00-20:45 UTC = 3:00-3:45 PM ET).

    Args:
        start_price: Starting price
        trend: "down" for oversold setup, "up" for overbought setup
        num_bars: Number of bars to generate
        high_volume: Whether to include volume spike
    """
    base_time = datetime(2024, 1, 15, 20, 0)  # UTC = 3:00 PM ET
    bars = []

    price = start_price
    for i in range(num_bars):
        # Downtrend creates oversold, uptrend creates overbought
        change = -0.1 - (i * 0.02) if trend == "down" else 0.1 + (i * 0.02)
        new_price = price + change
        high = max(price, new_price) + 0.1
        low = min(price, new_price) - 0.1

        # Create bullish candle for reversal at the end if downtrend
        if trend == "down" and i == num_bars - 1:
            # Bullish reversal candle
            open_price = new_price - 0.2
            close_price = new_price + 0.3
            high = close_price + 0.05
            low = open_price - 0.05
        elif trend == "up" and i == num_bars - 1:
            # Bearish reversal candle
            open_price = new_price + 0.2
            close_price = new_price - 0.3
            high = open_price + 0.05
            low = close_price - 0.05
        else:
            open_price = price
            close_price = new_price

        volume = 50000 if high_volume and i >= num_bars - 5 else 10000

        bars.append(
            {
                "datetime": base_time + timedelta(minutes=i),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close_price,
                "volume": volume,
            }
        )

        price = new_price

    return pl.DataFrame(bars)


@pytest.fixture
def power_hour_oversold_data() -> pl.DataFrame:
    """Create data with oversold condition during power hour."""
    return create_power_hour_data(trend="down", num_bars=50)


@pytest.fixture
def power_hour_overbought_data() -> pl.DataFrame:
    """Create data with overbought condition during power hour."""
    return create_power_hour_data(trend="up", num_bars=50)


@pytest.fixture
def outside_power_hour_data() -> pl.DataFrame:
    """Create data outside power hour (10:00 AM ET = 15:00 UTC)."""
    base_time = datetime(2024, 1, 15, 15, 0)  # UTC = 10:00 AM ET (not power hour)
    bars = []

    price = 100.0
    for i in range(50):
        change = -0.1 - (i * 0.02)
        new_price = price + change

        bars.append(
            {
                "datetime": base_time + timedelta(minutes=i),
                "open": price,
                "high": max(price, new_price) + 0.1,
                "low": min(price, new_price) - 0.1,
                "close": new_price,
                "volume": 50000,
            }
        )

        price = new_price

    return pl.DataFrame(bars)


class TestPowerHourReversalStrategy:
    def test_strategy_name(self, strategy):
        assert strategy.name == "power_hour_reversal"

    def test_relaxed_strategy_name(self, relaxed_strategy):
        assert relaxed_strategy.name == "power_hour_reversal_relaxed"

    def test_compute_adds_required_columns(self, strategy, power_hour_oversold_data):
        result = strategy.compute(power_hour_oversold_data)

        assert "vwap" in result.columns
        assert "vwap_distance" in result.columns
        assert "rsi" in result.columns
        assert "volume_ratio" in result.columns

    def test_compute_is_idempotent(self, strategy, power_hour_oversold_data):
        result1 = strategy.compute(power_hour_oversold_data)
        result2 = strategy.compute(result1)

        assert result1.shape == result2.shape
        assert result1.columns == result2.columns

    def test_hold_when_position_open(self, strategy, power_hour_oversold_data):
        result = strategy.signal(power_hour_oversold_data, idx=49, has_position=True)

        assert result.signal == Signal.HOLD
        assert "Position open" in result.reason

    def test_hold_with_insufficient_data(self, strategy, power_hour_oversold_data):
        result = strategy.signal(power_hour_oversold_data, idx=5, has_position=False)

        assert result.signal == Signal.HOLD
        assert "Insufficient data" in result.reason

    def test_hold_outside_power_hour(self, strategy, outside_power_hour_data):
        result = strategy.signal(outside_power_hour_data, idx=49, has_position=False)

        assert result.signal == Signal.HOLD
        assert "Outside power hour" in result.reason


class TestPowerHourTimeDetection:
    """Tests use UTC timestamps (Alpaca data is in UTC).

    3:00 PM ET = 20:00 UTC (during EST, UTC-5)
    """

    def test_is_in_power_hour(self, strategy):
        # During power hour (20:00-20:45 UTC = 3:00-3:45 PM ET)
        dt_1500 = datetime(2024, 1, 15, 20, 0)  # 3:00 PM ET
        dt_1530 = datetime(2024, 1, 15, 20, 30)  # 3:30 PM ET
        dt_1544 = datetime(2024, 1, 15, 20, 44)  # 3:44 PM ET

        assert strategy._is_in_power_hour(dt_1500)
        assert strategy._is_in_power_hour(dt_1530)
        assert strategy._is_in_power_hour(dt_1544)

        # After power hour entry window
        dt_1545 = datetime(2024, 1, 15, 20, 45)  # 3:45 PM ET
        dt_1555 = datetime(2024, 1, 15, 20, 55)  # 3:55 PM ET

        assert not strategy._is_in_power_hour(dt_1545)
        assert not strategy._is_in_power_hour(dt_1555)

    def test_not_power_hour_before_3pm(self, strategy):
        # Before power hour
        dt_1400 = datetime(2024, 1, 15, 19, 0)  # 2:00 PM ET
        dt_1459 = datetime(2024, 1, 15, 19, 59)  # 2:59 PM ET

        assert not strategy._is_in_power_hour(dt_1400)
        assert not strategy._is_in_power_hour(dt_1459)

    def test_not_power_hour_morning(self, strategy):
        # Morning session
        dt_0930 = datetime(2024, 1, 15, 14, 30)  # 9:30 AM ET
        dt_1000 = datetime(2024, 1, 15, 15, 0)  # 10:00 AM ET

        assert not strategy._is_in_power_hour(dt_0930)
        assert not strategy._is_in_power_hour(dt_1000)


class TestIndicatorComputation:
    def test_vwap_calculation(self, strategy, power_hour_oversold_data):
        result = strategy.compute(power_hour_oversold_data)

        # VWAP should be populated for all bars after first
        vwap_values = result["vwap"].to_list()
        assert vwap_values[0] is not None  # First bar VWAP = typical price
        assert all(v is not None for v in vwap_values)

    def test_rsi_calculation(self, strategy, power_hour_oversold_data):
        result = strategy.compute(power_hour_oversold_data)

        rsi_values = result["rsi"].to_list()
        # RSI needs lookback period, first values will be None
        valid_rsi = [v for v in rsi_values if v is not None]
        assert len(valid_rsi) > 0
        # RSI should be between 0-100
        assert all(0 <= v <= 100 for v in valid_rsi)

    def test_volume_ratio_calculation(self, strategy, power_hour_oversold_data):
        result = strategy.compute(power_hour_oversold_data)

        vol_ratios = result["volume_ratio"].to_list()
        valid_ratios = [v for v in vol_ratios if v is not None]
        assert len(valid_ratios) > 0
        # Volume ratio should be positive
        assert all(v > 0 for v in valid_ratios)


class TestCandlePatternDetection:
    def test_bullish_candle_detection(self, strategy):
        # Bullish candle: close > open, close in upper 40% of range (position >= 0.6)
        assert strategy._is_bullish_candle(100.0, 101.0, 101.2, 99.8)  # Close near high
        # (100.2 - 99.0) / (101.0 - 99.0) = 0.6 -> at threshold, passes
        assert strategy._is_bullish_candle(100.0, 100.2, 101.0, 99.0)  # Close at 60% threshold
        # Close clearly in lower half
        assert not strategy._is_bullish_candle(100.0, 100.1, 101.0, 99.0)  # Close at 55%, fails
        assert not strategy._is_bullish_candle(101.0, 100.0, 101.2, 99.8)  # Bearish candle

    def test_bearish_candle_detection(self, strategy):
        # Bearish candle: close < open, close in lower 40% of range
        assert strategy._is_bearish_candle(101.0, 100.0, 101.2, 99.8)  # Close near low
        assert not strategy._is_bearish_candle(101.0, 100.8, 101.2, 99.8)  # Close in middle
        assert not strategy._is_bearish_candle(100.0, 101.0, 101.2, 99.8)  # Bullish candle


class TestDivergenceDetection:
    def test_find_rsi_swings(self, strategy):
        # Create RSI values with clear swing points
        rsi_values = [
            50.0,
            45.0,
            40.0,
            35.0,
            30.0,  # Downtrend
            32.0,
            35.0,
            40.0,
            45.0,
            50.0,  # Uptrend
            48.0,
            45.0,
            40.0,
            35.0,
            33.0,  # Another down
        ]

        swings = strategy._find_rsi_swings(rsi_values, lookback=2)

        # Should find swing lows and highs
        assert len(swings) > 0
        # Each swing is (index, value, is_high)
        for idx, val, is_high in swings:
            assert isinstance(idx, int)
            assert isinstance(val, float)
            assert isinstance(is_high, bool)


class TestSignalGeneration:
    def test_details_include_indicators(self, strategy, power_hour_oversold_data):
        result = strategy.signal(power_hour_oversold_data, idx=49, has_position=False)

        assert "price" in result.details
        assert "vwap" in result.details
        assert "rsi" in result.details
        assert "vol_ratio" in result.details

    def test_hold_on_low_volume(self, strategy):
        """Test that strategy holds when volume is below threshold."""
        # Create data with low volume
        data = create_power_hour_data(trend="down", num_bars=50, high_volume=False)
        result = strategy.signal(data, idx=49, has_position=False)

        # Should hold due to insufficient volume or other conditions
        assert result.signal == Signal.HOLD


class TestRelaxedStrategy:
    def test_relaxed_has_different_params(self, strategy, relaxed_strategy):
        # Relaxed should have lower thresholds
        assert relaxed_strategy._vwap_distance_pct < strategy._vwap_distance_pct
        assert relaxed_strategy._rsi_oversold > strategy._rsi_oversold
        assert relaxed_strategy._rsi_overbought < strategy._rsi_overbought
        assert relaxed_strategy._volume_multiplier < strategy._volume_multiplier

"""Tests for technical indicators."""

from datetime import datetime, timedelta

import polars as pl
import pytest

from tradingbot._components.indicators.plugins.macd import MACDIndicator
from tradingbot._components.indicators.plugins.rsi import RSIIndicator
from tradingbot.types import Signal


@pytest.fixture
def uptrend_data() -> pl.DataFrame:
    """Create upward trending price data."""
    n = 50
    prices = [100.0 + i * 0.5 for i in range(n)]

    base_date = datetime(2024, 1, 1)
    return pl.DataFrame(
        {
            "datetime": [base_date + timedelta(days=i) for i in range(n)],
            "open": prices,
            "high": [p + 1 for p in prices],
            "low": [p - 1 for p in prices],
            "close": prices,
            "volume": [1000] * n,
        }
    )


@pytest.fixture
def downtrend_data() -> pl.DataFrame:
    """Create downward trending price data."""
    n = 50
    prices = [150.0 - i * 0.5 for i in range(n)]

    base_date = datetime(2024, 1, 1)
    return pl.DataFrame(
        {
            "datetime": [base_date + timedelta(days=i) for i in range(n)],
            "open": prices,
            "high": [p + 1 for p in prices],
            "low": [p - 1 for p in prices],
            "close": prices,
            "volume": [1000] * n,
        }
    )


@pytest.fixture
def oscillating_data() -> pl.DataFrame:
    """Create oscillating price data for RSI testing."""
    n = 50
    prices = []
    for i in range(n):
        if i < 15:
            prices.append(100 - i * 0.5)
        elif i < 30:
            prices.append(92.5 + (i - 15) * 1.0)
        else:
            prices.append(107.5 - (i - 30) * 0.3)

    base_date = datetime(2024, 1, 1)
    return pl.DataFrame(
        {
            "datetime": [base_date + timedelta(days=i) for i in range(n)],
            "open": prices,
            "high": [p + 0.5 for p in prices],
            "low": [p - 0.5 for p in prices],
            "close": prices,
            "volume": [1000] * n,
        }
    )


class TestRSIIndicator:
    def test_default_parameters(self):
        rsi = RSIIndicator()
        assert rsi._period == 14
        assert rsi._overbought == 70.0
        assert rsi._oversold == 30.0
        assert rsi.name == "rsi"

    def test_custom_parameters(self):
        rsi = RSIIndicator(period=7, overbought=80, oversold=20)
        assert rsi._period == 7
        assert rsi._overbought == 80
        assert rsi._oversold == 20

    def test_compute_adds_rsi_column(self, uptrend_data):
        rsi = RSIIndicator()
        result = rsi.compute(uptrend_data)
        assert "rsi" in result.columns
        assert len(result) == len(uptrend_data)

    def test_rsi_range_0_to_100(self, uptrend_data):
        rsi = RSIIndicator()
        result = rsi.compute(uptrend_data)
        rsi_values = result["rsi"].drop_nulls()
        assert (rsi_values >= 0).all()
        assert (rsi_values <= 100).all()

    def test_uptrend_high_rsi(self, uptrend_data):
        """RSI should be high (near 100) in strong uptrend."""
        rsi = RSIIndicator()
        result = rsi.compute(uptrend_data)
        last_rsi = result["rsi"][-1]
        assert last_rsi > 70

    def test_downtrend_low_rsi(self, downtrend_data):
        """RSI should be low (near 0) in strong downtrend."""
        rsi = RSIIndicator()
        result = rsi.compute(downtrend_data)
        last_rsi = result["rsi"][-1]
        assert last_rsi < 30

    def test_filter_blocks_buy_when_overbought(self, uptrend_data):
        rsi = RSIIndicator()
        df = rsi.compute(uptrend_data)
        idx = len(df) - 1
        result = rsi.filter_signal(Signal.BUY, df, idx)
        assert result is False

    def test_filter_allows_buy_when_not_overbought(self, downtrend_data):
        rsi = RSIIndicator()
        df = rsi.compute(downtrend_data)
        idx = len(df) - 1
        result = rsi.filter_signal(Signal.BUY, df, idx)
        assert result is True

    def test_filter_blocks_sell_when_oversold(self, downtrend_data):
        rsi = RSIIndicator()
        df = rsi.compute(downtrend_data)
        idx = len(df) - 1
        result = rsi.filter_signal(Signal.SELL, df, idx)
        assert result is False

    def test_get_signal_returns_none_without_crossover(self, uptrend_data):
        rsi = RSIIndicator()
        df = rsi.compute(uptrend_data)
        signal = rsi.get_signal(df, len(df) - 1)
        # No crossover in steady uptrend
        assert signal is None


class TestMACDIndicator:
    def test_default_parameters(self):
        macd = MACDIndicator()
        assert macd._fast_period == 12
        assert macd._slow_period == 26
        assert macd._signal_period == 9
        assert macd.name == "macd"

    def test_custom_parameters(self):
        macd = MACDIndicator(fast_period=8, slow_period=21, signal_period=5)
        assert macd._fast_period == 8
        assert macd._slow_period == 21
        assert macd._signal_period == 5

    def test_compute_adds_macd_columns(self, uptrend_data):
        macd = MACDIndicator()
        result = macd.compute(uptrend_data)
        assert "macd" in result.columns
        assert "macd_signal" in result.columns
        assert "macd_histogram" in result.columns

    def test_histogram_equals_macd_minus_signal(self, uptrend_data):
        macd = MACDIndicator()
        result = macd.compute(uptrend_data)
        computed_hist = result["macd"] - result["macd_signal"]
        actual_hist = result["macd_histogram"]
        diff = (computed_hist - actual_hist).drop_nulls().abs()
        assert (diff < 0.0001).all()

    def test_uptrend_positive_macd(self, uptrend_data):
        """MACD should be positive in strong uptrend."""
        macd = MACDIndicator()
        result = macd.compute(uptrend_data)
        last_macd = result["macd"][-1]
        assert last_macd > 0

    def test_downtrend_negative_macd(self, downtrend_data):
        """MACD should be negative in strong downtrend."""
        macd = MACDIndicator()
        result = macd.compute(downtrend_data)
        last_macd = result["macd"][-1]
        assert last_macd < 0

    def test_filter_blocks_buy_when_histogram_negative(self, downtrend_data):
        macd = MACDIndicator()
        df = macd.compute(downtrend_data)
        idx = len(df) - 1
        result = macd.filter_signal(Signal.BUY, df, idx)
        assert result is False

    def test_filter_allows_buy_when_histogram_positive(self, uptrend_data):
        macd = MACDIndicator()
        df = macd.compute(uptrend_data)
        idx = len(df) - 1
        result = macd.filter_signal(Signal.BUY, df, idx)
        assert result is True

    def test_filter_blocks_sell_when_histogram_positive(self, uptrend_data):
        macd = MACDIndicator()
        df = macd.compute(uptrend_data)
        idx = len(df) - 1
        result = macd.filter_signal(Signal.SELL, df, idx)
        assert result is False

    def test_get_signal_returns_none_without_crossover(self, uptrend_data):
        macd = MACDIndicator()
        df = macd.compute(uptrend_data)
        signal = macd.get_signal(df, len(df) - 1)
        # No crossover in steady uptrend
        assert signal is None


class TestIndicatorRegistry:
    def test_registry_loads_indicators(self):
        from tradingbot._components.indicators import get_registry

        registry = get_registry()
        assert "rsi" in registry.list()
        assert "macd" in registry.list()

    def test_get_enabled_returns_requested(self):
        from tradingbot._components.indicators import get_registry

        registry = get_registry()
        enabled = registry.get_enabled(["rsi"])
        assert len(enabled) == 1
        assert enabled[0].name == "rsi"

    def test_get_enabled_filters_invalid(self):
        from tradingbot._components.indicators import get_registry

        registry = get_registry()
        enabled = registry.get_enabled(["rsi", "invalid"])
        assert len(enabled) == 1
        assert enabled[0].name == "rsi"

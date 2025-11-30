"""Tests for signal generation."""

from datetime import datetime, timedelta

import polars as pl
import pytest

from tradingbot import Position, Signal, SignalGenerator


@pytest.fixture
def signal_generator() -> SignalGenerator:
    """Create a signal generator with default settings."""
    return SignalGenerator(swing_lookback=3)


@pytest.fixture
def sample_price_data() -> pl.DataFrame:
    """Create sample price data for signal testing."""
    # Create enough data for swing detection
    n = 50
    prices = []
    # Create oscillating pattern
    for i in range(n):
        base = 100 + (i % 10) - 5  # Oscillates around 100
        prices.append(base)

    base_date = datetime(2024, 1, 1)
    df = pl.DataFrame(
        {
            "datetime": [base_date + timedelta(days=i) for i in range(n)],
            "open": prices,
            "high": [p + 1 for p in prices],
            "low": [p - 1 for p in prices],
            "close": prices,
            "volume": [1000] * n,
        }
    )
    return df


class TestSignalGenerator:
    def test_initialization(self, signal_generator):
        assert signal_generator.swing_lookback == 3

    def test_hold_signal_insufficient_data(self, signal_generator, sample_price_data):
        signal, details = signal_generator.generate(sample_price_data, idx=2, position=None)
        assert signal == Signal.HOLD
        assert "reason" in details
        assert "Insufficient" in details["reason"]

    def test_hold_signal_when_position_open(self, signal_generator, sample_price_data):
        position = Position(
            entry_price=100.0,
            entry_index=10,
            entry_time="2024-01-10",
            direction="LONG",
            size=100,
            stop_loss=98.0,
            take_profit=104.0,
        )
        signal, details = signal_generator.generate(sample_price_data, idx=30, position=position)
        assert signal == Signal.HOLD

    def test_returns_signal_and_details(self, signal_generator, sample_price_data):
        signal, details = signal_generator.generate(sample_price_data, idx=30, position=None)
        assert isinstance(signal, Signal)
        assert isinstance(details, dict)

    def test_details_contain_trend(self, signal_generator, sample_price_data):
        signal, details = signal_generator.generate(sample_price_data, idx=30, position=None)
        # May or may not have trend depending on data
        if "trend" in details:
            assert details["trend"] in ["BULLISH", "BEARISH", "NEUTRAL"]


class TestSignalValues:
    def test_buy_signal_value(self):
        assert Signal.BUY.value == "BUY"

    def test_sell_signal_value(self):
        assert Signal.SELL.value == "SELL"

    def test_hold_signal_value(self):
        assert Signal.HOLD.value == "HOLD"

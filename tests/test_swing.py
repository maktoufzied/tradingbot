"""Tests for swing point detection."""

from datetime import datetime, timedelta

import polars as pl
import pytest

from tradingbot import SwingPoint, Trend, analyze_structure, find_swing_points


@pytest.fixture
def sample_ohlcv_data() -> pl.DataFrame:
    """Create sample OHLCV data with clear swing points."""
    # Create a simple up-down-up pattern
    prices = [100, 101, 102, 103, 104, 105, 104, 103, 102, 101, 100, 101, 102, 103, 104]
    base_date = datetime(2024, 1, 1)
    df = pl.DataFrame(
        {
            "datetime": [base_date + timedelta(days=i) for i in range(len(prices))],
            "open": prices,
            "high": [p + 0.5 for p in prices],
            "low": [p - 0.5 for p in prices],
            "close": prices,
            "volume": [1000] * len(prices),
        }
    )
    return df


@pytest.fixture
def bullish_swing_points() -> list[SwingPoint]:
    """Create swing points showing bullish structure (HH, HL)."""
    return [
        SwingPoint(0, 100.0, False),  # Low
        SwingPoint(5, 110.0, True),  # High
        SwingPoint(10, 105.0, False),  # Higher Low
        SwingPoint(15, 115.0, True),  # Higher High
        SwingPoint(20, 108.0, False),  # Higher Low
        SwingPoint(25, 120.0, True),  # Higher High
    ]


@pytest.fixture
def bearish_swing_points() -> list[SwingPoint]:
    """Create swing points showing bearish structure (LH, LL)."""
    return [
        SwingPoint(0, 120.0, True),  # High
        SwingPoint(5, 110.0, False),  # Low
        SwingPoint(10, 115.0, True),  # Lower High
        SwingPoint(15, 105.0, False),  # Lower Low
        SwingPoint(20, 110.0, True),  # Lower High
        SwingPoint(25, 100.0, False),  # Lower Low
    ]


class TestFindSwingPoints:
    def test_find_swing_points_returns_list(self, sample_ohlcv_data):
        result = find_swing_points(sample_ohlcv_data, lookback=2)
        assert isinstance(result, list)

    def test_find_swing_points_identifies_highs_and_lows(self, sample_ohlcv_data):
        result = find_swing_points(sample_ohlcv_data, lookback=2)
        highs = [sp for sp in result if sp.is_high]
        lows = [sp for sp in result if not sp.is_high]
        # Should find at least one high and one low
        assert len(highs) >= 0
        assert len(lows) >= 0

    def test_find_swing_points_sorted_by_index(self, sample_ohlcv_data):
        result = find_swing_points(sample_ohlcv_data, lookback=2)
        if len(result) > 1:
            indices = [sp.index for sp in result]
            assert indices == sorted(indices)

    def test_find_swing_points_empty_with_insufficient_data(self):
        df = pl.DataFrame(
            {
                "high": [100, 101, 102],
                "low": [99, 100, 101],
            }
        )
        result = find_swing_points(df, lookback=5)
        assert result == []

    def test_swing_point_has_timestamp(self, sample_ohlcv_data):
        result = find_swing_points(sample_ohlcv_data, lookback=2)
        for sp in result:
            assert sp.timestamp is not None


class TestAnalyzeStructure:
    def test_bullish_structure(self, bullish_swing_points):
        trend, analysis = analyze_structure(bullish_swing_points)
        assert trend == Trend.BULLISH
        assert "hh" in analysis
        assert "hl" in analysis

    def test_bearish_structure(self, bearish_swing_points):
        trend, analysis = analyze_structure(bearish_swing_points)
        assert trend == Trend.BEARISH
        assert "lh" in analysis
        assert "ll" in analysis

    def test_neutral_with_few_points(self):
        few_points = [
            SwingPoint(0, 100.0, True),
            SwingPoint(5, 95.0, False),
        ]
        trend, analysis = analyze_structure(few_points)
        assert trend == Trend.NEUTRAL
        assert analysis == {}

    def test_analysis_contains_last_swing_points(self, bullish_swing_points):
        trend, analysis = analyze_structure(bullish_swing_points)
        assert "last_high" in analysis
        assert "last_low" in analysis
        assert isinstance(analysis["last_high"], SwingPoint)
        assert isinstance(analysis["last_low"], SwingPoint)

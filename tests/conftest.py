"""Pytest configuration and fixtures for tradingbot tests."""

import polars as pl
import pytest

from tradingbot.types import SwingPoint


@pytest.fixture
def sample_df() -> pl.DataFrame:
    """Create sample OHLCV DataFrame for testing."""
    return pl.DataFrame(
        {
            "datetime": [f"2024-01-{i:02d}" for i in range(1, 21)],
            "open": [100.0] * 20,
            "high": [105.0] * 20,
            "low": [95.0] * 20,
            "close": [102.0] * 20,
            "volume": [10000] * 20,
        }
    )


@pytest.fixture
def swing_points() -> list[SwingPoint]:
    """Create sample swing points for testing."""
    return [
        SwingPoint(index=0, price=95.0, is_high=False),
        SwingPoint(index=5, price=110.0, is_high=True),
        SwingPoint(index=10, price=98.0, is_high=False),
        SwingPoint(index=15, price=108.0, is_high=True),
    ]

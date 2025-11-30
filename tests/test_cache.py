"""Tests for the smart caching layer."""

from datetime import datetime, timedelta

import polars as pl

from tradingbot._components._fetchers.cache import (
    _period_to_start_date,
    get_missing_ranges,
    merge_dataframes,
)


class TestPeriodToStartDate:
    def test_days(self):
        result = _period_to_start_date("30d")
        expected = datetime.now() - timedelta(days=30)
        assert abs((result - expected).total_seconds()) < 60

    def test_weeks(self):
        result = _period_to_start_date("4w")
        expected = datetime.now() - timedelta(weeks=4)
        assert abs((result - expected).total_seconds()) < 60

    def test_months(self):
        result = _period_to_start_date("6mo")
        expected = datetime.now() - timedelta(days=6 * 30)
        assert abs((result - expected).total_seconds()) < 60

    def test_years(self):
        result = _period_to_start_date("2y")
        expected = datetime.now() - timedelta(days=2 * 365)
        assert abs((result - expected).total_seconds()) < 60


class TestGetMissingRanges:
    def test_no_cache_returns_full_range(self):
        start = datetime(2024, 1, 1)
        end = datetime(2024, 6, 30)
        ranges = get_missing_ranges(None, start, end)
        assert len(ranges) == 1
        assert ranges[0] == (start, end)

    def test_empty_cache_returns_full_range(self):
        start = datetime(2024, 1, 1)
        end = datetime(2024, 6, 30)
        empty_df = pl.DataFrame()
        ranges = get_missing_ranges(empty_df, start, end)
        assert len(ranges) == 1
        assert ranges[0] == (start, end)

    def test_cache_covers_all_returns_empty(self):
        # Cache has Jan-June, request Feb-May
        cache_df = pl.DataFrame(
            {
                "datetime": [datetime(2024, 1, 1), datetime(2024, 6, 30)],
                "close": [100, 200],
            }
        )
        start = datetime(2024, 2, 1)
        end = datetime(2024, 5, 31)
        ranges = get_missing_ranges(cache_df, start, end)
        assert len(ranges) == 0

    def test_need_data_before_cache(self):
        # Cache has Mar-June, request Jan-June
        cache_df = pl.DataFrame(
            {
                "datetime": [datetime(2024, 3, 1), datetime(2024, 6, 30)],
                "close": [100, 200],
            }
        )
        start = datetime(2024, 1, 1)
        end = datetime(2024, 6, 30)
        ranges = get_missing_ranges(cache_df, start, end)
        assert len(ranges) == 1
        assert ranges[0][0] == datetime(2024, 1, 1)

    def test_need_data_after_cache(self):
        # Cache has Jan-Mar, request Jan-June
        cache_df = pl.DataFrame(
            {
                "datetime": [datetime(2024, 1, 1), datetime(2024, 3, 31)],
                "close": [100, 200],
            }
        )
        start = datetime(2024, 1, 1)
        end = datetime(2024, 6, 30)
        ranges = get_missing_ranges(cache_df, start, end)
        assert len(ranges) == 1
        assert ranges[0][1] == datetime(2024, 6, 30)

    def test_need_data_before_and_after(self):
        # Cache has Mar-Apr, request Jan-June
        cache_df = pl.DataFrame(
            {
                "datetime": [datetime(2024, 3, 1), datetime(2024, 4, 30)],
                "close": [100, 200],
            }
        )
        start = datetime(2024, 1, 1)
        end = datetime(2024, 6, 30)
        ranges = get_missing_ranges(cache_df, start, end)
        assert len(ranges) == 2


class TestMergeDataframes:
    def test_merge_with_none(self):
        new_df = pl.DataFrame(
            {
                "datetime": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
                "close": [100, 200],
            }
        )
        result = merge_dataframes(None, new_df)
        assert len(result) == 2

    def test_merge_removes_duplicates(self):
        existing = pl.DataFrame(
            {
                "datetime": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
                "close": [100, 200],
            }
        )
        new = pl.DataFrame(
            {
                "datetime": [datetime(2024, 1, 2), datetime(2024, 1, 3)],
                "close": [250, 300],
            }
        )
        result = merge_dataframes(existing, new)
        assert len(result) == 3
        # New data should win on duplicates (keep="last")
        jan2_row = result.filter(pl.col("datetime") == datetime(2024, 1, 2))
        assert jan2_row["close"][0] == 250

    def test_merge_sorts_by_datetime(self):
        existing = pl.DataFrame(
            {
                "datetime": [datetime(2024, 1, 3)],
                "close": [300],
            }
        )
        new = pl.DataFrame(
            {
                "datetime": [datetime(2024, 1, 1)],
                "close": [100],
            }
        )
        result = merge_dataframes(existing, new)
        assert result["datetime"][0] == datetime(2024, 1, 1)
        assert result["datetime"][-1] == datetime(2024, 1, 3)

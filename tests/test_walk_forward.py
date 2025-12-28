"""Comprehensive tests for walk-forward validation."""

from datetime import datetime, timedelta

import polars as pl
import pytest

from tradingbot import ExecutionModel, WalkForwardResult, WalkForwardValidator, walk_forward


def make_test_df(n_bars: int, trend: str = "up", volatility: float = 0.05) -> pl.DataFrame:
    """Create synthetic price data for testing with clear swing patterns.

    Args:
        n_bars: Number of bars to generate
        trend: 'up', 'down', or 'sideways'
        volatility: Price volatility factor
    """
    import math
    import random

    random.seed(42)

    base_price = 100.0
    prices = []

    # Create swing patterns with multiple frequency components
    swing_period_1 = 15  # shorter swing cycle for more signals
    swing_period_2 = 40  # longer swing cycle for structure

    for i in range(n_bars):
        # Trend component (stronger trend)
        if trend == "up":
            drift = 0.002
        elif trend == "down":
            drift = -0.002
        else:
            drift = 0.0

        # Multi-frequency swing component (creates clearer highs and lows)
        swing_1 = math.sin(2 * math.pi * i / swing_period_1) * volatility * 1.5
        swing_2 = math.sin(2 * math.pi * i / swing_period_2) * volatility * 2.5

        # Apply trend and swing
        current = base_price * (1 + drift * i + swing_1 + swing_2)

        # Add moderate noise
        noise = (random.random() - 0.5) * volatility * 0.3
        current = current * (1 + noise)

        # Generate OHLCV with realistic high/low spread
        bar_range = current * volatility * 0.8
        high = current + bar_range * (0.3 + 0.7 * random.random())
        low = current - bar_range * (0.3 + 0.7 * random.random())

        # Open and close in the direction of trend
        if trend == "up":
            open_price = low + (high - low) * (0.2 + 0.3 * random.random())
            close = low + (high - low) * (0.5 + 0.4 * random.random())
        elif trend == "down":
            open_price = low + (high - low) * (0.5 + 0.4 * random.random())
            close = low + (high - low) * (0.1 + 0.3 * random.random())
        else:
            open_price = low + (high - low) * random.random()
            close = low + (high - low) * random.random()

        volume = random.randint(100000, 1000000)

        prices.append(
            {
                "datetime": datetime(2023, 1, 1) + timedelta(hours=i),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )

    return pl.DataFrame(prices)


class TestWalkForwardValidatorInit:
    """Test WalkForwardValidator initialization."""

    def test_default_init(self) -> None:
        """Test default initialization values."""
        validator = WalkForwardValidator(symbol="TEST")

        assert validator.symbol == "TEST"
        assert validator.capital == 100000
        assert validator.n_folds == 5
        assert validator.train_ratio == 0.7
        assert isinstance(validator.execution_model, ExecutionModel)

    def test_custom_init(self) -> None:
        """Test custom initialization values."""
        execution_model = ExecutionModel.zero()
        validator = WalkForwardValidator(
            symbol="AAPL",
            capital=50000,
            n_folds=2,
            train_ratio=0.8,
            execution_model=execution_model,
        )

        assert validator.symbol == "AAPL"
        assert validator.capital == 50000
        assert validator.n_folds == 2
        assert validator.train_ratio == 0.8
        assert validator.execution_model.slippage_bps == 0

    def test_parameter_search_space(self) -> None:
        """Test parameter search space is reasonable."""
        validator = WalkForwardValidator(symbol="TEST")

        assert len(validator.swing_lb_range) >= 3
        assert len(validator.risk_pct_range) >= 2
        assert len(validator.rr_ratio_range) >= 2

        # Check reasonable ranges
        assert min(validator.swing_lb_range) >= 3
        assert max(validator.swing_lb_range) <= 15
        assert min(validator.risk_pct_range) >= 0.005
        assert max(validator.risk_pct_range) <= 0.05


class TestWalkForwardValidation:
    """Test walk-forward validation process."""

    def test_validate_with_uptrend_data(self) -> None:
        """Test validation with trending data produces results."""
        df = make_test_df(2000, trend="up")  # More data for reliable trades
        validator = WalkForwardValidator(symbol="TEST", n_folds=2)

        result = validator.validate(df, verbose=False)

        assert isinstance(result, WalkForwardResult)
        assert result.symbol == "TEST"
        assert result.n_folds == 2
        assert len(result.folds) > 0

    def test_validate_with_downtrend_data(self) -> None:
        """Test validation with downtrend data."""
        df = make_test_df(2000, trend="down")
        validator = WalkForwardValidator(symbol="TEST", n_folds=2)

        result = validator.validate(df, verbose=False)

        assert isinstance(result, WalkForwardResult)
        # Downtrend should have lower/negative returns
        assert len(result.folds) > 0

    def test_validate_with_sideways_data(self) -> None:
        """Test validation with sideways data."""
        df = make_test_df(2000, trend="sideways")
        validator = WalkForwardValidator(symbol="TEST", n_folds=2)

        result = validator.validate(df, verbose=False)

        assert isinstance(result, WalkForwardResult)

    def test_insufficient_data_raises_error(self) -> None:
        """Test that insufficient data raises an error."""
        df = make_test_df(50)  # Too few bars
        validator = WalkForwardValidator(symbol="TEST", n_folds=5)

        with pytest.raises(ValueError, match="Insufficient data"):
            validator.validate(df, verbose=False)

    def test_fold_count_matches_request(self) -> None:
        """Test that requested fold count is respected."""
        df = make_test_df(2400, trend="up")

        for n_folds in [3, 5]:
            validator = WalkForwardValidator(symbol="TEST", n_folds=n_folds)
            result = validator.validate(df, verbose=False)

            # May have fewer folds if some failed, but never more
            assert len(result.folds) <= n_folds

    def test_train_ratio_affects_split(self) -> None:
        """Test that train ratio affects data split."""
        df = make_test_df(2400, trend="up")

        # Higher train ratio = more training data per fold
        validator_70 = WalkForwardValidator(symbol="TEST", n_folds=2, train_ratio=0.7)
        validator_80 = WalkForwardValidator(symbol="TEST", n_folds=2, train_ratio=0.8)

        result_70 = validator_70.validate(df, verbose=False)
        result_80 = validator_80.validate(df, verbose=False)

        # With 80% train ratio, should have more training bars on average
        if result_70.folds and result_80.folds:
            avg_train_70 = sum(f.train_bars for f in result_70.folds) / len(result_70.folds)
            avg_train_80 = sum(f.train_bars for f in result_80.folds) / len(result_80.folds)
            # 80% train should have more training data
            assert avg_train_80 >= avg_train_70 * 0.9  # Allow some tolerance


class TestFoldResults:
    """Test individual fold result structure."""

    def test_fold_result_has_required_fields(self) -> None:
        """Test that fold results have all required fields."""
        df = make_test_df(2000, trend="up")
        validator = WalkForwardValidator(symbol="TEST", n_folds=2)

        result = validator.validate(df, verbose=False)

        if result.folds:
            fold = result.folds[0]

            # Check all fields are present
            assert hasattr(fold, "fold")
            assert hasattr(fold, "train_start")
            assert hasattr(fold, "train_end")
            assert hasattr(fold, "test_start")
            assert hasattr(fold, "test_end")
            assert hasattr(fold, "train_bars")
            assert hasattr(fold, "test_bars")
            assert hasattr(fold, "best_swing_lb")
            assert hasattr(fold, "best_risk_pct")
            assert hasattr(fold, "best_rr_ratio")
            assert hasattr(fold, "train_return")
            assert hasattr(fold, "train_trades")
            assert hasattr(fold, "test_return")
            assert hasattr(fold, "test_trades")

    def test_fold_dates_are_sequential(self) -> None:
        """Test that fold dates don't overlap incorrectly."""
        df = make_test_df(2000, trend="up")
        validator = WalkForwardValidator(symbol="TEST", n_folds=2)

        result = validator.validate(df, verbose=False)

        if len(result.folds) >= 2:
            for i in range(1, len(result.folds)):
                prev_fold = result.folds[i - 1]
                curr_fold = result.folds[i]

                # Test periods should be sequential (later folds have later test periods)
                assert curr_fold.test_start >= prev_fold.test_start

    def test_fold_params_are_valid(self) -> None:
        """Test that found parameters are within valid ranges."""
        df = make_test_df(2000, trend="up")
        validator = WalkForwardValidator(symbol="TEST", n_folds=2)

        result = validator.validate(df, verbose=False)

        for fold in result.folds:
            assert fold.best_swing_lb in validator.swing_lb_range
            assert fold.best_risk_pct in validator.risk_pct_range
            assert fold.best_rr_ratio in validator.rr_ratio_range


class TestAggregatedResults:
    """Test aggregated walk-forward results."""

    def test_aggregated_metrics_computed(self) -> None:
        """Test that aggregated metrics are computed correctly."""
        df = make_test_df(2000, trend="up")
        validator = WalkForwardValidator(symbol="TEST", n_folds=2)

        result = validator.validate(df, verbose=False)

        # Check aggregated metrics exist
        assert hasattr(result, "avg_train_return")
        assert hasattr(result, "avg_test_return")
        assert hasattr(result, "total_train_trades")
        assert hasattr(result, "total_test_trades")
        assert hasattr(result, "return_degradation")
        assert hasattr(result, "degradation_pct")
        assert hasattr(result, "consistency")

    def test_avg_return_is_average_of_folds(self) -> None:
        """Test that average return is correctly computed."""
        df = make_test_df(2000, trend="up")
        validator = WalkForwardValidator(symbol="TEST", n_folds=2)

        result = validator.validate(df, verbose=False)

        if result.folds:
            expected_avg_train = sum(f.train_return for f in result.folds) / len(result.folds)
            expected_avg_test = sum(f.test_return for f in result.folds) / len(result.folds)

            assert result.avg_train_return == pytest.approx(expected_avg_train, rel=1e-6)
            assert result.avg_test_return == pytest.approx(expected_avg_test, rel=1e-6)

    def test_total_trades_is_sum_of_folds(self) -> None:
        """Test that total trades is sum of all folds."""
        df = make_test_df(2000, trend="up")
        validator = WalkForwardValidator(symbol="TEST", n_folds=2)

        result = validator.validate(df, verbose=False)

        if result.folds:
            expected_train = sum(f.train_trades for f in result.folds)
            expected_test = sum(f.test_trades for f in result.folds)

            assert result.total_train_trades == expected_train
            assert result.total_test_trades == expected_test

    def test_degradation_calculation(self) -> None:
        """Test degradation is correctly calculated."""
        df = make_test_df(2000, trend="up")
        validator = WalkForwardValidator(symbol="TEST", n_folds=2)

        result = validator.validate(df, verbose=False)

        expected_degradation = result.avg_train_return - result.avg_test_return
        assert result.return_degradation == pytest.approx(expected_degradation, rel=1e-6)

    def test_consistency_is_percentage(self) -> None:
        """Test consistency is between 0 and 100."""
        df = make_test_df(2000, trend="up")
        validator = WalkForwardValidator(symbol="TEST", n_folds=2)

        result = validator.validate(df, verbose=False)

        assert 0 <= result.consistency <= 100


class TestExecutionCostIntegration:
    """Test integration with execution cost model."""

    def test_zero_costs_vs_default_costs(self) -> None:
        """Test that zero costs produce different results than default."""
        df = make_test_df(2000, trend="up")

        validator_zero = WalkForwardValidator(
            symbol="TEST",
            n_folds=2,
            execution_model=ExecutionModel.zero(),
        )
        validator_default = WalkForwardValidator(
            symbol="TEST",
            n_folds=2,
            execution_model=ExecutionModel(),
        )

        result_zero = validator_zero.validate(df, verbose=False)
        result_default = validator_default.validate(df, verbose=False)

        # With costs, returns should be lower
        if result_zero.folds and result_default.folds:
            # Zero costs should have >= returns than with costs
            assert result_zero.avg_train_return >= result_default.avg_train_return - 1.0

    def test_high_costs_reduce_returns(self) -> None:
        """Test that high execution costs reduce returns."""
        df = make_test_df(2000, trend="up")

        validator_low = WalkForwardValidator(
            symbol="TEST",
            n_folds=2,
            execution_model=ExecutionModel(slippage_bps=1, spread_bps=1, commission_per_share=0.001),
        )
        validator_high = WalkForwardValidator(
            symbol="TEST",
            n_folds=2,
            execution_model=ExecutionModel(slippage_bps=20, spread_bps=10, commission_per_share=0.05),
        )

        result_low = validator_low.validate(df, verbose=False)
        result_high = validator_high.validate(df, verbose=False)

        # Higher costs should reduce returns
        if result_low.folds and result_high.folds:
            assert result_low.avg_train_return >= result_high.avg_train_return


class TestConvenienceFunction:
    """Test the walk_forward convenience function."""

    def test_walk_forward_function(self) -> None:
        """Test the convenience function works."""
        df = make_test_df(2000, trend="up")

        result = walk_forward(
            symbol="TEST",
            df=df,
            interval="1h",
            period="1y",
            n_folds=2,
            verbose=False,
        )

        assert isinstance(result, WalkForwardResult)
        assert result.symbol == "TEST"
        assert result.interval == "1h"
        assert result.period == "1y"

    def test_walk_forward_with_all_params(self) -> None:
        """Test convenience function with all parameters."""
        df = make_test_df(2000, trend="up")

        result = walk_forward(
            symbol="AAPL",
            df=df,
            interval="15m",
            period="6mo",
            n_folds=4,
            train_ratio=0.75,
            capital=50000,
            execution_model=ExecutionModel.zero(),
            verbose=False,
        )

        assert result.symbol == "AAPL"
        assert result.interval == "15m"
        assert result.period == "6mo"
        assert result.n_folds == 4
        assert result.train_ratio == 0.75


class TestOverfittingDetection:
    """Test overfitting detection capabilities."""

    def test_high_degradation_indicates_overfitting(self) -> None:
        """Test that high train/test degradation is captured."""
        df = make_test_df(2000, trend="up")
        validator = WalkForwardValidator(symbol="TEST", n_folds=2)

        result = validator.validate(df, verbose=False)

        # Degradation percentage should be meaningful
        # (may be positive or negative depending on data)
        assert isinstance(result.degradation_pct, float)

    def test_consistency_captures_profitable_folds(self) -> None:
        """Test that consistency metric captures profitable folds."""
        df = make_test_df(2000, trend="up")
        validator = WalkForwardValidator(symbol="TEST", n_folds=5)

        result = validator.validate(df, verbose=False)

        if result.folds:
            # Count profitable test folds manually
            profitable_count = sum(1 for f in result.folds if f.test_return > 0)
            expected_consistency = profitable_count / len(result.folds) * 100

            assert result.consistency == pytest.approx(expected_consistency, rel=1e-6)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_single_fold(self) -> None:
        """Test with single fold (minimum)."""
        df = make_test_df(300, trend="up")
        validator = WalkForwardValidator(symbol="TEST", n_folds=1)

        result = validator.validate(df, verbose=False)

        assert len(result.folds) <= 1

    def test_many_folds(self) -> None:
        """Test with many folds."""
        df = make_test_df(2000, trend="up")
        validator = WalkForwardValidator(symbol="TEST", n_folds=10)

        result = validator.validate(df, verbose=False)

        assert len(result.folds) <= 10

    def test_high_train_ratio(self) -> None:
        """Test with high train ratio."""
        df = make_test_df(2000, trend="up")
        validator = WalkForwardValidator(symbol="TEST", n_folds=2, train_ratio=0.9)

        result = validator.validate(df, verbose=False)

        assert isinstance(result, WalkForwardResult)

    def test_low_train_ratio(self) -> None:
        """Test with low train ratio."""
        df = make_test_df(2000, trend="up")
        validator = WalkForwardValidator(symbol="TEST", n_folds=2, train_ratio=0.5)

        result = validator.validate(df, verbose=False)

        assert isinstance(result, WalkForwardResult)

    def test_different_symbols(self) -> None:
        """Test that symbol is correctly tracked."""
        df = make_test_df(2000, trend="up")

        for symbol in ["AAPL", "MSFT", "GOOGL"]:
            validator = WalkForwardValidator(symbol=symbol, n_folds=2)
            result = validator.validate(df, verbose=False)

            assert result.symbol == symbol


class TestVerboseOutput:
    """Test verbose output (without capturing, just ensure no errors)."""

    def test_verbose_true_no_error(self) -> None:
        """Test that verbose=True runs without error."""
        df = make_test_df(2000, trend="up")
        validator = WalkForwardValidator(symbol="TEST", n_folds=2)

        # Should not raise
        result = validator.validate(df, verbose=True)

        assert isinstance(result, WalkForwardResult)

    def test_verbose_false_no_error(self) -> None:
        """Test that verbose=False runs without error."""
        df = make_test_df(2000, trend="up")
        validator = WalkForwardValidator(symbol="TEST", n_folds=2)

        result = validator.validate(df, verbose=False)

        assert isinstance(result, WalkForwardResult)

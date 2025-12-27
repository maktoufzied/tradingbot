"""Bollinger Bands indicator."""

import polars as pl

from tradingbot.types import Signal


class BollingerIndicator:
    """Bollinger Bands indicator.

    Bollinger Bands consist of:
    - Middle band: SMA of close price
    - Upper band: SMA + (std_dev * multiplier)
    - Lower band: SMA - (std_dev * multiplier)

    Signals:
    - Price touches lower band = potential buy (mean reversion)
    - Price touches upper band = potential sell (mean reversion)
    - Squeeze (narrow bands) = volatility expansion coming
    """

    def __init__(
        self,
        period: int = 20,
        std_dev: float = 2.0,
    ) -> None:
        self._period = period
        self._std_dev = std_dev

    @property
    def name(self) -> str:
        return "bollinger"

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add Bollinger Bands columns to DataFrame."""
        close = df["close"]

        sma = close.rolling_mean(window_size=self._period)
        std = close.rolling_std(window_size=self._period)

        upper = sma + (std * self._std_dev)
        lower = sma - (std * self._std_dev)

        # Bandwidth: (upper - lower) / middle - measures volatility
        bandwidth = (upper - lower) / (sma + 1e-10)

        # %B: (price - lower) / (upper - lower) - position within bands
        percent_b = (close - lower) / ((upper - lower) + 1e-10)

        return df.with_columns(
            [
                sma.alias("bb_middle"),
                upper.alias("bb_upper"),
                lower.alias("bb_lower"),
                bandwidth.alias("bb_bandwidth"),
                percent_b.alias("bb_percent_b"),
            ]
        )

    def get_signal(self, df: pl.DataFrame, idx: int) -> Signal | None:
        """Generate signal on Bollinger Band touches."""
        if "bb_lower" not in df.columns or idx < 1:
            return None

        close = df["close"][idx]
        lower = df["bb_lower"][idx]
        upper = df["bb_upper"][idx]
        prev_close = df["close"][idx - 1]
        prev_lower = df["bb_lower"][idx - 1]
        prev_upper = df["bb_upper"][idx - 1]

        if any(v is None for v in [close, lower, upper, prev_close, prev_lower, prev_upper]):
            return None

        # Price crosses below lower band then back above = BUY
        if prev_close <= prev_lower and close > lower:
            return Signal.BUY

        # Price crosses above upper band then back below = SELL
        if prev_close >= prev_upper and close < upper:
            return Signal.SELL

        return None

    def filter_signal(self, signal: Signal, df: pl.DataFrame, idx: int) -> bool:
        """Filter: block signals during squeeze (low volatility)."""
        if "bb_bandwidth" not in df.columns:
            return True

        bandwidth = df["bb_bandwidth"][idx]
        if bandwidth is None:
            return True

        # Block signals if bandwidth is very low (squeeze)
        # Squeeze threshold is typically 20th percentile of historical bandwidth
        return bool(bandwidth > 0.02)

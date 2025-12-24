"""MACD (Moving Average Convergence Divergence) indicator."""

import polars as pl

from tradingbot.types import Signal


class MACDIndicator:
    """Moving Average Convergence Divergence indicator.

    MACD consists of:
    - MACD line: fast EMA - slow EMA
    - Signal line: EMA of MACD line
    - Histogram: MACD - Signal

    Signals:
    - MACD crosses above signal = bullish
    - MACD crosses below signal = bearish
    """

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> None:
        self._fast_period = fast_period
        self._slow_period = slow_period
        self._signal_period = signal_period

    @property
    def name(self) -> str:
        return "macd"

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add MACD, signal, and histogram columns to DataFrame."""
        close = df["close"]

        ema_fast = close.ewm_mean(span=self._fast_period, adjust=False)
        ema_slow = close.ewm_mean(span=self._slow_period, adjust=False)

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm_mean(span=self._signal_period, adjust=False)
        histogram = macd_line - signal_line

        return df.with_columns(
            [
                macd_line.alias("macd"),
                signal_line.alias("macd_signal"),
                histogram.alias("macd_histogram"),
            ]
        )

    def get_signal(self, df: pl.DataFrame, idx: int) -> Signal | None:
        """Generate signal on MACD/signal line crossover."""
        if "macd" not in df.columns or idx < 1:
            return None

        macd_curr = df["macd"][idx]
        macd_prev = df["macd"][idx - 1]
        signal_curr = df["macd_signal"][idx]
        signal_prev = df["macd_signal"][idx - 1]

        if any(v is None for v in [macd_curr, macd_prev, signal_curr, signal_prev]):
            return None

        # MACD crosses above signal = BUY
        if macd_prev <= signal_prev and macd_curr > signal_curr:
            return Signal.BUY

        # MACD crosses below signal = SELL
        if macd_prev >= signal_prev and macd_curr < signal_curr:
            return Signal.SELL

        return None

    def filter_signal(self, signal: Signal, df: pl.DataFrame, idx: int) -> bool:
        """Filter: require MACD histogram direction to confirm signal."""
        if "macd_histogram" not in df.columns:
            return True

        hist = df["macd_histogram"][idx]
        if hist is None:
            return True

        # BUY requires positive histogram (bullish momentum)
        if signal == Signal.BUY and hist < 0:
            return False

        # SELL requires negative histogram (bearish momentum)
        return not (signal == Signal.SELL and hist > 0)

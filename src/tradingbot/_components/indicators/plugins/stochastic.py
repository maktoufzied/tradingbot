"""Stochastic Oscillator indicator."""

import polars as pl

from tradingbot.types import Signal


class StochasticIndicator:
    """Stochastic Oscillator indicator.

    Stochastic compares closing price to price range:
    - %K: (Close - Lowest Low) / (Highest High - Lowest Low) * 100
    - %D: SMA of %K (signal line)

    Signals:
    - %K crosses above %D in oversold zone = BUY
    - %K crosses below %D in overbought zone = SELL
    """

    def __init__(
        self,
        k_period: int = 14,
        d_period: int = 3,
        smooth_k: int = 3,
        overbought: float = 80.0,
        oversold: float = 20.0,
    ) -> None:
        self._k_period = k_period
        self._d_period = d_period
        self._smooth_k = smooth_k
        self._overbought = overbought
        self._oversold = oversold

    @property
    def name(self) -> str:
        return "stochastic"

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add Stochastic columns to DataFrame."""
        high = df["high"]
        low = df["low"]
        close = df["close"]

        # Highest high and lowest low over k_period
        highest_high = high.rolling_max(window_size=self._k_period)
        lowest_low = low.rolling_min(window_size=self._k_period)

        # Raw %K
        raw_k = (close - lowest_low) / ((highest_high - lowest_low) + 1e-10) * 100

        # Smoothed %K (slow stochastic)
        stoch_k = raw_k.rolling_mean(window_size=self._smooth_k)

        # %D (signal line)
        stoch_d = stoch_k.rolling_mean(window_size=self._d_period)

        return df.with_columns(
            [
                stoch_k.alias("stoch_k"),
                stoch_d.alias("stoch_d"),
            ]
        )

    def get_signal(self, df: pl.DataFrame, idx: int) -> Signal | None:
        """Generate signal on %K/%D crossover in extreme zones."""
        if "stoch_k" not in df.columns or idx < 1:
            return None

        k_curr = df["stoch_k"][idx]
        k_prev = df["stoch_k"][idx - 1]
        d_curr = df["stoch_d"][idx]
        d_prev = df["stoch_d"][idx - 1]

        if any(v is None for v in [k_curr, k_prev, d_curr, d_prev]):
            return None

        # %K crosses above %D in oversold zone = BUY
        if k_prev <= d_prev and k_curr > d_curr and k_curr < self._oversold + 10:
            return Signal.BUY

        # %K crosses below %D in overbought zone = SELL
        if k_prev >= d_prev and k_curr < d_curr and k_curr > self._overbought - 10:
            return Signal.SELL

        return None

    def filter_signal(self, signal: Signal, df: pl.DataFrame, idx: int) -> bool:
        """Filter: block BUY if overbought, block SELL if oversold."""
        if "stoch_k" not in df.columns:
            return True

        k = df["stoch_k"][idx]
        if k is None:
            return True

        if signal == Signal.BUY and k > self._overbought:
            return False

        return not (signal == Signal.SELL and k < self._oversold)

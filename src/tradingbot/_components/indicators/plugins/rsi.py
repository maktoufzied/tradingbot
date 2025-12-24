"""RSI (Relative Strength Index) indicator."""

import polars as pl

from tradingbot.types import Signal


class RSIIndicator:
    """Relative Strength Index indicator.

    RSI measures momentum on a 0-100 scale:
    - RSI > overbought: Potential sell zone
    - RSI < oversold: Potential buy zone
    """

    def __init__(
        self,
        period: int = 14,
        overbought: float = 70.0,
        oversold: float = 30.0,
    ) -> None:
        self._period = period
        self._overbought = overbought
        self._oversold = oversold

    @property
    def name(self) -> str:
        return "rsi"

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add RSI column to DataFrame."""
        delta = df["close"].diff()

        gains = delta.clip(lower_bound=0)
        losses = (-delta).clip(lower_bound=0)

        avg_gain = gains.rolling_mean(window_size=self._period)
        avg_loss = losses.rolling_mean(window_size=self._period)

        # Avoid division by zero
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))

        return df.with_columns(rsi.alias("rsi"))

    def get_signal(self, df: pl.DataFrame, idx: int) -> Signal | None:
        """Generate signal on RSI crossover of overbought/oversold levels."""
        if "rsi" not in df.columns or idx < 1:
            return None

        rsi_curr = df["rsi"][idx]
        rsi_prev = df["rsi"][idx - 1]

        if rsi_curr is None or rsi_prev is None:
            return None

        # Oversold crossover (RSI crosses above oversold) = BUY
        if rsi_prev < self._oversold <= rsi_curr:
            return Signal.BUY

        # Overbought crossover (RSI crosses below overbought) = SELL
        if rsi_prev > self._overbought >= rsi_curr:
            return Signal.SELL

        return None

    def filter_signal(self, signal: Signal, df: pl.DataFrame, idx: int) -> bool:
        """Filter: block BUY if overbought, block SELL if oversold."""
        if "rsi" not in df.columns:
            return True

        rsi = df["rsi"][idx]
        if rsi is None:
            return True

        if signal == Signal.BUY and rsi > self._overbought:
            return False

        return not (signal == Signal.SELL and rsi < self._oversold)

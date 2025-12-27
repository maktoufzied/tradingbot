"""EMA Crossover indicator."""

import polars as pl

from tradingbot.types import Signal


class EMACrossoverIndicator:
    """Exponential Moving Average Crossover indicator.

    Uses fast and slow EMAs to identify trend direction:
    - Fast EMA crosses above slow EMA = bullish
    - Fast EMA crosses below slow EMA = bearish

    Common periods: 8/21, 9/21, 12/26
    """

    def __init__(
        self,
        fast_period: int = 9,
        slow_period: int = 21,
    ) -> None:
        self._fast_period = fast_period
        self._slow_period = slow_period

    @property
    def name(self) -> str:
        return "ema_crossover"

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add EMA columns to DataFrame."""
        close = df["close"]

        ema_fast = close.ewm_mean(span=self._fast_period, adjust=False)
        ema_slow = close.ewm_mean(span=self._slow_period, adjust=False)

        # Distance between EMAs as percentage
        ema_diff = (ema_fast - ema_slow) / (ema_slow + 1e-10) * 100

        return df.with_columns(
            [
                ema_fast.alias("ema_fast"),
                ema_slow.alias("ema_slow"),
                ema_diff.alias("ema_diff"),
            ]
        )

    def get_signal(self, df: pl.DataFrame, idx: int) -> Signal | None:
        """Generate signal on EMA crossover."""
        if "ema_fast" not in df.columns or idx < 1:
            return None

        fast_curr = df["ema_fast"][idx]
        fast_prev = df["ema_fast"][idx - 1]
        slow_curr = df["ema_slow"][idx]
        slow_prev = df["ema_slow"][idx - 1]

        if any(v is None for v in [fast_curr, fast_prev, slow_curr, slow_prev]):
            return None

        # Fast EMA crosses above slow EMA = BUY
        if fast_prev <= slow_prev and fast_curr > slow_curr:
            return Signal.BUY

        # Fast EMA crosses below slow EMA = SELL
        if fast_prev >= slow_prev and fast_curr < slow_curr:
            return Signal.SELL

        return None

    def filter_signal(self, signal: Signal, df: pl.DataFrame, idx: int) -> bool:
        """Filter: require price to be on correct side of EMAs."""
        if "ema_fast" not in df.columns:
            return True

        close = df["close"][idx]
        ema_fast = df["ema_fast"][idx]
        ema_slow = df["ema_slow"][idx]

        if any(v is None for v in [close, ema_fast, ema_slow]):
            return True

        # BUY requires price above both EMAs
        if signal == Signal.BUY and close < ema_slow:
            return False

        # SELL requires price below both EMAs
        return not (signal == Signal.SELL and close > ema_slow)

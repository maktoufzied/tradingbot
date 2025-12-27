"""Keltner Channels indicator."""

import polars as pl

from tradingbot.types import Signal


class KeltnerIndicator:
    """Keltner Channels indicator.

    Keltner Channels use ATR for volatility bands:
    - Middle: EMA of close
    - Upper: EMA + (ATR * multiplier)
    - Lower: EMA - (ATR * multiplier)

    Key uses:
    - Squeeze detection with Bollinger Bands
    - Trend following (riding the channel)
    - Mean reversion at channel edges
    """

    def __init__(
        self,
        ema_period: int = 20,
        atr_period: int = 10,
        multiplier: float = 2.0,
    ) -> None:
        self._ema_period = ema_period
        self._atr_period = atr_period
        self._multiplier = multiplier

    @property
    def name(self) -> str:
        return "keltner"

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add Keltner Channel columns to DataFrame."""
        high = df["high"]
        low = df["low"]
        close = df["close"]

        # True Range
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pl.max_horizontal(tr1, tr2, tr3)

        # ATR
        atr = tr.ewm_mean(span=self._atr_period, adjust=False)

        # EMA (middle band)
        ema = close.ewm_mean(span=self._ema_period, adjust=False)

        # Keltner Channels
        upper = ema + (atr * self._multiplier)
        lower = ema - (atr * self._multiplier)

        return df.with_columns(
            [
                ema.alias("kc_middle"),
                upper.alias("kc_upper"),
                lower.alias("kc_lower"),
                atr.alias("kc_atr"),
            ]
        )

    def get_signal(self, df: pl.DataFrame, idx: int) -> Signal | None:
        """Generate signal on Keltner Channel breakouts/bounces."""
        if "kc_middle" not in df.columns or idx < 1:
            return None

        close = df["close"][idx]
        prev_close = df["close"][idx - 1]
        lower = df["kc_lower"][idx]
        upper = df["kc_upper"][idx]
        prev_lower = df["kc_lower"][idx - 1]
        prev_upper = df["kc_upper"][idx - 1]

        if any(v is None for v in [close, prev_close, lower, upper, prev_lower, prev_upper]):
            return None

        # Price bounces off lower channel = BUY
        if prev_close <= prev_lower and close > lower:
            return Signal.BUY

        # Price rejects from upper channel = SELL
        if prev_close >= prev_upper and close < upper:
            return Signal.SELL

        return None

    def filter_signal(self, signal: Signal, df: pl.DataFrame, idx: int) -> bool:
        """Filter: allow signals based on channel position."""
        if "kc_middle" not in df.columns:
            return True

        close = df["close"][idx]
        middle = df["kc_middle"][idx]
        upper = df["kc_upper"][idx]
        lower = df["kc_lower"][idx]

        if any(v is None for v in [close, middle, upper, lower]):
            return True

        # For mean reversion BUY, price should be in lower half
        if signal == Signal.BUY and close > middle:
            return True  # Still allow trend-following buys

        # For mean reversion SELL, price should be in upper half
        return True

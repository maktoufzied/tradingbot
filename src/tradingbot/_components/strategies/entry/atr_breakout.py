"""ATR Breakout entry strategy.

Trades breakouts when price moves beyond ATR-based bands.

Win rate: 50-55% | Best for trending/volatile markets
"""

import polars as pl

from tradingbot.types import Signal

from ..interfaces import Entry
from ..registry import register_entry


class ATRBreakoutStrategy:
    """Entry strategy based on ATR breakouts."""

    @property
    def name(self) -> str:
        return "atr_breakout"

    def __init__(
        self,
        atr_period: int = 14,
        atr_multiplier: float = 2.0,
    ) -> None:
        self._atr_period = atr_period
        self._atr_multiplier = atr_multiplier

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute ATR and breakout bands."""
        if "atr" in df.columns:
            return df

        # Compute True Range and ATR using proper Polars expressions
        return df.with_columns(
            [
                pl.max_horizontal(
                    pl.col("high") - pl.col("low"),
                    (pl.col("high") - pl.col("close").shift(1)).abs(),
                    (pl.col("low") - pl.col("close").shift(1)).abs(),
                )
                .rolling_mean(window_size=self._atr_period)
                .alias("atr"),
                pl.col("close").rolling_mean(window_size=self._atr_period).alias("sma"),
            ]
        ).with_columns(
            [
                (pl.col("sma") + pl.col("atr") * self._atr_multiplier).alias("atr_upper"),
                (pl.col("sma") - pl.col("atr") * self._atr_multiplier).alias("atr_lower"),
            ]
        )

    def signal(self, df: pl.DataFrame, idx: int, has_position: bool) -> Entry:
        """Generate signal based on ATR breakout."""
        if idx < self._atr_period + 5:
            return Entry(Signal.HOLD, "Insufficient data", {})

        hist = df.head(idx + 1)
        if "atr" not in hist.columns:
            hist = self.compute(hist)

        close = float(hist["close"][-1])
        atr = hist["atr"][-1]
        upper = hist["atr_upper"][-1]
        lower = hist["atr_lower"][-1]

        if atr is None or upper is None or lower is None:
            return Entry(Signal.HOLD, "ATR calculation error", {})

        details: dict[str, str | float] = {
            "price": round(close, 2),
            "atr": round(float(atr), 2),
            "upper": round(float(upper), 2),
            "lower": round(float(lower), 2),
        }

        if has_position:
            return Entry(Signal.HOLD, "Position open", details)

        if close > upper:
            return Entry(Signal.BUY, "ATR breakout up", details)

        if close < lower:
            return Entry(Signal.SELL, "ATR breakdown", details)

        return Entry(Signal.HOLD, "", details)


# Register on import
_strategy = ATRBreakoutStrategy()
register_entry(_strategy)

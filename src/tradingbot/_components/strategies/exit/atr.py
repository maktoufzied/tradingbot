"""ATR-based exit strategy.

Places stop-loss and take-profit based on Average True Range.
Adapts to market volatility automatically.
"""

from typing import Final

import polars as pl

from tradingbot.types import Direction, SwingPoint

from ..interfaces import Exit
from ..registry import register_exit

# Maximum allowed stop distance from entry price
MAX_STOP_DISTANCE_PCT: Final[float] = 0.05  # 5%


class ATRExitStrategy:
    """Exit strategy using ATR for SL/TP placement."""

    @property
    def name(self) -> str:
        return "atr"

    def __init__(
        self,
        atr_period: int = 14,
        stop_atr_mult: float = 2.0,
    ) -> None:
        self._atr_period = atr_period
        self._stop_atr_mult = stop_atr_mult

    def _compute_atr(self, df: pl.DataFrame) -> float | None:
        """Compute current ATR value."""
        if len(df) < self._atr_period + 1:
            return None

        # Compute True Range using proper Polars expressions
        result = df.select(
            pl.max_horizontal(
                pl.col("high") - pl.col("low"),
                (pl.col("high") - pl.col("close").shift(1)).abs(),
                (pl.col("low") - pl.col("close").shift(1)).abs(),
            )
            .rolling_mean(window_size=self._atr_period)
            .alias("atr")
        )

        atr_val = result["atr"][-1]
        return float(atr_val) if atr_val is not None else None

    def calc(
        self,
        direction: Direction,
        entry: float,
        df: pl.DataFrame,
        swings: list[SwingPoint],
        rr_ratio: float,
        stop_pct: float = 0.01,
    ) -> Exit:
        """Calculate ATR-based stop-loss and take-profit."""
        _ = swings  # Not used by ATR strategy
        atr = self._compute_atr(df)

        # Fallback to percentage-based if ATR unavailable
        if atr is None:
            stop_distance = entry * stop_pct
        else:
            stop_distance = atr * self._stop_atr_mult
            # Cap stop distance
            max_stop = entry * MAX_STOP_DISTANCE_PCT
            stop_distance = min(stop_distance, max_stop)

        # TP based on RR ratio (no cap - honor the configured ratio)
        tp_distance = stop_distance * rr_ratio

        if direction == "LONG":
            stop = round(entry - stop_distance, 2)
            tp = round(entry + tp_distance, 2)
        else:
            stop = round(entry + stop_distance, 2)
            tp = round(entry - tp_distance, 2)

        return Exit(stop_loss=stop, take_profit=tp)


# Register on import
_strategy = ATRExitStrategy()
register_exit(_strategy)

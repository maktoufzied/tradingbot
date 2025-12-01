from typing import Final

import polars as pl

from ...models import Direction, SwingPoint

# Small buffer beyond swing point to avoid stop-hunting wicks
SWING_BUFFER_PCT: Final[float] = 0.002  # 0.2%

# Maximum allowed stop distance from entry price.
# Prevents absurd stops when swing points are far from current price.
# This caps risk per trade and ensures reasonable position sizing.
MAX_STOP_DISTANCE_PCT: Final[float] = 0.05  # 5%

# Fallback stop distance when no swing points exist
DEFAULT_STOP_PCT: Final[float] = 0.02  # 2%


class SwingStopStrategy:
    """Place stop loss at recent swing point, capped at max distance."""

    @property
    def name(self) -> str:
        return "swing"

    def calc_stop(
        self,
        direction: Direction,
        entry: float,
        df: pl.DataFrame,
        idx: int,
        swings: list[SwingPoint],
    ) -> float:
        if direction == "LONG":
            lows = [s for s in swings if not s.is_high]
            swing_stop = lows[-1].price * (1 - SWING_BUFFER_PCT) if lows else entry * (1 - DEFAULT_STOP_PCT)
            max_stop = entry * (1 - MAX_STOP_DISTANCE_PCT)
            return max(swing_stop, max_stop)
        else:
            highs = [s for s in swings if s.is_high]
            swing_stop = highs[-1].price * (1 + SWING_BUFFER_PCT) if highs else entry * (1 + DEFAULT_STOP_PCT)
            max_stop = entry * (1 + MAX_STOP_DISTANCE_PCT)
            return min(swing_stop, max_stop)

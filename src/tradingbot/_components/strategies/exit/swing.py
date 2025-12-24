"""Swing-based exit strategy.

Places stop-loss and take-profit at swing points (local highs/lows).
"""

from typing import Final

import polars as pl

from tradingbot.types import Direction, SwingPoint

from ..interfaces import Exit
from ..registry import register_exit

# Small buffer beyond swing point to avoid stop-hunting wicks
SWING_BUFFER_PCT: Final[float] = 0.002  # 0.2%

# Maximum allowed stop distance from entry price
MAX_STOP_DISTANCE_PCT: Final[float] = 0.05  # 5%

# Maximum allowed take-profit distance (realistic for day trading)
MAX_TP_DISTANCE_PCT: Final[float] = 0.015  # 1.5%

# Fallback stop distance when no swing points exist
DEFAULT_STOP_PCT: Final[float] = 0.02  # 2%


class SwingExitStrategy:
    """Exit strategy using swing points for SL/TP placement."""

    @property
    def name(self) -> str:
        return "swing"

    def calc(
        self,
        direction: Direction,
        entry: float,
        df: pl.DataFrame,
        swings: list[SwingPoint],
        rr_ratio: float,
    ) -> Exit:
        """Calculate swing-based stop-loss and take-profit."""
        stop = self._calc_stop(direction, entry, swings)
        tp = self._calc_tp(direction, entry, stop, rr_ratio, swings)
        return Exit(stop_loss=stop, take_profit=tp)

    def _calc_stop(self, direction: Direction, entry: float, swings: list[SwingPoint]) -> float:
        """Calculate stop-loss at recent swing point."""
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

    def _calc_tp(
        self,
        direction: Direction,
        entry: float,
        stop: float,
        rr_ratio: float,
        swings: list[SwingPoint],
    ) -> float:
        """Calculate take-profit at swing level or RR-based, capped at max distance."""
        risk = abs(entry - stop)
        max_tp_distance = entry * MAX_TP_DISTANCE_PCT

        # RR-based TP (capped)
        rr_distance = min(risk * rr_ratio, max_tp_distance)
        rr_tp = entry + rr_distance if direction == "LONG" else entry - rr_distance

        # Try swing-based TP
        if direction == "LONG":
            highs = [s for s in swings if s.is_high and s.price > entry]
            if highs:
                swing_tp = min(h.price for h in highs)
                swing_distance = swing_tp - entry
                if swing_distance >= risk and swing_distance <= max_tp_distance:
                    return swing_tp
        else:
            lows = [s for s in swings if not s.is_high and s.price < entry]
            if lows:
                swing_tp = max(low.price for low in lows)
                swing_distance = entry - swing_tp
                if swing_distance >= risk and swing_distance <= max_tp_distance:
                    return swing_tp

        return rr_tp


# Register on import
_strategy = SwingExitStrategy()
register_exit(_strategy)

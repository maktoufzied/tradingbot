from typing import Final

import polars as pl

from tradingbot.types import Direction, SwingPoint

# Small buffer beyond swing point to avoid stop-hunting wicks
SWING_BUFFER_PCT: Final[float] = 0.002  # 0.2%

# Maximum allowed stop distance from entry price.
# Prevents absurd stops when swing points are far from current price.
# This caps risk per trade and ensures reasonable position sizing.
MAX_STOP_DISTANCE_PCT: Final[float] = 0.05  # 5%

# Fallback stop distance when no swing points exist
DEFAULT_STOP_PCT: Final[float] = 0.02  # 2%


class SwingStopStrategy:
    """Place stop/TP at swing points, capped at max distance."""

    @property
    def name(self) -> str:
        return "swing"

    def calc(
        self,
        direction: Direction,
        entry: float,
        rr_ratio: float,
        bars: pl.DataFrame,
        swings: list[SwingPoint],
    ) -> tuple[float, float]:
        stop = self._calc_stop(direction, entry, swings)
        tp = self._calc_tp(direction, entry, stop, rr_ratio, swings)
        return stop, tp

    def _calc_stop(self, direction: Direction, entry: float, swings: list[SwingPoint]) -> float:
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
        self, direction: Direction, entry: float, stop: float, rr_ratio: float, swings: list[SwingPoint]
    ) -> float:
        """Target next swing level (resistance for LONG, support for SHORT).

        Falls back to RR-based TP if no suitable swing level exists.
        """
        risk = abs(entry - stop)
        rr_tp = entry + risk * rr_ratio if direction == "LONG" else entry - risk * rr_ratio

        if direction == "LONG":
            highs = [s for s in swings if s.is_high and s.price > entry]
            if highs:
                swing_tp = min(h.price for h in highs)
                if swing_tp - entry >= risk:
                    return swing_tp
        else:
            lows = [s for s in swings if not s.is_high and s.price < entry]
            if lows:
                swing_tp = max(low.price for low in lows)
                if entry - swing_tp >= risk:
                    return swing_tp

        return rr_tp

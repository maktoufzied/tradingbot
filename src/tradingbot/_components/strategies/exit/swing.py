"""Swing-based exit strategy.

Places stop-loss and take-profit at swing points (local highs/lows).

SL: At the last swing low (for longs) or last swing high (for shorts)
TP: At the next swing high (for longs) or next swing low (for shorts)

If no swing-based TP exists, falls back to R:R ratio calculation.
"""

from typing import Final

import polars as pl

from tradingbot.types import Direction, SwingPoint

from ..interfaces import Exit
from ..registry import register_exit

# Small buffer beyond swing point to avoid stop-hunting wicks
SWING_BUFFER_PCT: Final[float] = 0.002  # 0.2%

# Fallback stop distance when no swing points exist
DEFAULT_STOP_PCT: Final[float] = 0.02  # 2%


class SwingExitStrategy:
    """Exit strategy using swing points for SL/TP placement.

    Stop Loss: Placed at the most recent swing point in the opposite direction.
    - LONG: SL at last swing low (with small buffer below)
    - SHORT: SL at last swing high (with small buffer above)

    Take Profit: Placed at the nearest swing point in the profit direction.
    - LONG: TP at next swing high above entry
    - SHORT: TP at next swing low below entry

    If no valid swing TP exists, falls back to R:R ratio calculation.
    """

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
        stop_pct: float = 0.01,
    ) -> Exit:
        """Calculate swing-based stop-loss and take-profit."""
        _ = stop_pct  # Not used by swing strategy
        stop = self._calc_stop(direction, entry, swings)
        tp = self._calc_tp(direction, entry, stop, rr_ratio, swings)
        return Exit(stop_loss=stop, take_profit=tp)

    def _calc_stop(self, direction: Direction, entry: float, swings: list[SwingPoint]) -> float:
        """Calculate stop-loss at recent swing point."""
        if direction == "LONG":
            lows = [s for s in swings if not s.is_high]
            if lows:
                return lows[-1].price * (1 - SWING_BUFFER_PCT)
            return entry * (1 - DEFAULT_STOP_PCT)
        else:
            highs = [s for s in swings if s.is_high]
            if highs:
                return highs[-1].price * (1 + SWING_BUFFER_PCT)
            return entry * (1 + DEFAULT_STOP_PCT)

    def _calc_tp(
        self,
        direction: Direction,
        entry: float,
        stop: float,
        rr_ratio: float,
        swings: list[SwingPoint],
    ) -> float:
        """Calculate take-profit at next swing level, or R:R-based fallback."""
        risk = abs(entry - stop)

        # Try swing-based TP first (next resistance/support)
        if direction == "LONG":
            # Find swing highs above entry price
            highs_above = [s for s in swings if s.is_high and s.price > entry]
            if highs_above:
                # Use the nearest swing high as TP
                swing_tp = min(h.price for h in highs_above)
                # Only use if it gives at least 1:1 R:R
                if (swing_tp - entry) >= risk:
                    return swing_tp
        else:
            # Find swing lows below entry price
            lows_below = [s for s in swings if not s.is_high and s.price < entry]
            if lows_below:
                # Use the nearest swing low as TP
                swing_tp = max(low.price for low in lows_below)
                # Only use if it gives at least 1:1 R:R
                if (entry - swing_tp) >= risk:
                    return swing_tp

        # Fallback: R:R-based TP
        rr_tp = entry + (risk * rr_ratio) if direction == "LONG" else entry - (risk * rr_ratio)
        return rr_tp


# Register on import
_strategy = SwingExitStrategy()
register_exit(_strategy)

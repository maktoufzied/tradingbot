"""Fixed percentage exit strategy.

Places stop-loss and take-profit at fixed percentage distances from entry.
Simple but effective for consistent risk management.
"""

from typing import Final

import polars as pl

from tradingbot.types import Direction, SwingPoint

from ..interfaces import Exit
from ..registry import register_exit

# Default percentages
DEFAULT_STOP_PCT: Final[float] = 0.02  # 2%
DEFAULT_TP_PCT: Final[float] = 0.015  # 1.5%


class FixedExitStrategy:
    """Exit strategy using fixed percentage SL/TP."""

    @property
    def name(self) -> str:
        return "fixed"

    def __init__(
        self,
        stop_pct: float = DEFAULT_STOP_PCT,
        tp_pct: float = DEFAULT_TP_PCT,
    ) -> None:
        self._stop_pct = stop_pct
        self._tp_pct = tp_pct

    def calc(
        self,
        direction: Direction,
        entry: float,
        df: pl.DataFrame,
        swings: list[SwingPoint],
        rr_ratio: float,
    ) -> Exit:
        """Calculate fixed percentage stop-loss and take-profit.

        Note: rr_ratio is ignored - use tp_pct to control target.
        """
        stop_distance = entry * self._stop_pct
        tp_distance = entry * self._tp_pct

        if direction == "LONG":
            stop = entry - stop_distance
            tp = entry + tp_distance
        else:
            stop = entry + stop_distance
            tp = entry - tp_distance

        return Exit(stop_loss=stop, take_profit=tp)


# Register on import
_strategy = FixedExitStrategy()
register_exit(_strategy)

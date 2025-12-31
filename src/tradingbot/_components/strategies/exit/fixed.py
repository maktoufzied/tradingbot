"""Fixed percentage exit strategy.

Places stop-loss at fixed percentage from entry, take-profit based on RR ratio.
"""

import polars as pl

from tradingbot.types import Direction, SwingPoint

from ..interfaces import Exit
from ..registry import register_exit


class FixedExitStrategy:
    """Exit strategy using fixed percentage stop and RR-based take-profit."""

    @property
    def name(self) -> str:
        return "fixed"

    def calc(
        self,
        direction: Direction,
        entry: float,
        df: pl.DataFrame,
        swings: list[SwingPoint],
        rr_ratio: float,
        stop_pct: float = 0.01,
    ) -> Exit:
        """Calculate stop-loss and take-profit.

        Stop is placed at stop_pct from entry.
        Take-profit is placed at stop_distance * rr_ratio from entry.
        Prices are rounded to 2 decimals to avoid sub-penny rejection.
        """
        stop_distance = entry * stop_pct
        tp_distance = stop_distance * rr_ratio

        if direction == "LONG":
            stop = round(entry - stop_distance, 2)
            tp = round(entry + tp_distance, 2)
        else:
            stop = round(entry + stop_distance, 2)
            tp = round(entry - tp_distance, 2)

        return Exit(stop_loss=stop, take_profit=tp)


# Register on import
_strategy = FixedExitStrategy()
register_exit(_strategy)

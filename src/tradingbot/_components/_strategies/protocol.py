from typing import Protocol

import polars as pl

from ..models import Direction, SwingPoint


class StopStrategyProtocol(Protocol):
    """Protocol for stop loss calculation strategies."""

    @property
    def name(self) -> str:
        """Unique identifier for this strategy."""
        ...

    def calc_stop(
        self,
        direction: Direction,
        entry: float,
        df: pl.DataFrame,
        idx: int,
        swings: list[SwingPoint],
    ) -> float:
        """Calculate stop loss price.

        Args:
            direction: Trade direction ("LONG" or "SHORT")
            entry: Entry price
            df: Price DataFrame up to current bar
            idx: Current bar index
            swings: List of swing points

        Returns:
            Stop loss price
        """
        ...

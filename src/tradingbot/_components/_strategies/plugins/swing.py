import polars as pl

from ...models import Direction, SwingPoint


class SwingStopStrategy:
    """Stop loss based on recent swing points."""

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
        buf = 0.002  # 0.2% buffer

        if direction == "LONG":
            lows: list[SwingPoint] = [s for s in swings if not s.is_high]
            return lows[-1].price * (1 - buf) if lows else entry * 0.98
        else:
            highs: list[SwingPoint] = [s for s in swings if s.is_high]
            return highs[-1].price * (1 + buf) if highs else entry * 1.02

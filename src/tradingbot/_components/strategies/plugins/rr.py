import polars as pl

from tradingbot.types import Direction, SwingPoint


class RRExitStrategy:
    """Risk/reward ratio based exits - classic fixed RR approach."""

    def __init__(self, stop_pct: float = 0.02) -> None:
        self.stop_pct = stop_pct

    @property
    def name(self) -> str:
        return "rr"

    def calc(
        self,
        direction: Direction,
        entry: float,
        rr_ratio: float,
        bars: pl.DataFrame,
        swings: list[SwingPoint],
    ) -> tuple[float, float]:
        """Fixed percentage stop with RR-based take profit."""
        if direction == "LONG":
            stop = entry * (1 - self.stop_pct)
            risk = entry - stop
            return stop, entry + risk * rr_ratio
        else:
            stop = entry * (1 + self.stop_pct)
            risk = stop - entry
            return stop, entry - risk * rr_ratio

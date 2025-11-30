import polars as pl

from ._strategies import StopStrategy
from .models import Direction, SwingPoint


class RiskManager:
    def __init__(self, capital: float, risk_pct: float = 0.01, rr_ratio: float = 2.0):
        self.initial: float = capital
        self.capital: float = capital
        self.risk_pct: float = risk_pct
        self.rr_ratio: float = rr_ratio

    def calc_size(self, entry: float, stop: float) -> float:
        risk_amt: float = self.capital * self.risk_pct
        risk_per_unit: float = abs(entry - stop)
        return risk_amt / risk_per_unit if risk_per_unit > 0 else 0.0

    def calc_stop(
        self,
        direction: Direction,
        entry: float,
        df: pl.DataFrame,
        idx: int,
        swings: list[SwingPoint],
    ) -> float:
        return StopStrategy.calc_stop(direction, entry, df, idx, swings)

    def calc_tp(self, direction: Direction, entry: float, stop: float) -> float:
        risk: float = abs(entry - stop)
        reward: float = risk * self.rr_ratio
        return entry + reward if direction == "LONG" else entry - reward

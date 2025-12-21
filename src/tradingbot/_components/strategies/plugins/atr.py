import polars as pl

from tradingbot.types import Direction, SwingPoint


class ATRStopStrategy:
    """Stop loss based on Average True Range (ATR)."""

    def __init__(self, period: int = 14, multiplier: float = 2.0) -> None:
        self.period = period
        self.multiplier = multiplier

    @property
    def name(self) -> str:
        return "atr"

    def calc_stop(
        self,
        direction: Direction,
        entry: float,
        df: pl.DataFrame,
        idx: int,
        swings: list[SwingPoint],
    ) -> float:
        atr = self._calc_atr(df, idx)
        stop_distance = atr * self.multiplier

        if direction == "LONG":
            return entry - stop_distance
        else:
            return entry + stop_distance

    def _calc_atr(self, df: pl.DataFrame, idx: int) -> float:
        """Calculate Average True Range."""
        if idx < self.period:
            # Not enough data, use simple range
            subset = df.head(idx + 1)
            mean_val = (subset["high"] - subset["low"]).mean()
            return float(mean_val) if isinstance(mean_val, (int, float)) else 0.0

        # Get data for ATR calculation (slice: offset, length)
        start = idx - self.period + 1
        subset = df.slice(start, self.period)
        high = subset["high"]
        low = subset["low"]
        prev_close = df.slice(start - 1, self.period)["close"]

        # True Range = max(high-low, |high-prev_close|, |low-prev_close|)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()

        # Compute row-wise max via DataFrame
        true_range = (
            pl.DataFrame({"tr1": tr1, "tr2": tr2, "tr3": tr3})
            .select(pl.max_horizontal("tr1", "tr2", "tr3"))
            .to_series()
        )
        mean_val = true_range.mean()
        return float(mean_val) if isinstance(mean_val, (int, float)) else 0.0

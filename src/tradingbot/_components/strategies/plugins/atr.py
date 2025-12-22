import polars as pl

from tradingbot.types import Direction, SwingPoint


class ATRStopStrategy:
    """Stop/TP based on Average True Range (ATR)."""

    def __init__(self, period: int = 14, multiplier: float = 2.0) -> None:
        self.period = period
        self.multiplier = multiplier

    @property
    def name(self) -> str:
        return "atr"

    def calc(
        self,
        direction: Direction,
        entry: float,
        rr_ratio: float,
        bars: pl.DataFrame,
        swings: list[SwingPoint],
    ) -> tuple[float, float]:
        atr = self._calc_atr(bars)
        stop_distance = atr * self.multiplier
        tp_distance = stop_distance * rr_ratio

        if direction == "LONG":
            return entry - stop_distance, entry + tp_distance
        else:
            return entry + stop_distance, entry - tp_distance

    def _calc_atr(self, bars: pl.DataFrame) -> float:
        """Calculate Average True Range using the last `period` bars."""
        n = len(bars)
        if n < self.period:
            # Not enough data, use simple range
            mean_val = (bars["high"] - bars["low"]).mean()
            return float(mean_val) if isinstance(mean_val, (int, float)) else 0.0

        # Get data for ATR calculation (last `period` bars)
        subset = bars.tail(self.period)
        high = subset["high"]
        low = subset["low"]
        # Previous close needs period+1 bars, get it from the tail
        prev_close = bars.tail(self.period + 1).head(self.period)["close"]

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

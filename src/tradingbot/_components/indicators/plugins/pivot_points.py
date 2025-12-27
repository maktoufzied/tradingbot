"""Pivot Points indicator."""

import polars as pl

from tradingbot.types import Signal


class PivotPointsIndicator:
    """Pivot Points indicator.

    Classic floor trader pivots calculated from previous session:
    - PP (Pivot Point): (High + Low + Close) / 3
    - R1, R2, R3: Resistance levels above pivot
    - S1, S2, S3: Support levels below pivot

    Day traders use these as:
    - Pre-market support/resistance levels
    - Entry/exit targets
    - Trend bias (price above/below PP)
    """

    def __init__(self, lookback_bars: int = 78) -> None:
        # 78 bars = ~1 trading day for 5-min bars (6.5 hours)
        self._lookback_bars = lookback_bars

    @property
    def name(self) -> str:
        return "pivot_points"

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add Pivot Point columns to DataFrame."""
        n = len(df)
        pp_values: list[float | None] = []
        r1_values: list[float | None] = []
        r2_values: list[float | None] = []
        r3_values: list[float | None] = []
        s1_values: list[float | None] = []
        s2_values: list[float | None] = []
        s3_values: list[float | None] = []

        highs = df["high"].to_list()
        lows = df["low"].to_list()
        closes = df["close"].to_list()

        for i in range(n):
            if i < self._lookback_bars:
                pp_values.append(None)
                r1_values.append(None)
                r2_values.append(None)
                r3_values.append(None)
                s1_values.append(None)
                s2_values.append(None)
                s3_values.append(None)
                continue

            # Use previous session's high, low, close
            start_idx = max(0, i - self._lookback_bars)
            end_idx = i

            prev_high = max(highs[start_idx:end_idx])
            prev_low = min(lows[start_idx:end_idx])
            prev_close = closes[end_idx - 1]

            # Standard Pivot Point formula
            pp = (prev_high + prev_low + prev_close) / 3
            r1 = (2 * pp) - prev_low
            s1 = (2 * pp) - prev_high
            r2 = pp + (prev_high - prev_low)
            s2 = pp - (prev_high - prev_low)
            r3 = prev_high + 2 * (pp - prev_low)
            s3 = prev_low - 2 * (prev_high - pp)

            pp_values.append(pp)
            r1_values.append(r1)
            r2_values.append(r2)
            r3_values.append(r3)
            s1_values.append(s1)
            s2_values.append(s2)
            s3_values.append(s3)

        return df.with_columns(
            [
                pl.Series("pivot_pp", pp_values),
                pl.Series("pivot_r1", r1_values),
                pl.Series("pivot_r2", r2_values),
                pl.Series("pivot_r3", r3_values),
                pl.Series("pivot_s1", s1_values),
                pl.Series("pivot_s2", s2_values),
                pl.Series("pivot_s3", s3_values),
            ]
        )

    def get_signal(self, df: pl.DataFrame, idx: int) -> Signal | None:
        """Generate signal on pivot level touches."""
        if "pivot_pp" not in df.columns or idx < 1:
            return None

        close = df["close"][idx]
        prev_close = df["close"][idx - 1]
        s1 = df["pivot_s1"][idx]
        r1 = df["pivot_r1"][idx]

        if any(v is None for v in [close, prev_close, s1, r1]):
            return None

        # Price bounces off S1 = BUY
        if prev_close <= s1 and close > s1:
            return Signal.BUY

        # Price rejects from R1 = SELL
        if prev_close >= r1 and close < r1:
            return Signal.SELL

        return None

    def filter_signal(self, signal: Signal, df: pl.DataFrame, idx: int) -> bool:
        """Filter: confirm signals based on pivot position."""
        if "pivot_pp" not in df.columns:
            return True

        close = df["close"][idx]
        pp = df["pivot_pp"][idx]

        if close is None or pp is None:
            return True

        # For BUY, prefer price below pivot (more upside)
        if signal == Signal.BUY and close > pp:
            return True  # Still allow but less confident

        # For SELL, prefer price above pivot (more downside)
        return True

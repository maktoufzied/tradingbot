"""ADX (Average Directional Index) indicator."""

import polars as pl

from tradingbot.types import Signal


class ADXIndicator:
    """Average Directional Index indicator.

    ADX measures trend strength (not direction):
    - ADX > 25: Strong trend
    - ADX < 20: Weak trend / ranging
    - +DI > -DI: Bullish trend
    - -DI > +DI: Bearish trend

    Used to filter trades:
    - Take trend-following signals when ADX > 25
    - Take mean-reversion signals when ADX < 20
    """

    def __init__(
        self,
        period: int = 14,
        trend_threshold: float = 25.0,
    ) -> None:
        self._period = period
        self._trend_threshold = trend_threshold

    @property
    def name(self) -> str:
        return "adx"

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add ADX, +DI, -DI columns to DataFrame."""
        high = df["high"]
        low = df["low"]
        close = df["close"]

        # True Range
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pl.max_horizontal(tr1, tr2, tr3)

        # Directional Movement
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low

        # +DM and -DM
        plus_dm = pl.when((up_move > down_move) & (up_move > 0)).then(up_move).otherwise(0)
        minus_dm = pl.when((down_move > up_move) & (down_move > 0)).then(down_move).otherwise(0)

        # Smoothed TR, +DM, -DM using Wilder's smoothing (EMA with alpha = 1/period)
        atr = tr.ewm_mean(span=self._period, adjust=False)
        plus_dm_smooth = plus_dm.ewm_mean(span=self._period, adjust=False)
        minus_dm_smooth = minus_dm.ewm_mean(span=self._period, adjust=False)

        # +DI and -DI
        plus_di = (plus_dm_smooth / (atr + 1e-10)) * 100
        minus_di = (minus_dm_smooth / (atr + 1e-10)) * 100

        # DX and ADX
        di_diff = (plus_di - minus_di).abs()
        di_sum = plus_di + minus_di
        dx = (di_diff / (di_sum + 1e-10)) * 100
        adx = dx.ewm_mean(span=self._period, adjust=False)

        return df.with_columns(
            [
                adx.alias("adx"),
                plus_di.alias("adx_plus_di"),
                minus_di.alias("adx_minus_di"),
                atr.alias("atr"),
            ]
        )

    def get_signal(self, df: pl.DataFrame, idx: int) -> Signal | None:
        """Generate signal on DI crossover with strong trend."""
        if "adx" not in df.columns or idx < 1:
            return None

        adx = df["adx"][idx]
        plus_di_curr = df["adx_plus_di"][idx]
        plus_di_prev = df["adx_plus_di"][idx - 1]
        minus_di_curr = df["adx_minus_di"][idx]
        minus_di_prev = df["adx_minus_di"][idx - 1]

        if any(v is None for v in [adx, plus_di_curr, plus_di_prev, minus_di_curr, minus_di_prev]):
            return None

        # Only signal when trend is strong
        if adx < self._trend_threshold:
            return None

        # +DI crosses above -DI = BUY
        if plus_di_prev <= minus_di_prev and plus_di_curr > minus_di_curr:
            return Signal.BUY

        # -DI crosses above +DI = SELL
        if minus_di_prev <= plus_di_prev and minus_di_curr > plus_di_curr:
            return Signal.SELL

        return None

    def filter_signal(self, signal: Signal, df: pl.DataFrame, idx: int) -> bool:
        """Filter: require DI alignment with signal direction."""
        if "adx" not in df.columns:
            return True

        plus_di = df["adx_plus_di"][idx]
        minus_di = df["adx_minus_di"][idx]

        if plus_di is None or minus_di is None:
            return True

        # BUY requires +DI > -DI (bullish trend)
        if signal == Signal.BUY and plus_di < minus_di:
            return False

        # SELL requires -DI > +DI (bearish trend)
        return not (signal == Signal.SELL and minus_di < plus_di)

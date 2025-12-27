"""Fibonacci Retracement indicator."""

import polars as pl

from tradingbot.types import Signal


class FibonacciIndicator:
    """Fibonacci Retracement indicator.

    Calculates Fibonacci retracement levels from recent swing high/low:
    - 0.236 (23.6%): Shallow retracement
    - 0.382 (38.2%): Common retracement
    - 0.500 (50.0%): Half retracement
    - 0.618 (61.8%): Golden ratio
    - 0.786 (78.6%): Deep retracement

    Day traders use these for:
    - Pullback entry levels
    - Stop-loss placement
    - Take-profit targets
    """

    def __init__(
        self,
        lookback: int = 50,
        levels: tuple[float, ...] = (0.236, 0.382, 0.5, 0.618, 0.786),
    ) -> None:
        self._lookback = lookback
        self._levels = levels

    @property
    def name(self) -> str:
        return "fibonacci"

    def _find_swing_high_low(
        self, highs: list[float], lows: list[float], closes: list[float]
    ) -> tuple[float, float, bool]:
        """Find swing high and low, and determine trend direction."""
        swing_high = max(highs)
        swing_low = min(lows)
        high_idx = highs.index(swing_high)
        low_idx = lows.index(swing_low)

        # If high came before low, we're in a downtrend (retracing up)
        # If low came before high, we're in an uptrend (retracing down)
        is_uptrend = low_idx < high_idx

        return swing_high, swing_low, is_uptrend

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add Fibonacci level columns to DataFrame."""
        n = len(df)
        fib_high: list[float | None] = []
        fib_low: list[float | None] = []
        fib_trend: list[int | None] = []  # 1 for uptrend, -1 for downtrend
        fib_levels: dict[float, list[float | None]] = {level: [] for level in self._levels}

        highs = df["high"].to_list()
        lows = df["low"].to_list()
        closes = df["close"].to_list()

        for i in range(n):
            if i < self._lookback:
                fib_high.append(None)
                fib_low.append(None)
                fib_trend.append(None)
                for level in self._levels:
                    fib_levels[level].append(None)
                continue

            start_idx = i - self._lookback
            h_slice = highs[start_idx : i + 1]
            l_slice = lows[start_idx : i + 1]
            c_slice = closes[start_idx : i + 1]

            swing_high, swing_low, is_uptrend = self._find_swing_high_low(h_slice, l_slice, c_slice)
            fib_range = swing_high - swing_low

            fib_high.append(swing_high)
            fib_low.append(swing_low)
            fib_trend.append(1 if is_uptrend else -1)

            for level in self._levels:
                fib_price = swing_high - fib_range * level if is_uptrend else swing_low + fib_range * level
                fib_levels[level].append(fib_price)

        columns = [
            pl.Series("fib_high", fib_high),
            pl.Series("fib_low", fib_low),
            pl.Series("fib_trend", fib_trend),
        ]

        for level in self._levels:
            level_str = str(level).replace(".", "_")
            columns.append(pl.Series(f"fib_{level_str}", fib_levels[level]))

        return df.with_columns(columns)

    def get_signal(self, df: pl.DataFrame, idx: int) -> Signal | None:
        """Generate signal on Fibonacci level touches."""
        if "fib_trend" not in df.columns or idx < 1:
            return None

        close = df["close"][idx]
        prev_close = df["close"][idx - 1]
        trend = df["fib_trend"][idx]
        fib_382 = df.get_column("fib_0_382")[idx] if "fib_0_382" in df.columns else None
        fib_618 = df.get_column("fib_0_618")[idx] if "fib_0_618" in df.columns else None

        if any(v is None for v in [close, prev_close, trend, fib_382, fib_618]):
            return None

        # In uptrend, look for bounces off retracement levels (38.2% or 61.8%)
        if trend == 1 and ((prev_close <= fib_382 and close > fib_382) or (prev_close <= fib_618 and close > fib_618)):
            return Signal.BUY

        # In downtrend, look for rejections at retracement levels (38.2% or 61.8%)
        if trend == -1 and ((prev_close >= fib_382 and close < fib_382) or (prev_close >= fib_618 and close < fib_618)):
            return Signal.SELL

        return None

    def filter_signal(self, signal: Signal, df: pl.DataFrame, idx: int) -> bool:
        """Filter: require signal alignment with Fibonacci trend."""
        if "fib_trend" not in df.columns:
            return True

        trend = df["fib_trend"][idx]
        if trend is None:
            return True

        # BUY signals preferred in uptrend
        if signal == Signal.BUY and trend == -1:
            return False

        # SELL signals preferred in downtrend
        return not (signal == Signal.SELL and trend == 1)

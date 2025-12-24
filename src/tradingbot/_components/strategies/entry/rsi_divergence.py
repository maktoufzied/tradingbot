"""RSI Divergence entry strategy.

Trades divergences between price and RSI momentum indicator.

Win rate: 52-58% in trend exhaustion | Best RR: 1:1 to 1.5:1
Source: Wilder (1978)
Best for: End of trends, after extended moves
"""

import polars as pl

from tradingbot.types import Signal, SwingPoint

from ...swing import find_swing_points
from ..interfaces import Entry
from ..registry import register_entry


class RSIDivergenceStrategy:
    """Entry strategy based on RSI divergence detection."""

    @property
    def name(self) -> str:
        return "rsi_divergence"

    def __init__(
        self,
        rsi_period: int = 14,
        lookback_bars: int = 20,
        min_divergence_bars: int = 5,
    ) -> None:
        self._rsi_period = rsi_period
        self._lookback_bars = lookback_bars
        self._min_divergence_bars = min_divergence_bars

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute RSI indicator."""
        if "rsi" in df.columns:
            return df

        delta = df["close"].diff()
        gains = delta.clip(lower_bound=0)
        losses = (-delta).clip(lower_bound=0)

        avg_gain = gains.rolling_mean(window_size=self._rsi_period)
        avg_loss = losses.rolling_mean(window_size=self._rsi_period)

        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))

        return df.with_columns(rsi.alias("rsi"))

    def _find_rsi_swings(self, rsi_values: list[float | None], lookback: int = 3) -> list[tuple[int, float, bool]]:
        """Find swing highs and lows in RSI values."""
        swings: list[tuple[int, float, bool]] = []
        for i in range(lookback, len(rsi_values) - lookback):
            val = rsi_values[i]
            if val is None:
                continue

            # Use val which is guaranteed not None here
            is_high = all(
                val > (rsi_values[j] or 0)
                for j in range(i - lookback, i + lookback + 1)
                if j != i and rsi_values[j] is not None
            )
            is_low = all(
                val < (rsi_values[j] or 100)
                for j in range(i - lookback, i + lookback + 1)
                if j != i and rsi_values[j] is not None
            )

            if is_high:
                swings.append((i, val, True))
            elif is_low:
                swings.append((i, val, False))

        return swings

    def _detect_divergence(
        self,
        price_swings: list[SwingPoint],
        rsi_swings: list[tuple[int, float, bool]],
    ) -> tuple[str | None, dict[str, float]]:
        """Detect bullish or bearish divergence."""
        price_lows = [(s.index, s.price) for s in price_swings if not s.is_high][-3:]
        price_highs = [(s.index, s.price) for s in price_swings if s.is_high][-3:]
        rsi_lows = [(idx, val) for idx, val, is_high in rsi_swings if not is_high][-3:]
        rsi_highs = [(idx, val) for idx, val, is_high in rsi_swings if is_high][-3:]

        # Bullish divergence: price lower low, RSI higher low
        if len(price_lows) >= 2 and len(rsi_lows) >= 2:
            prev_price_low_idx, prev_price_low = price_lows[-2]
            curr_price_low_idx, curr_price_low = price_lows[-1]
            prev_rsi_low_idx, prev_rsi_low = rsi_lows[-2]
            curr_rsi_low_idx, curr_rsi_low = rsi_lows[-1]

            timing_ok = (
                abs(prev_rsi_low_idx - prev_price_low_idx) < 5 and abs(curr_rsi_low_idx - curr_price_low_idx) < 5
            )

            if (
                curr_price_low < prev_price_low
                and curr_rsi_low > prev_rsi_low
                and timing_ok
                and curr_price_low_idx > prev_price_low_idx + self._min_divergence_bars
            ):
                return "bullish", {
                    "prev_price_low": prev_price_low,
                    "curr_price_low": curr_price_low,
                    "prev_rsi_low": prev_rsi_low,
                    "curr_rsi_low": curr_rsi_low,
                }

        # Bearish divergence: price higher high, RSI lower high
        if len(price_highs) >= 2 and len(rsi_highs) >= 2:
            prev_price_high_idx, prev_price_high = price_highs[-2]
            curr_price_high_idx, curr_price_high = price_highs[-1]
            prev_rsi_high_idx, prev_rsi_high = rsi_highs[-2]
            curr_rsi_high_idx, curr_rsi_high = rsi_highs[-1]

            timing_ok = (
                abs(prev_rsi_high_idx - prev_price_high_idx) < 5 and abs(curr_rsi_high_idx - curr_price_high_idx) < 5
            )

            if (
                curr_price_high > prev_price_high
                and curr_rsi_high < prev_rsi_high
                and timing_ok
                and curr_price_high_idx > prev_price_high_idx + self._min_divergence_bars
            ):
                return "bearish", {
                    "prev_price_high": prev_price_high,
                    "curr_price_high": curr_price_high,
                    "prev_rsi_high": prev_rsi_high,
                    "curr_rsi_high": curr_rsi_high,
                }

        return None, {}

    def signal(self, df: pl.DataFrame, idx: int, has_position: bool) -> Entry:
        """Generate signal based on RSI divergence detection."""
        min_bars = self._rsi_period + self._lookback_bars + 10
        if idx < min_bars:
            return Entry(Signal.HOLD, "Insufficient data", {})

        hist = df.head(idx + 1)
        hist = self.compute(hist)

        close = float(hist["close"][-1])
        rsi = hist["rsi"][-1]

        if rsi is None:
            return Entry(Signal.HOLD, "RSI not available", {})

        details: dict[str, str | float] = {
            "price": round(close, 2),
            "rsi": round(float(rsi), 2),
        }

        if has_position:
            return Entry(Signal.HOLD, "Position open", details)

        price_swings = find_swing_points(hist, lookback=5)
        rsi_values = [hist["rsi"][i] for i in range(len(hist))]
        rsi_swings = self._find_rsi_swings(rsi_values, lookback=3)

        if len(price_swings) < 4 or len(rsi_swings) < 4:
            return Entry(Signal.HOLD, "Not enough swings", details)

        divergence_type, div_details = self._detect_divergence(price_swings, rsi_swings)

        if divergence_type == "bullish" and rsi < 50:
            return Entry(
                Signal.BUY,
                "Bullish RSI divergence",
                {**details, **{k: round(v, 2) for k, v in div_details.items()}},
            )

        if divergence_type == "bearish" and rsi > 50:
            return Entry(
                Signal.SELL,
                "Bearish RSI divergence",
                {**details, **{k: round(v, 2) for k, v in div_details.items()}},
            )

        return Entry(Signal.HOLD, "", details)


# Register on import
_strategy = RSIDivergenceStrategy()
register_entry(_strategy)

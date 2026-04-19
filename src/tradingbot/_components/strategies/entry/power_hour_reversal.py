"""Power Hour Reversal entry strategy.

Trades mean reversion during the final trading hour (3:00-4:00 PM ET) when
institutional rebalancing and end-of-day position squaring create reversals.

Win rate: 50-60% | Best RR: 1:1.5 to 1:2
Source: Institutional order flow patterns (Heston et al. 2010)
Best for: High-volume names (SPY, QQQ), last hour of regular session
"""

from datetime import UTC, datetime
from typing import Final
from zoneinfo import ZoneInfo

import polars as pl

from tradingbot.types import Signal, SwingPoint

from ...swing import find_swing_points
from ..interfaces import Entry
from ..registry import register_entry

# Power hour timing (US/Eastern)
# 3:00 PM ET = 15:00, 3:45 PM ET = 15:45 (no new entries after 15:45)
POWER_HOUR_START: Final = 15
POWER_HOUR_START_MINUTE: Final = 0
POWER_HOUR_END_MINUTE: Final = 45

# Eastern timezone (handles DST automatically)
ET_TZ: Final = ZoneInfo("America/New_York")


class PowerHourReversalStrategy:
    """Entry strategy exploiting mean reversion during power hour.

    Looks for:
    - Price extended from VWAP (above/below by threshold)
    - RSI in extreme territory with divergence
    - Volume confirmation (institutional participation)
    - Time within power hour window (3:00-3:45 PM ET)
    """

    @property
    def name(self) -> str:
        return "power_hour_reversal"

    def __init__(
        self,
        vwap_distance_pct: float = 0.003,
        rsi_period: int = 14,
        rsi_oversold: int = 35,
        rsi_overbought: int = 65,
        volume_multiplier: float = 1.5,
        volume_sma_period: int = 20,
        divergence_lookback: int = 10,
        min_divergence_bars: int = 3,
    ) -> None:
        self._vwap_distance_pct = vwap_distance_pct
        self._rsi_period = rsi_period
        self._rsi_oversold = rsi_oversold
        self._rsi_overbought = rsi_overbought
        self._volume_multiplier = volume_multiplier
        self._volume_sma_period = volume_sma_period
        self._divergence_lookback = divergence_lookback
        self._min_divergence_bars = min_divergence_bars

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute VWAP, RSI, and volume ratio indicators."""
        result = df

        # VWAP computation
        if "vwap" not in result.columns:
            typical_price = (result["high"] + result["low"] + result["close"]) / 3
            cum_vol = result["volume"].cum_sum()
            cum_tp_vol = (typical_price * result["volume"]).cum_sum()
            vwap = cum_tp_vol / cum_vol
            result = result.with_columns(vwap.alias("vwap"))

        # VWAP distance (as percentage)
        if "vwap_distance" not in result.columns:
            vwap_distance = (result["close"] - result["vwap"]) / result["vwap"]
            result = result.with_columns(vwap_distance.alias("vwap_distance"))

        # RSI computation
        if "rsi" not in result.columns:
            delta = result["close"].diff()
            gains = delta.clip(lower_bound=0)
            losses = (-delta).clip(lower_bound=0)
            avg_gain = gains.rolling_mean(window_size=self._rsi_period)
            avg_loss = losses.rolling_mean(window_size=self._rsi_period)
            rs = avg_gain / (avg_loss + 1e-10)
            rsi = 100 - (100 / (1 + rs))
            result = result.with_columns(rsi.alias("rsi"))

        # Volume ratio (current vs SMA)
        if "volume_ratio" not in result.columns:
            avg_volume = result["volume"].rolling_mean(window_size=self._volume_sma_period)
            volume_ratio = result["volume"] / (avg_volume + 1e-10)
            result = result.with_columns(volume_ratio.alias("volume_ratio"))

        return result

    def _to_et_time(self, dt: datetime | None) -> tuple[int, int]:
        """Convert datetime to Eastern Time (hour, minute).

        Handles both:
        - Timezone-aware datetimes (Yahoo Finance returns ET with tzinfo)
        - Naive UTC datetimes (YahooFeed converts to naive UTC)

        Uses zoneinfo for proper DST handling.
        """
        if dt is None or not hasattr(dt, "hour") or not hasattr(dt, "minute"):
            return (-1, -1)

        # Check if datetime is timezone-aware
        if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
            utc_offset = dt.utcoffset()
            if utc_offset is not None:
                offset_hours = utc_offset.total_seconds() / 3600
                # If offset is -5 or -4 (EST/EDT), it's already ET
                if offset_hours in (-5, -4):
                    return (dt.hour, dt.minute)
            # Convert from any timezone to ET
            et_dt = dt.astimezone(ET_TZ)
            return (et_dt.hour, et_dt.minute)

        # Naive datetime - assume UTC, convert to ET with DST handling
        utc_dt = dt.replace(tzinfo=UTC)
        et_dt = utc_dt.astimezone(ET_TZ)
        return (et_dt.hour, et_dt.minute)

    def _is_in_power_hour(self, dt: datetime | None) -> bool:
        """Check if datetime is within power hour entry window (3:00-3:45 PM ET)."""
        et_hour, et_minute = self._to_et_time(dt)
        if et_hour < 0:
            return False

        if et_hour != POWER_HOUR_START:
            return False

        return POWER_HOUR_START_MINUTE <= et_minute < POWER_HOUR_END_MINUTE

    def _find_rsi_swings(self, rsi_values: list[float | None], lookback: int = 3) -> list[tuple[int, float, bool]]:
        """Find swing highs and lows in RSI values."""
        swings: list[tuple[int, float, bool]] = []
        n = len(rsi_values)

        for i in range(lookback, n - lookback):
            val = rsi_values[i]
            if val is None:
                continue

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
        current_idx: int,
    ) -> tuple[str | None, dict[str, float]]:
        """Detect bullish or bearish RSI divergence.

        Bullish: Price makes lower low, RSI makes higher low
        Bearish: Price makes higher high, RSI makes lower high
        """
        # Filter to recent swings within lookback window
        min_idx = max(0, current_idx - self._divergence_lookback)

        price_lows = [(s.index, s.price) for s in price_swings if not s.is_high and s.index >= min_idx][-3:]
        price_highs = [(s.index, s.price) for s in price_swings if s.is_high and s.index >= min_idx][-3:]
        rsi_lows = [(idx, val) for idx, val, is_high in rsi_swings if not is_high and idx >= min_idx][-3:]
        rsi_highs = [(idx, val) for idx, val, is_high in rsi_swings if is_high and idx >= min_idx][-3:]

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

    def _is_bullish_candle(self, open_price: float, close: float, high: float, low: float) -> bool:
        """Check if candle is bullish with close in upper portion of range."""
        if close <= open_price:
            return False
        candle_range = high - low
        if candle_range == 0:
            return False
        close_position = (close - low) / candle_range
        return close_position >= 0.6  # Close in upper 40% of range

    def _is_bearish_candle(self, open_price: float, close: float, high: float, low: float) -> bool:
        """Check if candle is bearish with close in lower portion of range."""
        if close >= open_price:
            return False
        candle_range = high - low
        if candle_range == 0:
            return False
        close_position = (close - low) / candle_range
        return close_position <= 0.4  # Close in lower 40% of range

    def signal(self, df: pl.DataFrame, idx: int, has_position: bool) -> Entry:
        """Generate signal based on power hour reversal conditions."""
        min_bars = self._rsi_period + self._divergence_lookback + 10
        if idx < min_bars:
            return Entry(Signal.HOLD, "Insufficient data", {})

        hist = df.head(idx + 1)
        hist = self.compute(hist)

        current_bar = hist.row(-1, named=True)
        current_dt = current_bar.get("datetime")

        close = float(current_bar["close"])
        open_price = float(current_bar["open"])
        high = float(current_bar["high"])
        low = float(current_bar["low"])
        vwap = hist["vwap"][-1]
        vwap_distance = hist["vwap_distance"][-1]
        rsi = hist["rsi"][-1]
        volume_ratio = hist["volume_ratio"][-1]

        if vwap is None or rsi is None or vwap_distance is None:
            return Entry(Signal.HOLD, "Indicator calculation error", {})

        details: dict[str, str | float] = {
            "price": round(close, 2),
            "vwap": round(float(vwap), 2),
            "vwap_dist": round(float(vwap_distance) * 100, 3),
            "rsi": round(float(rsi), 1),
            "vol_ratio": round(float(volume_ratio), 2) if volume_ratio else 0,
        }

        if has_position:
            return Entry(Signal.HOLD, "Position open", details)

        # Check if in power hour window
        if current_dt is not None and not self._is_in_power_hour(current_dt):
            return Entry(Signal.HOLD, "Outside power hour", details)

        # Check volume confirmation
        if volume_ratio is None or volume_ratio < self._volume_multiplier:
            return Entry(Signal.HOLD, "Insufficient volume", details)

        # Find swing points for divergence detection
        price_swings = find_swing_points(hist, lookback=3)
        rsi_values = [hist["rsi"][i] for i in range(len(hist))]
        rsi_swings = self._find_rsi_swings(rsi_values, lookback=2)

        if len(price_swings) < 4 or len(rsi_swings) < 4:
            return Entry(Signal.HOLD, "Not enough swings", details)

        divergence_type, div_details = self._detect_divergence(price_swings, rsi_swings, idx)

        # LONG: Price below VWAP, RSI oversold, bullish divergence, bullish candle
        if (
            vwap_distance < -self._vwap_distance_pct
            and rsi < self._rsi_oversold
            and divergence_type == "bullish"
            and self._is_bullish_candle(open_price, close, high, low)
        ):
            return Entry(
                Signal.BUY,
                f"Power hour bullish reversal (RSI={rsi:.0f}, VWAP dist={vwap_distance * 100:.2f}%)",
                {**details, **{k: round(v, 2) for k, v in div_details.items()}},
            )

        # SHORT: Price above VWAP, RSI overbought, bearish divergence, bearish candle
        if (
            vwap_distance > self._vwap_distance_pct
            and rsi > self._rsi_overbought
            and divergence_type == "bearish"
            and self._is_bearish_candle(open_price, close, high, low)
        ):
            return Entry(
                Signal.SELL,
                f"Power hour bearish reversal (RSI={rsi:.0f}, VWAP dist={vwap_distance * 100:.2f}%)",
                {**details, **{k: round(v, 2) for k, v in div_details.items()}},
            )

        # Relaxed mode: Signal without divergence if other conditions are strong
        if (
            vwap_distance < -self._vwap_distance_pct * 1.5
            and rsi < self._rsi_oversold - 5
            and self._is_bullish_candle(open_price, close, high, low)
        ):
            return Entry(
                Signal.BUY,
                f"Power hour oversold bounce (RSI={rsi:.0f}, VWAP dist={vwap_distance * 100:.2f}%)",
                details,
            )

        if (
            vwap_distance > self._vwap_distance_pct * 1.5
            and rsi > self._rsi_overbought + 5
            and self._is_bearish_candle(open_price, close, high, low)
        ):
            return Entry(
                Signal.SELL,
                f"Power hour overbought fade (RSI={rsi:.0f}, VWAP dist={vwap_distance * 100:.2f}%)",
                details,
            )

        return Entry(Signal.HOLD, "", details)


class PowerHourReversalRelaxedStrategy(PowerHourReversalStrategy):
    """Power Hour Reversal with relaxed parameters for more signals."""

    @property
    def name(self) -> str:
        return "power_hour_reversal_relaxed"

    def __init__(self) -> None:
        super().__init__(
            vwap_distance_pct=0.002,  # 0.2% threshold
            rsi_oversold=40,
            rsi_overbought=60,
            volume_multiplier=1.2,
        )


# Register on import
_strategy = PowerHourReversalStrategy()
_strategy_relaxed = PowerHourReversalRelaxedStrategy()
register_entry(_strategy)
register_entry(_strategy_relaxed)

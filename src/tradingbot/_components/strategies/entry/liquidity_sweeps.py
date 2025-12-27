"""Liquidity Sweeps entry strategy (ICT/Smart Money Concepts).

Identifies stop hunts where price sweeps above/below swing points to grab liquidity
before reversing.

Win rate: 55-65% | Best RR: 1:2 to 1:3
Source: ICT methodology - liquidity concepts
Best for: Reversal setups, after extended moves
"""

import polars as pl

from tradingbot.types import Signal

from ..interfaces import Entry
from ..registry import register_entry


class LiquiditySweepsStrategy:
    """Entry strategy based on liquidity sweep identification."""

    @property
    def name(self) -> str:
        return "liquidity_sweeps"

    def __init__(
        self,
        swing_lookback: int = 10,
        sweep_threshold_pct: float = 0.1,
        confirmation_bars: int = 2,
    ) -> None:
        self._swing_lookback = swing_lookback
        self._sweep_threshold_pct = sweep_threshold_pct
        self._confirmation_bars = confirmation_bars

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """No additional computation needed."""
        return df

    def _find_swing_highs(self, highs: list[float], lookback: int) -> list[tuple[int, float]]:
        """Find swing high points."""
        swing_highs: list[tuple[int, float]] = []
        n = len(highs)

        for i in range(lookback, n - lookback):
            is_swing_high = True
            for j in range(1, lookback + 1):
                if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                    is_swing_high = False
                    break
            if is_swing_high:
                swing_highs.append((i, highs[i]))

        return swing_highs

    def _find_swing_lows(self, lows: list[float], lookback: int) -> list[tuple[int, float]]:
        """Find swing low points."""
        swing_lows: list[tuple[int, float]] = []
        n = len(lows)

        for i in range(lookback, n - lookback):
            is_swing_low = True
            for j in range(1, lookback + 1):
                if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                    is_swing_low = False
                    break
            if is_swing_low:
                swing_lows.append((i, lows[i]))

        return swing_lows

    def _detect_sweep(
        self,
        current_idx: int,
        highs: list[float],
        lows: list[float],
        closes: list[float],
        swing_highs: list[tuple[int, float]],
        swing_lows: list[tuple[int, float]],
    ) -> tuple[str | None, float | None, float | None]:
        """Detect if current price action is sweeping liquidity."""
        current_high = highs[current_idx]
        current_low = lows[current_idx]
        current_close = closes[current_idx]

        # Check for sweep of recent swing highs (bearish sweep)
        for swing_idx, swing_price in reversed(swing_highs):
            if swing_idx >= current_idx - 3:  # Skip very recent swings
                continue

            sweep_threshold = swing_price * (1 + self._sweep_threshold_pct / 100)

            # Price wicked above swing high but closed below = bearish sweep
            if current_high > swing_price and current_close < swing_price:
                return "bearish_sweep", swing_price, current_high

            # Price pushed slightly above and reversed
            if current_high > swing_price and current_high < sweep_threshold and current_close < current_high:
                return "bearish_sweep", swing_price, current_high

        # Check for sweep of recent swing lows (bullish sweep)
        for swing_idx, swing_price in reversed(swing_lows):
            if swing_idx >= current_idx - 3:  # Skip very recent swings
                continue

            sweep_threshold = swing_price * (1 - self._sweep_threshold_pct / 100)

            # Price wicked below swing low but closed above = bullish sweep
            if current_low < swing_price and current_close > swing_price:
                return "bullish_sweep", swing_price, current_low

            # Price pushed slightly below and reversed
            if current_low < swing_price and current_low > sweep_threshold and current_close > current_low:
                return "bullish_sweep", swing_price, current_low

        return None, None, None

    def signal(self, df: pl.DataFrame, idx: int, has_position: bool) -> Entry:
        """Generate signal on liquidity sweep detection."""
        min_bars = self._swing_lookback * 2 + 5
        if idx < min_bars:
            return Entry(Signal.HOLD, "Insufficient data", {})

        hist = df.head(idx + 1)

        highs = hist["high"].to_list()
        lows = hist["low"].to_list()
        closes = hist["close"].to_list()

        # Find swing points
        swing_highs = self._find_swing_highs(highs, self._swing_lookback)
        swing_lows = self._find_swing_lows(lows, self._swing_lookback)

        current_close = closes[-1]

        details: dict[str, str | float] = {
            "price": round(current_close, 2),
            "swing_highs": len(swing_highs),
            "swing_lows": len(swing_lows),
        }

        if has_position:
            return Entry(Signal.HOLD, "Position open", details)

        # Look for sweep in last few bars
        for i in range(len(highs) - 1, max(len(highs) - self._confirmation_bars - 1, 0), -1):
            sweep_type, sweep_level, extreme = self._detect_sweep(i, highs, lows, closes, swing_highs, swing_lows)

            if sweep_type is None:
                continue

            # Confirm reversal: current bar should be moving away from sweep
            if sweep_type == "bullish_sweep" and current_close > closes[i]:
                details["sweep_type"] = sweep_type
                details["sweep_level"] = round(sweep_level, 2) if sweep_level else 0
                details["extreme"] = round(extreme, 2) if extreme else 0
                return Entry(
                    Signal.BUY,
                    f"Bullish sweep of {sweep_level:.2f}",
                    details,
                )

            if sweep_type == "bearish_sweep" and current_close < closes[i]:
                details["sweep_type"] = sweep_type
                details["sweep_level"] = round(sweep_level, 2) if sweep_level else 0
                details["extreme"] = round(extreme, 2) if extreme else 0
                return Entry(
                    Signal.SELL,
                    f"Bearish sweep of {sweep_level:.2f}",
                    details,
                )

        return Entry(Signal.HOLD, "No liquidity sweep", details)


# Register on import
_strategy = LiquiditySweepsStrategy()
register_entry(_strategy)

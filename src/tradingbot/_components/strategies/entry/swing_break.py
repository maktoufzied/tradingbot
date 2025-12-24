"""Swing Break entry strategy.

Generates signals based on market structure analysis:
- Swing point detection (local highs/lows)
- Structure patterns (HH/HL/LH/LL)
- Breakout entries (trend reversal)
- Pullback entries (trend continuation)

Win rate: 45-55% | Best in trending markets
"""

import polars as pl

from tradingbot.types import Signal, Trend

from ...swing import analyze_structure, find_swing_points
from ..interfaces import Entry
from ..registry import register_entry


class SwingBreakStrategy:
    """Entry strategy based on swing point structure breaks."""

    @property
    def name(self) -> str:
        return "swing_break"

    def __init__(self, lookback: int = 5) -> None:
        self._lookback = lookback

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """No additional indicators required."""
        return df

    def signal(self, df: pl.DataFrame, idx: int, has_position: bool) -> Entry:
        """Generate signal based on market structure analysis."""
        if idx < self._lookback * 3:
            return Entry(Signal.HOLD, "Insufficient data", {})

        hist = df.head(idx + 1)
        swings = find_swing_points(hist, self._lookback)

        if len(swings) < 4:
            return Entry(Signal.HOLD, "Not enough swings", {})

        trend, analysis = analyze_structure(swings)
        bar = df.row(idx, named=True)
        price = float(bar["close"])

        details: dict[str, str | float] = {
            "trend": trend.value,
            "price": price,
            **analysis,
        }

        if has_position:
            return Entry(Signal.HOLD, "Position open", details)

        highs = [s for s in swings if s.is_high]
        lows = [s for s in swings if not s.is_high]

        # Structure break signals
        if trend == Trend.BEARISH and highs and price > highs[-1].price:
            return Entry(Signal.BUY, "Bullish structure break", details)

        if trend == Trend.BULLISH and lows and price < lows[-1].price:
            return Entry(Signal.SELL, "Bearish structure break", details)

        # Pullback/Rally signals
        if trend == Trend.BULLISH and len(lows) >= 2:
            last_low = lows[-1].price
            if bar["low"] <= last_low * 1.01 and bar["close"] > bar["open"]:
                return Entry(Signal.BUY, "Pullback to HL", details)

        if trend == Trend.BEARISH and len(highs) >= 2:
            last_high = highs[-1].price
            if bar["high"] >= last_high * 0.99 and bar["close"] < bar["open"]:
                return Entry(Signal.SELL, "Rally to LH", details)

        return Entry(Signal.HOLD, "", details)


# Register on import
_strategy = SwingBreakStrategy()
register_entry(_strategy)

"""Fair Value Gaps (FVG) entry strategy (ICT/Smart Money Concepts).

Identifies imbalance zones where price moved too fast, leaving gaps that tend to fill.

Win rate: 55-65% | Best RR: 1:1.5 to 1:2
Source: ICT methodology - market inefficiency zones
Best for: Trending markets, after impulsive moves
"""

import polars as pl

from tradingbot.types import Signal

from ..interfaces import Entry
from ..registry import register_entry


class FairValueGapsStrategy:
    """Entry strategy based on Fair Value Gap identification and fill."""

    @property
    def name(self) -> str:
        return "fvg"

    def __init__(
        self,
        min_gap_pct: float = 0.1,
        fvg_validity_bars: int = 30,
        require_fill: bool = True,
    ) -> None:
        self._min_gap_pct = min_gap_pct
        self._fvg_validity_bars = fvg_validity_bars
        self._require_fill = require_fill

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """No additional computation needed."""
        return df

    def _find_fvgs(
        self,
        highs: list[float],
        lows: list[float],
        closes: list[float],
    ) -> list[dict[str, float | str | int]]:
        """Find bullish and bearish Fair Value Gaps.

        FVG is a 3-candle pattern where:
        - Bullish FVG: candle 1's high < candle 3's low (gap up)
        - Bearish FVG: candle 1's low > candle 3's high (gap down)
        """
        fvgs: list[dict[str, float | str | int]] = []
        n = len(closes)

        for i in range(2, n):
            candle1_high = highs[i - 2]
            candle1_low = lows[i - 2]
            candle3_high = highs[i]
            candle3_low = lows[i]

            # Bullish FVG: gap between candle 1 high and candle 3 low
            if candle3_low > candle1_high:
                gap_size = candle3_low - candle1_high
                gap_pct = (gap_size / candle1_high) * 100
                if gap_pct >= self._min_gap_pct:
                    fvgs.append(
                        {
                            "type": "bullish",
                            "idx": i,
                            "top": candle3_low,
                            "bottom": candle1_high,
                            "size_pct": gap_pct,
                        }
                    )

            # Bearish FVG: gap between candle 3 high and candle 1 low
            if candle1_low > candle3_high:
                gap_size = candle1_low - candle3_high
                gap_pct = (gap_size / candle3_high) * 100
                if gap_pct >= self._min_gap_pct:
                    fvgs.append(
                        {
                            "type": "bearish",
                            "idx": i,
                            "top": candle1_low,
                            "bottom": candle3_high,
                            "size_pct": gap_pct,
                        }
                    )

        return fvgs

    def _is_fvg_filled(
        self,
        fvg: dict[str, float | str | int],
        highs: list[float],
        lows: list[float],
        fvg_idx: int,
    ) -> bool:
        """Check if FVG has been partially filled (mitigated)."""
        fvg_type = str(fvg["type"])
        fvg_top = float(fvg["top"])
        fvg_bottom = float(fvg["bottom"])
        midpoint = (fvg_top + fvg_bottom) / 2

        # Check bars after FVG formation
        for i in range(fvg_idx + 1, len(highs)):
            if fvg_type == "bullish":
                # Bullish FVG filled when price drops into gap
                if lows[i] <= midpoint:
                    return True
            else:
                # Bearish FVG filled when price rises into gap
                if highs[i] >= midpoint:
                    return True

        return False

    def signal(self, df: pl.DataFrame, idx: int, has_position: bool) -> Entry:
        """Generate signal when price enters unfilled FVG."""
        if idx < 10:
            return Entry(Signal.HOLD, "Insufficient data", {})

        hist = df.head(idx + 1)

        highs = hist["high"].to_list()
        lows = hist["low"].to_list()
        closes = hist["close"].to_list()

        # Find FVGs in recent history
        fvgs = self._find_fvgs(highs, lows, closes)

        current_close = closes[-1]
        current_high = highs[-1]
        current_low = lows[-1]

        details: dict[str, str | float] = {
            "price": round(current_close, 2),
            "fvg_count": len(fvgs),
        }

        if has_position:
            return Entry(Signal.HOLD, "Position open", details)

        # Check each FVG for potential entry
        for fvg in reversed(fvgs):  # Most recent first
            fvg_idx = int(fvg["idx"])
            bars_since = len(highs) - 1 - fvg_idx

            # Skip if FVG is too old or too recent
            if bars_since > self._fvg_validity_bars or bars_since < 2:
                continue

            fvg_type = str(fvg["type"])
            fvg_top = float(fvg["top"])
            fvg_bottom = float(fvg["bottom"])

            # Check if already filled
            if self._require_fill and self._is_fvg_filled(fvg, highs[:-1], lows[:-1], fvg_idx):
                continue

            if fvg_type == "bullish":
                # Price entering bullish FVG from above = BUY
                if current_low <= fvg_top and current_close >= fvg_bottom:
                    details["fvg_type"] = "bullish"
                    details["fvg_top"] = round(fvg_top, 2)
                    details["fvg_bottom"] = round(fvg_bottom, 2)
                    return Entry(
                        Signal.BUY,
                        f"Bullish FVG fill (gap: {fvg_bottom:.2f}-{fvg_top:.2f})",
                        details,
                    )

            elif fvg_type == "bearish" and current_high >= fvg_bottom and current_close <= fvg_top:
                # Price entering bearish FVG from below = SELL
                details["fvg_type"] = "bearish"
                details["fvg_top"] = round(fvg_top, 2)
                details["fvg_bottom"] = round(fvg_bottom, 2)
                return Entry(
                    Signal.SELL,
                    f"Bearish FVG fill (gap: {fvg_bottom:.2f}-{fvg_top:.2f})",
                    details,
                )

        return Entry(Signal.HOLD, "No FVG entry", details)


# Register on import
_strategy = FairValueGapsStrategy()
register_entry(_strategy)

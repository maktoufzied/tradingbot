"""Order Blocks entry strategy (ICT/Smart Money Concepts).

Identifies institutional order blocks - the last opposing candle before a significant move.

Win rate: 50-60% | Best RR: 1:2 to 1:3
Source: ICT (Inner Circle Trader) methodology
Best for: After liquidity sweeps, at key levels
"""

import polars as pl

from tradingbot.types import Signal

from ..interfaces import Entry
from ..registry import register_entry


class OrderBlocksStrategy:
    """Entry strategy based on order block identification."""

    @property
    def name(self) -> str:
        return "order_blocks"

    def __init__(
        self,
        lookback: int = 20,
        min_move_pct: float = 0.5,
        ob_validity_bars: int = 50,
    ) -> None:
        self._lookback = lookback
        self._min_move_pct = min_move_pct
        self._ob_validity_bars = ob_validity_bars

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """No additional computation needed."""
        return df

    def _find_order_blocks(
        self,
        opens: list[float],
        highs: list[float],
        lows: list[float],
        closes: list[float],
    ) -> list[dict[str, float | str | int]]:
        """Find bullish and bearish order blocks."""
        order_blocks: list[dict[str, float | str | int]] = []
        n = len(closes)

        for i in range(2, n - 2):
            # Check for significant move after this candle
            current_close = closes[i]
            future_high = max(highs[i + 1 : min(i + 5, n)])
            future_low = min(lows[i + 1 : min(i + 5, n)])

            move_up_pct = ((future_high - current_close) / current_close) * 100
            move_down_pct = ((current_close - future_low) / current_close) * 100

            is_bearish_candle = closes[i] < opens[i]
            is_bullish_candle = closes[i] > opens[i]

            # Bullish Order Block: Last bearish candle before big up move
            if is_bearish_candle and move_up_pct >= self._min_move_pct:
                order_blocks.append(
                    {
                        "type": "bullish",
                        "idx": i,
                        "high": highs[i],
                        "low": lows[i],
                        "open": opens[i],
                        "close": closes[i],
                    }
                )

            # Bearish Order Block: Last bullish candle before big down move
            if is_bullish_candle and move_down_pct >= self._min_move_pct:
                order_blocks.append(
                    {
                        "type": "bearish",
                        "idx": i,
                        "high": highs[i],
                        "low": lows[i],
                        "open": opens[i],
                        "close": closes[i],
                    }
                )

        return order_blocks

    def _is_price_in_ob(self, price: float, ob: dict[str, float | str | int], ob_type: str) -> bool:
        """Check if price is within order block zone."""
        ob_high = float(ob["high"])
        ob_low = float(ob["low"])

        if ob_type == "bullish":
            # For bullish OB, price should touch or enter the OB from above
            return ob_low <= price <= ob_high
        else:
            # For bearish OB, price should touch or enter the OB from below
            return ob_low <= price <= ob_high

    def signal(self, df: pl.DataFrame, idx: int, has_position: bool) -> Entry:
        """Generate signal when price returns to order block."""
        if idx < self._lookback + 5:
            return Entry(Signal.HOLD, "Insufficient data", {})

        hist = df.head(idx + 1)

        opens = hist["open"].to_list()
        highs = hist["high"].to_list()
        lows = hist["low"].to_list()
        closes = hist["close"].to_list()

        # Find order blocks in recent history
        start_idx = max(0, len(hist) - self._lookback - 10)
        ob_opens = opens[start_idx:]
        ob_highs = highs[start_idx:]
        ob_lows = lows[start_idx:]
        ob_closes = closes[start_idx:]

        order_blocks = self._find_order_blocks(ob_opens, ob_highs, ob_lows, ob_closes)

        current_close = closes[-1]
        current_low = lows[-1]
        current_high = highs[-1]

        details: dict[str, str | float] = {
            "price": round(current_close, 2),
            "ob_count": len(order_blocks),
        }

        if has_position:
            return Entry(Signal.HOLD, "Position open", details)

        # Check each order block for potential entry
        for ob in reversed(order_blocks):  # Most recent first
            ob_idx = int(ob["idx"])
            bars_since = len(ob_closes) - 1 - ob_idx

            # Skip if OB is too old
            if bars_since > self._ob_validity_bars:
                continue

            ob_type = str(ob["type"])
            ob_high = float(ob["high"])
            ob_low = float(ob["low"])

            if ob_type == "bullish":
                # Price returning to bullish OB = BUY opportunity
                if current_low <= ob_high and current_close > ob_low:
                    details["ob_type"] = "bullish"
                    details["ob_high"] = round(ob_high, 2)
                    details["ob_low"] = round(ob_low, 2)
                    return Entry(
                        Signal.BUY,
                        f"Bullish OB test (zone: {ob_low:.2f}-{ob_high:.2f})",
                        details,
                    )

            elif ob_type == "bearish" and current_high >= ob_low and current_close < ob_high:
                # Price returning to bearish OB = SELL opportunity
                details["ob_type"] = "bearish"
                details["ob_high"] = round(ob_high, 2)
                details["ob_low"] = round(ob_low, 2)
                return Entry(
                    Signal.SELL,
                    f"Bearish OB test (zone: {ob_low:.2f}-{ob_high:.2f})",
                    details,
                )

        return Entry(Signal.HOLD, "No OB test", details)


# Register on import
_strategy = OrderBlocksStrategy()
register_entry(_strategy)

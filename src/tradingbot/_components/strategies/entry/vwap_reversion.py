"""VWAP Mean Reversion entry strategy.

Trades reversion to Volume Weighted Average Price when price deviates significantly.

Win rate: 55-62% in ranging markets | Best RR: 1:1 to 1.2:1
Source: Berkowitz et al. (1988) - VWAP as institutional benchmark
"""

import polars as pl

from tradingbot.types import Signal

from ..interfaces import Entry
from ..registry import register_entry


class VWAPReversionStrategy:
    """Entry strategy based on VWAP deviation."""

    @property
    def name(self) -> str:
        return "vwap_reversion"

    def __init__(
        self,
        deviation_threshold: float = 1.5,
        min_volume_ratio: float = 0.8,
    ) -> None:
        self._deviation_threshold = deviation_threshold
        self._min_volume_ratio = min_volume_ratio

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute VWAP and standard deviation bands."""
        if "vwap" in df.columns:
            return df

        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        cum_vol = df["volume"].cum_sum()
        cum_tp_vol = (typical_price * df["volume"]).cum_sum()
        vwap = cum_tp_vol / cum_vol

        price_diff = df["close"] - vwap
        squared_diff = price_diff**2
        cum_sq_diff_vol = (squared_diff * df["volume"]).cum_sum()
        variance = cum_sq_diff_vol / cum_vol
        vwap_std = variance.sqrt()

        z_score = price_diff / (vwap_std + 1e-10)

        avg_volume = df["volume"].rolling_mean(window_size=20)
        volume_ratio = df["volume"] / (avg_volume + 1)

        return df.with_columns(
            [
                vwap.alias("vwap"),
                vwap_std.alias("vwap_std"),
                z_score.alias("vwap_zscore"),
                volume_ratio.alias("volume_ratio"),
            ]
        )

    def signal(self, df: pl.DataFrame, idx: int, has_position: bool) -> Entry:
        """Generate signal based on VWAP deviation."""
        if idx < 20:
            return Entry(Signal.HOLD, "Insufficient data", {})

        hist = df.head(idx + 1)
        if "vwap" not in hist.columns:
            hist = self.compute(hist)

        close = hist["close"][-1]
        vwap = hist["vwap"][-1]
        z_score = hist["vwap_zscore"][-1]
        volume_ratio = hist["volume_ratio"][-1]

        if vwap is None or z_score is None:
            return Entry(Signal.HOLD, "VWAP calculation error", {})

        details: dict[str, str | float] = {
            "price": round(float(close), 2),
            "vwap": round(float(vwap), 2),
            "z_score": round(float(z_score), 2),
            "volume_ratio": round(float(volume_ratio), 2) if volume_ratio else 0,
        }

        if has_position:
            return Entry(Signal.HOLD, "Position open", details)

        if volume_ratio is not None and volume_ratio < self._min_volume_ratio:
            return Entry(Signal.HOLD, "Low volume", details)

        # LONG: price significantly below VWAP (oversold)
        if z_score < -self._deviation_threshold:
            return Entry(Signal.BUY, f"VWAP oversold (z={z_score:.1f})", details)

        # SHORT: price significantly above VWAP (overbought)
        if z_score > self._deviation_threshold:
            return Entry(Signal.SELL, f"VWAP overbought (z={z_score:.1f})", details)

        return Entry(Signal.HOLD, "", details)


# Register on import
_strategy = VWAPReversionStrategy()
register_entry(_strategy)

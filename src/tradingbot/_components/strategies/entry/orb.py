"""Opening Range Breakout (ORB) entry strategy.

Trades breakouts from the opening range of the trading session.

Win rate: 55-60% | Best RR: 1:1
Source: Toby Crabel (1990s)
Best for: High volatility days, gap opens
"""

import polars as pl

from tradingbot.types import Signal

from ..interfaces import Entry
from ..registry import register_entry


class ORBStrategy:
    """Entry strategy based on opening range breakouts."""

    @property
    def name(self) -> str:
        return "orb"

    def __init__(
        self,
        opening_bars: int = 2,
        breakout_buffer: float = 0.001,
        volume_multiplier: float = 1.2,
    ) -> None:
        self._opening_bars = opening_bars
        self._breakout_buffer = breakout_buffer
        self._volume_multiplier = volume_multiplier
        self._session_range: dict[str, tuple[float, float]] = {}
        self._session_date: str | None = None

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute volume ratio."""
        if "volume_ratio" in df.columns:
            return df

        avg_volume = df["volume"].rolling_mean(window_size=20)
        volume_ratio = df["volume"] / (avg_volume + 1)

        return df.with_columns(
            [
                avg_volume.alias("avg_volume"),
                volume_ratio.alias("volume_ratio"),
            ]
        )

    def _get_session_date(self, dt: object) -> str:
        """Extract session date from datetime."""
        if hasattr(dt, "date"):
            return str(dt.date())
        return str(dt)[:10]

    def _calculate_opening_range(self, df: pl.DataFrame) -> tuple[float, float] | None:
        """Calculate opening range from first N bars."""
        if len(df) < self._opening_bars:
            return None

        opening_df = df.head(self._opening_bars)
        range_high_val = opening_df["high"].max()
        range_low_val = opening_df["low"].min()
        if range_high_val is None or range_low_val is None:
            return None
        return float(str(range_high_val)), float(str(range_low_val))

    def signal(self, df: pl.DataFrame, idx: int, has_position: bool) -> Entry:
        """Generate signal based on opening range breakout."""
        if idx < self._opening_bars + 5:
            return Entry(Signal.HOLD, "Building opening range", {})

        hist = df.head(idx + 1)
        if "volume_ratio" not in hist.columns:
            hist = self.compute(hist)

        current_bar = hist.row(-1, named=True)
        current_dt = current_bar["datetime"]
        session_date = self._get_session_date(current_dt)

        # Check if we need to recalculate opening range (new session)
        if self._session_date != session_date:
            self._session_date = session_date
            session_start_idx = 0
            for i in range(len(hist)):
                bar_date = self._get_session_date(hist["datetime"][i])
                if bar_date == session_date:
                    session_start_idx = i
                    break

            session_df = hist.slice(session_start_idx, len(hist) - session_start_idx)
            opening_range = self._calculate_opening_range(session_df)
            if opening_range:
                self._session_range[session_date] = opening_range

        opening_range = self._session_range.get(session_date)
        if not opening_range:
            return Entry(Signal.HOLD, "Opening range not defined", {})

        range_high, range_low = opening_range
        range_size = range_high - range_low
        close = float(current_bar["close"])
        volume_ratio = hist["volume_ratio"][-1] if "volume_ratio" in hist.columns else 1.0

        details: dict[str, str | float] = {
            "price": round(close, 2),
            "or_high": round(range_high, 2),
            "or_low": round(range_low, 2),
            "or_size": round(range_size, 2),
            "volume_ratio": round(float(volume_ratio), 2) if volume_ratio else 0,
        }

        if has_position:
            return Entry(Signal.HOLD, "Position open", details)

        breakout_high = range_high * (1 + self._breakout_buffer)
        breakout_low = range_low * (1 - self._breakout_buffer)
        has_volume = volume_ratio is not None and volume_ratio >= self._volume_multiplier

        if close > breakout_high and has_volume:
            return Entry(Signal.BUY, f"ORB breakout (range: {range_size:.2f})", details)

        if close < breakout_low and has_volume:
            return Entry(Signal.SELL, f"ORB breakdown (range: {range_size:.2f})", details)

        if close > breakout_high or close < breakout_low:
            return Entry(Signal.HOLD, "Breakout without volume", details)

        return Entry(Signal.HOLD, "", details)


# Register on import
_strategy = ORBStrategy()
register_entry(_strategy)

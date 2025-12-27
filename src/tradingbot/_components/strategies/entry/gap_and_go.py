"""Gap and Go entry strategy.

Trades opening gaps that continue in the gap direction with momentum.

Win rate: 55-65% on strong gaps | Best RR: 1:1.5
Source: Gap trading methodology
Best for: High volatility opens, news-driven gaps
"""

import polars as pl

from tradingbot.types import Signal

from ..interfaces import Entry
from ..registry import register_entry


class GapAndGoStrategy:
    """Entry strategy based on opening gaps with continuation."""

    @property
    def name(self) -> str:
        return "gap_and_go"

    def __init__(
        self,
        min_gap_pct: float = 0.5,
        volume_multiplier: float = 1.5,
        confirmation_bars: int = 2,
    ) -> None:
        self._min_gap_pct = min_gap_pct
        self._volume_multiplier = volume_multiplier
        self._confirmation_bars = confirmation_bars
        self._session_date: str | None = None
        self._gap_info: dict[str, dict[str, float | str]] = {}

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute gap and volume metrics."""
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

    def _detect_gap(self, prev_close: float, open_price: float) -> tuple[str, float]:
        """Detect gap type and size."""
        gap_pct = ((open_price - prev_close) / prev_close) * 100

        if gap_pct >= self._min_gap_pct:
            return "gap_up", gap_pct
        elif gap_pct <= -self._min_gap_pct:
            return "gap_down", gap_pct
        return "no_gap", gap_pct

    def signal(self, df: pl.DataFrame, idx: int, has_position: bool) -> Entry:
        """Generate signal based on gap and continuation."""
        if idx < 5:
            return Entry(Signal.HOLD, "Insufficient data", {})

        hist = df.head(idx + 1)
        if "volume_ratio" not in hist.columns:
            hist = self.compute(hist)

        current_bar = hist.row(-1, named=True)
        current_dt = current_bar["datetime"]
        session_date = self._get_session_date(current_dt)

        # Detect new session and gap
        if self._session_date != session_date:
            self._session_date = session_date

            # Find previous session's close
            prev_close = None
            for i in range(len(hist) - 1, -1, -1):
                bar_date = self._get_session_date(hist["datetime"][i])
                if bar_date != session_date:
                    prev_close = float(hist["close"][i])
                    break

            if prev_close is not None:
                # Find today's open
                for i in range(len(hist)):
                    bar_date = self._get_session_date(hist["datetime"][i])
                    if bar_date == session_date:
                        open_price = float(hist["open"][i])
                        gap_type, gap_pct = self._detect_gap(prev_close, open_price)
                        self._gap_info[session_date] = {
                            "type": gap_type,
                            "pct": gap_pct,
                            "prev_close": prev_close,
                            "open": open_price,
                        }
                        break

        gap_info = self._gap_info.get(session_date, {})
        if not gap_info or gap_info.get("type") == "no_gap":
            return Entry(Signal.HOLD, "No significant gap", {})

        close = float(current_bar["close"])
        open_price = float(gap_info.get("open", close))
        gap_type = str(gap_info.get("type", ""))
        gap_pct = float(gap_info.get("pct", 0))
        volume_ratio = hist["volume_ratio"][-1] if "volume_ratio" in hist.columns else 1.0

        details: dict[str, str | float] = {
            "price": round(close, 2),
            "gap_type": gap_type,
            "gap_pct": round(gap_pct, 2),
            "volume_ratio": round(float(volume_ratio), 2) if volume_ratio else 0,
        }

        if has_position:
            return Entry(Signal.HOLD, "Position open", details)

        # Check for continuation with volume
        has_volume = volume_ratio is not None and volume_ratio >= self._volume_multiplier

        if gap_type == "gap_up":
            # Gap up: price should be above open and making higher highs
            if close > open_price and has_volume:
                return Entry(Signal.BUY, f"Gap up continuation ({gap_pct:.1f}%)", details)

        elif gap_type == "gap_down" and close < open_price and has_volume:
            # Gap down: price should be below open and making lower lows
            return Entry(Signal.SELL, f"Gap down continuation ({gap_pct:.1f}%)", details)

        return Entry(Signal.HOLD, "Waiting for confirmation", details)


# Register on import
_strategy = GapAndGoStrategy()
register_entry(_strategy)

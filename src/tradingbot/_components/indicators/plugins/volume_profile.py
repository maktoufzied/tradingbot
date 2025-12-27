"""Volume Profile indicator."""

import polars as pl

from tradingbot.types import Signal


class VolumeProfileIndicator:
    """Volume Profile indicator.

    Volume Profile shows volume distribution across price levels:
    - POC (Point of Control): Price with highest volume
    - VAH (Value Area High): Upper bound of 70% volume
    - VAL (Value Area Low): Lower bound of 70% volume

    Day traders use these as:
    - Strong support/resistance levels
    - Targets for mean reversion
    - Breakout confirmation zones
    """

    def __init__(
        self,
        num_bins: int = 50,
        value_area_pct: float = 0.70,
        lookback: int = 100,
    ) -> None:
        self._num_bins = num_bins
        self._value_area_pct = value_area_pct
        self._lookback = lookback

    @property
    def name(self) -> str:
        return "volume_profile"

    def _calculate_profile(
        self, highs: list[float], lows: list[float], closes: list[float], volumes: list[float]
    ) -> tuple[float, float, float]:
        """Calculate POC, VAH, VAL from price/volume data."""
        if not highs or not volumes:
            return 0.0, 0.0, 0.0

        price_min = min(lows)
        price_max = max(highs)
        price_range = price_max - price_min

        if price_range <= 0:
            return closes[-1] if closes else 0.0, price_max, price_min

        bin_size = price_range / self._num_bins
        volume_at_price: dict[int, float] = {}

        for high, low, vol in zip(highs, lows, volumes, strict=True):
            low_bin = int((low - price_min) / bin_size)
            high_bin = int((high - price_min) / bin_size)
            high_bin = min(high_bin, self._num_bins - 1)

            bins_touched = high_bin - low_bin + 1
            vol_per_bin = vol / bins_touched if bins_touched > 0 else vol

            for b in range(low_bin, high_bin + 1):
                volume_at_price[b] = volume_at_price.get(b, 0) + vol_per_bin

        if not volume_at_price:
            return closes[-1] if closes else 0.0, price_max, price_min

        # POC: bin with highest volume
        poc_bin = max(volume_at_price, key=lambda x: volume_at_price[x])
        poc = price_min + (poc_bin + 0.5) * bin_size

        # Value Area: 70% of volume centered around POC
        total_vol = sum(volume_at_price.values())
        target_vol = total_vol * self._value_area_pct

        sorted_bins = sorted(volume_at_price.keys(), key=lambda x: abs(x - poc_bin))
        accumulated_vol = 0.0
        included_bins: list[int] = []

        for b in sorted_bins:
            included_bins.append(b)
            accumulated_vol += volume_at_price[b]
            if accumulated_vol >= target_vol:
                break

        val_bin = min(included_bins)
        vah_bin = max(included_bins)

        val = price_min + val_bin * bin_size
        vah = price_min + (vah_bin + 1) * bin_size

        return poc, vah, val

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add Volume Profile columns to DataFrame."""
        n = len(df)
        poc_values: list[float | None] = []
        vah_values: list[float | None] = []
        val_values: list[float | None] = []

        highs = df["high"].to_list()
        lows = df["low"].to_list()
        closes = df["close"].to_list()
        volumes = df["volume"].to_list()

        for i in range(n):
            if i < self._lookback:
                poc_values.append(None)
                vah_values.append(None)
                val_values.append(None)
                continue

            start_idx = max(0, i - self._lookback)
            h_slice = highs[start_idx : i + 1]
            l_slice = lows[start_idx : i + 1]
            c_slice = closes[start_idx : i + 1]
            v_slice = volumes[start_idx : i + 1]

            poc, vah, val = self._calculate_profile(h_slice, l_slice, c_slice, v_slice)
            poc_values.append(poc)
            vah_values.append(vah)
            val_values.append(val)

        return df.with_columns(
            [
                pl.Series("vp_poc", poc_values),
                pl.Series("vp_vah", vah_values),
                pl.Series("vp_val", val_values),
            ]
        )

    def get_signal(self, df: pl.DataFrame, idx: int) -> Signal | None:
        """Generate signal on Volume Profile level touches."""
        if "vp_poc" not in df.columns or idx < 1:
            return None

        close = df["close"][idx]
        prev_close = df["close"][idx - 1]
        val = df["vp_val"][idx]
        vah = df["vp_vah"][idx]

        if any(v is None for v in [close, prev_close, val, vah]):
            return None

        # Price bounces off VAL = BUY
        if prev_close <= val and close > val:
            return Signal.BUY

        # Price rejects from VAH = SELL
        if prev_close >= vah and close < vah:
            return Signal.SELL

        return None

    def filter_signal(self, signal: Signal, df: pl.DataFrame, idx: int) -> bool:
        """Filter: confirm signals near volume profile levels."""
        if "vp_poc" not in df.columns:
            return True

        close = df["close"][idx]
        poc = df["vp_poc"][idx]
        val = df["vp_val"][idx]
        vah = df["vp_vah"][idx]

        if any(v is None for v in [close, poc, val, vah]):
            return True

        # For BUY, price should be below POC
        if signal == Signal.BUY and close > poc:
            return False

        # For SELL, price should be above POC
        return not (signal == Signal.SELL and close < poc)

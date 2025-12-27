"""VWAP Bands indicator."""

import polars as pl

from tradingbot.types import Signal


class VWAPBandsIndicator:
    """VWAP with Standard Deviation Bands indicator.

    VWAP Bands provide dynamic support/resistance levels:
    - VWAP: Volume-weighted average price (institutional benchmark)
    - Upper bands (+1σ, +2σ): Resistance levels
    - Lower bands (-1σ, -2σ): Support levels

    Day traders use these for:
    - Mean reversion entries at bands
    - Trend confirmation (price above/below VWAP)
    - Take-profit targets
    """

    def __init__(
        self,
        band_multipliers: tuple[float, float] = (1.0, 2.0),
    ) -> None:
        self._band_multipliers = band_multipliers

    @property
    def name(self) -> str:
        return "vwap_bands"

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add VWAP and band columns to DataFrame."""
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        cum_vol = df["volume"].cum_sum()
        cum_tp_vol = (typical_price * df["volume"]).cum_sum()
        vwap = cum_tp_vol / cum_vol

        # Standard deviation of price from VWAP
        price_diff = df["close"] - vwap
        squared_diff = price_diff**2
        cum_sq_diff_vol = (squared_diff * df["volume"]).cum_sum()
        variance = cum_sq_diff_vol / cum_vol
        vwap_std = variance.sqrt()

        columns = [
            vwap.alias("vwap"),
            vwap_std.alias("vwap_std"),
        ]

        # Add bands at each multiplier level
        for mult in self._band_multipliers:
            upper = vwap + (vwap_std * mult)
            lower = vwap - (vwap_std * mult)
            mult_str = str(mult).replace(".", "_")
            columns.extend(
                [
                    upper.alias(f"vwap_upper_{mult_str}"),
                    lower.alias(f"vwap_lower_{mult_str}"),
                ]
            )

        return df.with_columns(columns)

    def get_signal(self, df: pl.DataFrame, idx: int) -> Signal | None:
        """Generate signal on VWAP band touches."""
        if "vwap" not in df.columns or idx < 1:
            return None

        close = df["close"][idx]
        vwap = df["vwap"][idx]
        lower_1 = df.get_column("vwap_lower_1_0")[idx] if "vwap_lower_1_0" in df.columns else None
        upper_1 = df.get_column("vwap_upper_1_0")[idx] if "vwap_upper_1_0" in df.columns else None

        if any(v is None for v in [close, vwap, lower_1, upper_1]):
            return None

        prev_close = df["close"][idx - 1]

        # Price bounces off lower band = BUY
        if prev_close <= lower_1 and close > lower_1:
            return Signal.BUY

        # Price rejects from upper band = SELL
        if prev_close >= upper_1 and close < upper_1:
            return Signal.SELL

        return None

    def filter_signal(self, signal: Signal, df: pl.DataFrame, idx: int) -> bool:
        """Filter: allow signals only near VWAP bands."""
        if "vwap" not in df.columns:
            return True

        close = df["close"][idx]
        vwap = df["vwap"][idx]

        if close is None or vwap is None:
            return True

        # Calculate distance from VWAP as percentage
        distance = abs(close - vwap) / vwap * 100

        # Block signals if price is too close to VWAP (within 0.3%)
        return bool(distance > 0.3)

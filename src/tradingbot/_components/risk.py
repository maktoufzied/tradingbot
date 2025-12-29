"""Position sizing with optional volatility adjustment."""

from typing import Final

import polars as pl

# Default ATR period for volatility measurement
ATR_PERIOD: Final[int] = 14
# Baseline period for comparing current vs historical volatility
BASELINE_PERIOD: Final[int] = 50
# Minimum scaling factor (never reduce size below this fraction)
MIN_SCALE_FACTOR: Final[float] = 0.25
# Maximum scaling factor (cap size increase in low volatility)
MAX_SCALE_FACTOR: Final[float] = 1.5


def compute_atr(df: pl.DataFrame, period: int = ATR_PERIOD) -> float | None:
    """Compute current ATR value from OHLC data.

    Args:
        df: DataFrame with high, low, close columns
        period: ATR smoothing period

    Returns:
        Current ATR value, or None if insufficient data
    """
    if len(df) < period + 1:
        return None

    result = df.select(
        pl.max_horizontal(
            pl.col("high") - pl.col("low"),
            (pl.col("high") - pl.col("close").shift(1)).abs(),
            (pl.col("low") - pl.col("close").shift(1)).abs(),
        )
        .rolling_mean(window_size=period)
        .alias("atr")
    )

    atr_val = result["atr"][-1]
    return float(atr_val) if atr_val is not None else None


def compute_baseline_atr(df: pl.DataFrame, period: int = BASELINE_PERIOD) -> float | None:
    """Compute longer-term baseline ATR for volatility comparison.

    Args:
        df: DataFrame with high, low, close columns
        period: Baseline ATR period (longer than standard ATR)

    Returns:
        Baseline ATR value, or None if insufficient data
    """
    return compute_atr(df, period)


class PositionSizer:
    """Calculates position size based on risk percentage and tracks capital.

    Supports optional ATR-based volatility adjustment:
    - When use_atr_sizing=True, position size scales inversely with volatility
    - High volatility (ATR > baseline) = smaller positions
    - Low volatility (ATR < baseline) = larger positions (capped)
    """

    def __init__(
        self,
        capital: float,
        risk_pct: float = 0.01,
        use_atr_sizing: bool = False,
    ):
        self.initial: float = capital
        self.capital: float = capital
        self.risk_pct: float = risk_pct
        self.use_atr_sizing: bool = use_atr_sizing

    def calc_size(
        self,
        entry: float,
        stop: float,
        df: pl.DataFrame | None = None,
    ) -> float:
        """Calculate position size based on risk amount and stop distance.

        Args:
            entry: Entry price
            stop: Stop-loss price
            df: Optional DataFrame for ATR calculation (required if use_atr_sizing=True)

        Returns:
            Whole shares (rounded down) since most brokers don't support
            fractional shares for all order types.
        """
        risk_amt: float = self.capital * self.risk_pct
        risk_per_unit: float = abs(entry - stop)
        base_size = risk_amt / risk_per_unit if risk_per_unit > 0 else 0.0

        # Apply ATR-based scaling if enabled and data available
        if self.use_atr_sizing and df is not None:
            scale = self._calc_volatility_scale(df)
            base_size *= scale

        return float(int(base_size))  # Round down to whole shares

    def _calc_volatility_scale(self, df: pl.DataFrame) -> float:
        """Calculate position size scaling factor based on volatility.

        Returns:
            Scale factor: <1 when volatility is high, >1 when low (capped)
        """
        current_atr = compute_atr(df, ATR_PERIOD)
        baseline_atr = compute_baseline_atr(df, BASELINE_PERIOD)

        if current_atr is None or baseline_atr is None or current_atr <= 0:
            return 1.0  # No adjustment if ATR unavailable

        # Scale inversely with volatility relative to baseline
        # High volatility = smaller position, low volatility = larger (capped)
        scale = baseline_atr / current_atr

        # Clamp to reasonable bounds
        return max(MIN_SCALE_FACTOR, min(scale, MAX_SCALE_FACTOR))

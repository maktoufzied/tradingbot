class PositionSizer:
    """Calculates position size based on risk percentage and tracks capital."""

    def __init__(
        self,
        capital: float,
        risk_pct: float = 0.01,
    ):
        self.initial: float = capital
        self.capital: float = capital
        self.risk_pct: float = risk_pct

    def calc_size(self, entry: float, stop: float) -> float:
        """Calculate position size based on risk amount and stop distance.

        Returns whole shares (rounded down) since most brokers don't support
        fractional shares for all order types.
        """
        risk_amt: float = self.capital * self.risk_pct
        risk_per_unit: float = abs(entry - stop)
        size = risk_amt / risk_per_unit if risk_per_unit > 0 else 0.0
        return float(int(size))  # Round down to whole shares

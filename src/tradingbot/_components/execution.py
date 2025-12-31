"""Execution cost modeling for realistic backtesting.

Models real-world trading costs:
- Bid-ask spread: Cost of crossing the spread
- Slippage: Price movement between signal and fill
- Commission: Broker fees per share

Without cost modeling, backtests overestimate returns by 10-30%.
"""

from dataclasses import dataclass
from typing import Final

from tradingbot.types import Direction

# Default costs: zero (configure in tradingbot.toml if needed)
DEFAULT_SPREAD_BPS: Final = 0.0
DEFAULT_SLIPPAGE_BPS: Final = 0.0
DEFAULT_COMMISSION_PER_SHARE: Final = 0.0


@dataclass(frozen=True)
class ExecutionCosts:
    """Breakdown of execution costs for a single trade."""

    spread_cost: float  # Cost from bid-ask spread
    slippage_cost: float  # Cost from price movement
    commission: float  # Broker commission
    total: float  # Total execution cost


@dataclass
class ExecutionModel:
    """Models realistic execution costs for backtesting.

    Costs are applied symmetrically:
    - Entry: Pay spread + slippage (worse fill than signal price)
    - Exit: Pay spread + slippage (worse fill than signal price)
    - Commission: Charged on both entry and exit

    Example:
        For a LONG trade with $100 signal, 5 bps spread, 5 bps slippage:
        - Entry fill: $100 * (1 + 0.0005 + 0.0005) = $100.10
        - Exit fill at $102 signal: $102 * (1 - 0.0005 - 0.0005) = $101.90
        - Without costs: P&L = ($102 - $100) * shares
        - With costs: P&L = ($101.90 - $100.10) * shares - commission
    """

    spread_bps: float = DEFAULT_SPREAD_BPS
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS
    commission_per_share: float = DEFAULT_COMMISSION_PER_SHARE

    def __post_init__(self) -> None:
        # Convert basis points to decimal
        self._spread_pct = self.spread_bps / 10000
        self._slippage_pct = self.slippage_bps / 10000

    @classmethod
    def zero(cls) -> ExecutionModel:
        """Create model with zero costs (for comparison)."""
        return cls(spread_bps=0, slippage_bps=0, commission_per_share=0)

    @classmethod
    def conservative(cls) -> ExecutionModel:
        """Create model with conservative (higher) cost estimates."""
        return cls(spread_bps=5.0, slippage_bps=10.0, commission_per_share=0.01)

    def get_entry_price(self, signal_price: float, direction: Direction) -> float:
        """Calculate realistic entry price after costs.

        For LONG: Buy at ask (higher) + slippage
        For SHORT: Sell at bid (lower) - slippage
        """
        cost_pct = self._spread_pct / 2 + self._slippage_pct

        if direction == "LONG":
            return signal_price * (1 + cost_pct)
        else:
            return signal_price * (1 - cost_pct)

    def get_exit_price(self, signal_price: float, direction: Direction) -> float:
        """Calculate realistic exit price after costs.

        For LONG: Sell at bid (lower) - slippage
        For SHORT: Buy at ask (higher) + slippage
        """
        cost_pct = self._spread_pct / 2 + self._slippage_pct

        if direction == "LONG":
            return signal_price * (1 - cost_pct)
        else:
            return signal_price * (1 + cost_pct)

    def calculate_commission(self, shares: float) -> float:
        """Calculate round-trip commission (entry + exit)."""
        return abs(shares) * self.commission_per_share * 2

    def calculate_costs(
        self,
        entry_signal: float,
        exit_signal: float,
        shares: float,
        direction: Direction,
    ) -> ExecutionCosts:
        """Calculate detailed execution costs for a completed trade.

        Returns breakdown of spread, slippage, and commission costs.
        """
        shares = abs(shares)

        # Entry costs
        entry_actual = self.get_entry_price(entry_signal, direction)
        entry_spread = (
            abs(entry_actual - entry_signal) * self._spread_pct / (self._spread_pct + self._slippage_pct + 1e-10)
        )
        entry_slip = abs(entry_actual - entry_signal) - entry_spread

        # Exit costs
        exit_actual = self.get_exit_price(exit_signal, direction)
        exit_spread = (
            abs(exit_actual - exit_signal) * self._spread_pct / (self._spread_pct + self._slippage_pct + 1e-10)
        )
        exit_slip = abs(exit_actual - exit_signal) - exit_spread

        spread_cost = (entry_spread + exit_spread) * shares
        slippage_cost = (entry_slip + exit_slip) * shares
        commission = self.calculate_commission(shares)

        return ExecutionCosts(
            spread_cost=spread_cost,
            slippage_cost=slippage_cost,
            commission=commission,
            total=spread_cost + slippage_cost + commission,
        )

    def calculate_net_pnl(
        self,
        entry_signal: float,
        exit_signal: float,
        shares: float,
        direction: Direction,
    ) -> tuple[float, float]:
        """Calculate gross and net P&L for a trade.

        Returns:
            Tuple of (gross_pnl, net_pnl)
            - gross_pnl: P&L assuming perfect execution
            - net_pnl: P&L after all execution costs
        """
        # Gross P&L (no costs)
        if direction == "LONG":
            gross_pnl = (exit_signal - entry_signal) * shares
        else:
            gross_pnl = (entry_signal - exit_signal) * shares

        # Net P&L (with costs)
        entry_actual = self.get_entry_price(entry_signal, direction)
        exit_actual = self.get_exit_price(exit_signal, direction)
        commission = self.calculate_commission(shares)

        if direction == "LONG":
            net_pnl = (exit_actual - entry_actual) * shares - commission
        else:
            net_pnl = (entry_actual - exit_actual) * shares - commission

        return gross_pnl, net_pnl

    def would_be_profitable(
        self,
        entry_signal: float,
        exit_signal: float,
        shares: float,
        direction: Direction,
    ) -> bool:
        """Check if a trade would be profitable after costs.

        Useful for filtering out trades that appear profitable
        but would actually lose money after execution costs.
        """
        _, net_pnl = self.calculate_net_pnl(entry_signal, exit_signal, shares, direction)
        return net_pnl > 0

    def minimum_profit_target(
        self,
        entry_price: float,
        shares: float,
        direction: Direction,
    ) -> float:
        """Calculate minimum price move needed to break even after costs.

        Returns the minimum exit price (for LONG) or maximum exit price (for SHORT)
        needed to cover all execution costs.
        """
        # Total cost percentage (entry + exit spread/slippage + commission)
        cost_pct = (self._spread_pct + self._slippage_pct) * 2
        commission_pct = self.calculate_commission(shares) / (entry_price * shares)

        total_cost_pct = cost_pct + commission_pct

        if direction == "LONG":
            return entry_price * (1 + total_cost_pct)
        else:
            return entry_price * (1 - total_cost_pct)

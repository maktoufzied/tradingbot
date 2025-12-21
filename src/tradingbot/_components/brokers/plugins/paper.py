"""Paper trading broker - simulates order execution without real money."""

import uuid
from dataclasses import dataclass

from tradingbot.interfaces import BrokerProtocol
from tradingbot.types import AccountInfo, BrokerPosition, Direction, Order, OrderResult


@dataclass
class _SimulatedPosition:
    """Internal position tracking."""

    symbol: str
    direction: Direction
    size: float
    avg_entry_price: float


class PaperBroker(BrokerProtocol):
    """Simulated broker for paper trading."""

    def __init__(self, initial_capital: float = 100000) -> None:
        self._initial_capital: float = initial_capital
        self._cash: float = initial_capital
        self._positions: dict[str, _SimulatedPosition] = {}
        self._last_prices: dict[str, float] = {}

    @property
    def name(self) -> str:
        return "paper"

    def set_price(self, symbol: str, price: float) -> None:
        """Update the current price for a symbol (called by live engine)."""
        self._last_prices[symbol] = price

    def submit_order(self, order: Order) -> OrderResult:
        """Execute order immediately at current price (simulated)."""
        price = self._last_prices.get(order.symbol)
        if price is None:
            return OrderResult(
                order_id="",
                status="REJECTED",
                filled_price=None,
                filled_size=0,
                message=f"No price available for {order.symbol}",
            )

        order_id = str(uuid.uuid4())[:8]
        cost = price * order.size

        # Check buying power for long positions
        if order.direction == "LONG" and cost > self._cash:
            return OrderResult(
                order_id=order_id,
                status="REJECTED",
                filled_price=None,
                filled_size=0,
                message="Insufficient buying power",
            )

        # Execute the order
        existing = self._positions.get(order.symbol)

        if existing is None:
            # Open new position
            self._positions[order.symbol] = _SimulatedPosition(
                symbol=order.symbol,
                direction=order.direction,
                size=order.size,
                avg_entry_price=price,
            )
            if order.direction == "LONG":
                self._cash -= cost
        elif existing.direction == order.direction:
            # Add to position
            total_size = existing.size + order.size
            existing.avg_entry_price = ((existing.avg_entry_price * existing.size) + (price * order.size)) / total_size
            existing.size = total_size
            if order.direction == "LONG":
                self._cash -= cost
        else:
            # Reduce or close position
            if order.size >= existing.size:
                # Close position
                pnl = self._calc_pnl(existing, price)
                self._cash += (existing.size * price) + pnl if existing.direction == "LONG" else pnl
                del self._positions[order.symbol]

                # Open opposite position if size exceeds
                remaining = order.size - existing.size
                if remaining > 0:
                    self._positions[order.symbol] = _SimulatedPosition(
                        symbol=order.symbol,
                        direction=order.direction,
                        size=remaining,
                        avg_entry_price=price,
                    )
                    if order.direction == "LONG":
                        self._cash -= remaining * price
            else:
                # Partial close
                existing.size -= order.size
                pnl = self._calc_pnl_for_size(existing, price, order.size)
                if existing.direction == "LONG":
                    self._cash += order.size * price

        return OrderResult(
            order_id=order_id,
            status="FILLED",
            filled_price=price,
            filled_size=order.size,
        )

    def cancel_order(self, order_id: str) -> bool:
        """Paper broker executes immediately, so nothing to cancel."""
        return False

    def get_position(self, symbol: str) -> BrokerPosition | None:
        """Get position for a symbol."""
        pos = self._positions.get(symbol)
        if pos is None:
            return None

        price = self._last_prices.get(symbol, pos.avg_entry_price)
        return BrokerPosition(
            symbol=pos.symbol,
            direction=pos.direction,
            size=pos.size,
            avg_entry_price=pos.avg_entry_price,
            market_value=pos.size * price,
            unrealized_pnl=self._calc_pnl(pos, price),
        )

    def get_positions(self) -> list[BrokerPosition]:
        """Get all positions."""
        positions = [self.get_position(sym) for sym in self._positions]
        return [p for p in positions if p is not None]

    def get_account(self) -> AccountInfo:
        """Get account information."""
        equity = self._cash
        for sym, pos in self._positions.items():
            price = self._last_prices.get(sym, pos.avg_entry_price)
            if pos.direction == "LONG":
                equity += pos.size * price
            else:
                equity += self._calc_pnl(pos, price)

        return AccountInfo(
            equity=equity,
            buying_power=self._cash,
            cash=self._cash,
        )

    def _calc_pnl(self, pos: _SimulatedPosition, current_price: float) -> float:
        """Calculate unrealized P&L for a position."""
        if pos.direction == "LONG":
            return (current_price - pos.avg_entry_price) * pos.size
        else:
            return (pos.avg_entry_price - current_price) * pos.size

    def _calc_pnl_for_size(self, pos: _SimulatedPosition, current_price: float, size: float) -> float:
        """Calculate P&L for a partial position size."""
        if pos.direction == "LONG":
            return (current_price - pos.avg_entry_price) * size
        else:
            return (pos.avg_entry_price - current_price) * size

"""Abstract protocol for broker implementations."""

from abc import ABC, abstractmethod

from ..models import AccountInfo, BrokerPosition, Order, OrderResult


class BrokerProtocol(ABC):
    """Abstract protocol for brokers. Implement this to add new broker integrations."""

    @abstractmethod
    def submit_order(self, order: Order) -> OrderResult:
        """Submit an order to the broker."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order. Returns True if successful."""
        ...

    @abstractmethod
    def get_position(self, symbol: str) -> BrokerPosition | None:
        """Get current position for a symbol, or None if no position."""
        ...

    @abstractmethod
    def get_positions(self) -> list[BrokerPosition]:
        """Get all current positions."""
        ...

    @abstractmethod
    def get_account(self) -> AccountInfo:
        """Get account information (equity, buying power, etc.)."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this broker."""
        ...

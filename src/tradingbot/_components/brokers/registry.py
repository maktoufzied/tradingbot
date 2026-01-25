"""Registry and facade for broker implementations."""

from tradingbot.interfaces import BrokerProtocol, Registry
from tradingbot.types import AccountInfo, BrokerPosition, Order, OrderResult


class BrokerRegistry(Registry[BrokerProtocol]):
    """Registry for broker implementations."""


class Broker:
    """Facade for broker operations using registered implementations."""

    @staticmethod
    def submit_order(order: Order, broker: str | None = None) -> OrderResult:
        """Submit an order using the specified or default broker."""
        impl: BrokerProtocol = BrokerRegistry().get(broker)
        return impl.submit_order(order)

    @staticmethod
    def cancel_order(order_id: str, broker: str | None = None) -> bool:
        """Cancel an order using the specified or default broker."""
        impl: BrokerProtocol = BrokerRegistry().get(broker)
        return impl.cancel_order(order_id)

    @staticmethod
    def get_position(symbol: str, broker: str | None = None) -> BrokerPosition | None:
        """Get position for a symbol using the specified or default broker."""
        impl: BrokerProtocol = BrokerRegistry().get(broker)
        return impl.get_position(symbol)

    @staticmethod
    def get_positions(broker: str | None = None) -> list[BrokerPosition]:
        """Get all positions using the specified or default broker."""
        impl: BrokerProtocol = BrokerRegistry().get(broker)
        return impl.get_positions()

    @staticmethod
    def get_account(broker: str | None = None) -> AccountInfo:
        """Get account info using the specified or default broker."""
        impl: BrokerProtocol = BrokerRegistry().get(broker)
        return impl.get_account()


def get_broker_registry() -> BrokerRegistry:
    """Get the broker registry singleton."""
    return BrokerRegistry()

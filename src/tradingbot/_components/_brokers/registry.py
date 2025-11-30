"""Registry and facade for broker implementations."""

from ..models import AccountInfo, BrokerPosition, Order, OrderResult
from .protocol import BrokerProtocol


class BrokerRegistry:
    """Dependency injection registry for brokers."""

    _instance: BrokerRegistry | None = None
    _brokers: dict[str, BrokerProtocol]
    _default: str | None

    def __new__(cls) -> BrokerRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._brokers = {}
            cls._instance._default = None
        return cls._instance

    def register(self, broker: BrokerProtocol, default: bool = False) -> None:
        """Register a broker implementation."""
        self._brokers[broker.name] = broker
        if default or self._default is None:
            self._default = broker.name

    def get(self, name: str | None = None) -> BrokerProtocol:
        """Get a broker by name, or the default broker."""
        key: str = name or self._default or ""
        if key not in self._brokers:
            raise KeyError(f"Broker '{key}' not registered. Available: {list(self._brokers.keys())}")
        return self._brokers[key]

    def list_brokers(self) -> list[str]:
        """List all registered broker names."""
        return list(self._brokers.keys())

    @property
    def default_broker(self) -> str | None:
        """Get the default broker name."""
        return self._default


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


def get_registry() -> BrokerRegistry:
    """Get the broker registry singleton."""
    return BrokerRegistry()

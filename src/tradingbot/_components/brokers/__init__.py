"""Broker abstraction layer for live trading."""

from tradingbot.interfaces import BrokerProtocol
from tradingbot.plugins import bootstrap

from .registry import Broker, get_broker_registry

__all__ = ["Broker", "BrokerProtocol", "get_broker_registry"]

bootstrap(get_broker_registry, BrokerProtocol, __name__, "live", "broker", default="paper")

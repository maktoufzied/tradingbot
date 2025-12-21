"""Broker abstraction layer for live trading."""

from tradingbot.interfaces import BrokerProtocol
from tradingbot.plugins import bootstrap

from .registry import Broker, get_registry

__all__ = ["Broker", "BrokerProtocol", "get_registry"]

bootstrap(get_registry, BrokerProtocol, __name__, "live", "broker", default="paper")

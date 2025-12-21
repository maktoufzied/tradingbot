"""Real-time data feed abstraction layer."""

from tradingbot.interfaces import DataFeedProtocol
from tradingbot.plugins import bootstrap

from .registry import DataFeed, get_registry

__all__ = ["DataFeed", "DataFeedProtocol", "get_registry"]

bootstrap(get_registry, DataFeedProtocol, __name__, "live", "feed", default="yahoo")

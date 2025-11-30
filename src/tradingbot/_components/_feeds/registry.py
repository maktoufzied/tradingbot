"""Registry for data feed implementations."""

from .protocol import DataFeedProtocol


class FeedRegistry:
    """Dependency injection registry for data feeds."""

    _instance: FeedRegistry | None = None
    _feeds: dict[str, DataFeedProtocol]
    _default: str | None

    def __new__(cls) -> FeedRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._feeds = {}
            cls._instance._default = None
        return cls._instance

    def register(self, feed: DataFeedProtocol, default: bool = False) -> None:
        """Register a data feed implementation."""
        self._feeds[feed.name] = feed
        if default or self._default is None:
            self._default = feed.name

    def get(self, name: str | None = None) -> DataFeedProtocol:
        """Get a feed by name, or the default feed."""
        key: str = name or self._default or ""
        if key not in self._feeds:
            raise KeyError(f"Feed '{key}' not registered. Available: {list(self._feeds.keys())}")
        return self._feeds[key]

    def list_feeds(self) -> list[str]:
        """List all registered feed names."""
        return list(self._feeds.keys())

    @property
    def default_feed(self) -> str | None:
        """Get the default feed name."""
        return self._default


def get_registry() -> FeedRegistry:
    """Get the feed registry singleton."""
    return FeedRegistry()

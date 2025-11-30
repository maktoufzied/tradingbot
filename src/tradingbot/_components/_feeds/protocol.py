"""Abstract protocol for real-time data feed implementations."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from ..models import Bar


class DataFeedProtocol(ABC):
    """Abstract protocol for data feeds. Implement this to add new data sources."""

    @abstractmethod
    async def subscribe(self, symbols: list[str], on_bar: Callable[[Bar], Awaitable[None] | None]) -> None:
        """Subscribe to real-time bars for the given symbols.

        Args:
            symbols: List of symbols to subscribe to
            on_bar: Callback invoked when a new bar is received
        """
        ...

    @abstractmethod
    async def unsubscribe(self, symbols: list[str]) -> None:
        """Unsubscribe from the given symbols."""
        ...

    @abstractmethod
    async def start(self) -> None:
        """Start the data feed connection."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the data feed and disconnect."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this data feed."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the feed is currently connected."""
        ...

"""Protocol interfaces for all pluggable components."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Collection
from typing import Protocol, Self

import polars as pl

from tradingbot.types import (
    AccountInfo,
    Bar,
    BrokerPosition,
    Direction,
    MarketClock,
    Order,
    OrderResult,
    Position,
    Signal,
    SwingPoint,
)


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
    def get_order(self, order_id: str) -> OrderResult | None:
        """Get current status of an order. Returns None if order not found."""
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

    def get_clock(self) -> MarketClock | None:
        """Get market clock (open/close status). Returns None if not supported."""
        return None

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this broker."""
        ...


class DataFeedProtocol(ABC):
    """Abstract protocol for data feeds. Implement this to add new data sources."""

    @abstractmethod
    async def subscribe(self, symbols: Collection[str], on_bar: Callable[[Bar], Awaitable[None] | None]) -> None:
        """Subscribe to real-time bars for the given symbols.

        Args:
            symbols: List of symbols to subscribe to
            on_bar: Callback invoked when a new bar is received
        """
        ...

    @abstractmethod
    async def unsubscribe(self, symbols: Collection[str]) -> None:
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

    def set_raw_bar_callback(self, callback: Callable[[str, float, int, int], None] | None) -> None:
        """Set callback for raw bar progress updates during aggregation.

        Args:
            callback: Function called with (symbol, price, collected, target)
                      or None to clear the callback.

        Feeds that don't support aggregation should raise NotImplementedError.
        """
        raise NotImplementedError(f"{self.name} feed does not support raw bar callbacks")

    def history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        period: str = "1y",
        interval: str = "1d",
        debug: bool = False,
    ) -> pl.DataFrame:
        """Fetch historical OHLCV data for a symbol.

        Args:
            symbol: Ticker symbol to fetch
            start_date: Start date (YYYY-MM-DD format)
            end_date: End date (YYYY-MM-DD format)
            period: Period to fetch if no dates given (e.g., "2y", "1mo")
            interval: Bar interval (e.g., "1d", "1h", "5m")
            debug: Print debug info during fetch

        Returns:
            DataFrame with columns: datetime, open, high, low, close, volume
        """
        raise NotImplementedError(f"{self.name} feed does not support historical data")


class ExitStrategyProtocol(Protocol):
    """Protocol for exit (stop-loss and take-profit) calculation strategies."""

    @property
    def name(self) -> str:
        """Unique identifier for this strategy."""
        ...

    def calc(
        self,
        direction: Direction,
        entry: float,
        rr_ratio: float,
        bars: pl.DataFrame,
        swings: list[SwingPoint],
    ) -> tuple[float, float]:
        """Calculate stop loss and take-profit prices.

        Args:
            direction: Trade direction ("LONG" or "SHORT")
            entry: Entry price
            rr_ratio: Risk/reward ratio (e.g., 2.0 for 2:1)
            bars: OHLCV price data (last row is current bar)
            swings: List of swing points

        Returns:
            Tuple of (stop_loss, take_profit) prices
        """
        ...


class IndicatorProtocol(Protocol):
    """Protocol for technical indicators."""

    @property
    def name(self) -> str:
        """Unique identifier for this indicator."""
        ...

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute indicator values and add columns to DataFrame.

        Args:
            df: OHLCV DataFrame with columns: datetime, open, high, low, close, volume

        Returns:
            DataFrame with original columns plus indicator columns
        """
        ...

    def get_signal(self, df: pl.DataFrame, idx: int) -> Signal | None:
        """Generate standalone signal from indicator (optional).

        Args:
            df: DataFrame with indicator columns already computed
            idx: Current bar index

        Returns:
            Signal.BUY, Signal.SELL, or None (no signal)
        """
        ...

    def filter_signal(self, signal: Signal, df: pl.DataFrame, idx: int) -> bool:
        """Check if a signal should be allowed through the filter.

        Args:
            signal: The signal to filter (BUY or SELL)
            df: DataFrame with indicator columns already computed
            idx: Current bar index

        Returns:
            True if signal should be allowed, False to block it
        """
        ...


class EntryStrategyProtocol(Protocol):
    """Protocol for entry signal generation strategies.

    Entry strategies encapsulate the complete logic for:
    1. Computing required indicators
    2. Generating entry signals (BUY/SELL/HOLD)
    3. Providing strategy-specific exit parameters
    """

    @property
    def name(self) -> str:
        """Unique identifier for this strategy."""
        ...

    @property
    def default_rr_ratio(self) -> float:
        """Recommended RR ratio for this strategy.

        This is used when the strategy calculates its own exit parameters.
        """
        ...

    def compute_indicators(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute any required indicator columns.

        Args:
            df: OHLCV DataFrame

        Returns:
            DataFrame with indicator columns added
        """
        ...

    def generate(
        self,
        df: pl.DataFrame,
        idx: int,
        position: Position | None,
    ) -> tuple[Signal, dict[str, str | float]]:
        """Generate entry signal with analysis details.

        Args:
            df: OHLCV DataFrame with any required indicators
            idx: Current bar index
            position: Current open position, if any

        Returns:
            Tuple of (Signal, details_dict)
        """
        ...

    def get_exit_params(
        self,
        direction: Direction,
        entry: float,
        df: pl.DataFrame,
        swings: list[SwingPoint],
    ) -> tuple[float, float] | None:
        """Calculate strategy-specific stop loss and take profit.

        Some strategies have natural exit levels (e.g., VWAP return).
        Returns None to use the default exit strategy instead.

        Args:
            direction: Trade direction
            entry: Entry price
            df: OHLCV DataFrame with indicators
            swings: Detected swing points

        Returns:
            Tuple of (stop_loss, take_profit) or None to use default
        """
        ...


class NamedPlugin(Protocol):
    """Protocol for plugins with a name property."""

    @property
    def name(self) -> str: ...


class PluginRegistry[P](Protocol):
    """Protocol for registries that can register plugins."""

    def register(self, plugin: P, *, default: bool = False) -> None: ...


class Registry[P: NamedPlugin]:
    """Base registry class with singleton behavior and plugin management."""

    _instance: Self | None = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_plugins"):
            self._plugins: dict[str, P] = {}
            self._default: str | None = None

    def register(self, plugin: P, *, default: bool = False) -> None:
        """Register a plugin implementation."""
        self._plugins[plugin.name] = plugin
        if default or self._default is None:
            self._default = plugin.name

    def get(self, name: str | None = None) -> P:
        """Get a plugin by name, or the default plugin."""
        key = name or self._default or ""
        if key not in self._plugins:
            raise KeyError(f"Plugin '{key}' not registered. Available: {list(self._plugins.keys())}")
        return self._plugins[key]

    def list(self) -> list[str]:
        """List all registered plugin names."""
        return list(self._plugins.keys())

    @property
    def default_name(self) -> str | None:
        """Get the default plugin name."""
        return self._default

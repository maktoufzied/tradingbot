from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal


class Trend(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class BarOrigin(Enum):
    REALTIME = "realtime"  # Raw 1m bar from feed
    AGGREGATED = "aggregated"  # Aggregated to strategy interval (e.g., 5m)


Direction = Literal["LONG", "SHORT"]
ExitReason = Literal["STOP_LOSS", "TAKE_PROFIT", "PARTIAL_EXIT", "TIME_EXIT", "EOD_EXIT"]
OrderType = Literal["MARKET", "LIMIT", "STOP"]
OrderStatus = Literal["FILLED", "PARTIAL", "PENDING", "REJECTED", "CANCELLED"]


@dataclass(frozen=True)
class PartialExitLevel:
    """Defines a partial exit level at a specific R-multiple."""

    r_multiple: float  # Exit at this R-multiple (e.g., 1.0 = 1R profit)
    exit_pct: float  # Percentage of remaining position to exit (0.0-1.0)

    def __post_init__(self) -> None:
        if self.r_multiple <= 0:
            raise ValueError(f"r_multiple must be positive, got {self.r_multiple}")
        if not (0 < self.exit_pct <= 1.0):
            raise ValueError(f"exit_pct must be in (0.0, 1.0], got {self.exit_pct}")


@dataclass
class PartialExit:
    """Records an executed partial exit."""

    r_multiple: float
    exit_price: float
    exit_size: float
    pnl: float
    exit_time: datetime


@dataclass
class SwingPoint:
    index: int
    price: float
    is_high: bool
    timestamp: datetime | None = None


@dataclass
class Position:
    entry_price: float
    entry_index: int
    entry_time: datetime
    direction: Direction
    size: float
    stop_loss: float
    take_profit: float
    initial_stop_loss: float | None = None  # For trailing stop calculation
    remaining_size: float | None = None  # Tracks size after partial exits (None = full size)
    partial_exits: list[PartialExit] | None = None  # Executed partial exits
    triggered_levels: set[float] | None = None  # R-multiples already triggered
    high_water_mark: float | None = None  # Highest (LONG) or lowest (SHORT) price since entry

    def get_remaining_size(self) -> float:
        """Get remaining position size (accounts for partial exits)."""
        return self.remaining_size if self.remaining_size is not None else self.size


@dataclass
class Trade:
    symbol: str
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    entry_index: int
    direction: Direction
    size: float
    pnl: float  # Net P&L (after costs)
    pnl_pct: float
    exit_reason: ExitReason
    holding_period: int
    gross_pnl: float | None = None  # P&L before costs (None for backward compat)
    execution_costs: float | None = None  # Total execution costs
    partial_exits: list[PartialExit] | None = None  # Partial exits taken during trade
    stop_loss: float | None = None  # Stop loss price
    take_profit: float | None = None  # Take profit price


# Live trading models


@dataclass
class Bar:
    """Single OHLCV bar for live data feeds."""

    symbol: str
    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    origin: BarOrigin = BarOrigin.AGGREGATED  # Default for backward compat


@dataclass
class Order:
    """Order to submit to broker.

    For bracket orders (entry + SL + TP), provide stop_loss and take_profit.
    The broker will place all three orders atomically.
    """

    symbol: str
    direction: Direction
    size: float
    order_type: OrderType = "MARKET"
    limit_price: float | None = None
    stop_price: float | None = None
    client_id: str | None = None
    # Bracket order fields (SL/TP placed as OCO orders)
    stop_loss: float | None = None
    take_profit: float | None = None


@dataclass
class OrderResult:
    """Result from broker after order submission."""

    order_id: str
    status: OrderStatus
    filled_price: float | None
    filled_size: float
    message: str | None = None


@dataclass
class PendingOrder:
    """Tracks a pending order awaiting fill."""

    order_id: str
    symbol: str
    direction: Direction
    expected_price: float
    stop_loss: float
    take_profit: float
    entry_index: int
    entry_time: datetime


@dataclass
class BrokerPosition:
    """Current position held at broker."""

    symbol: str
    direction: Direction
    size: float
    avg_entry_price: float
    market_value: float
    unrealized_pnl: float


@dataclass
class AccountInfo:
    """Broker account information."""

    equity: float
    buying_power: float
    cash: float


@dataclass
class MarketClock:
    """Market clock status."""

    is_open: bool
    next_open: datetime | None = None
    next_close: datetime | None = None

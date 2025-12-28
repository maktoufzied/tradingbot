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


Direction = Literal["LONG", "SHORT"]
ExitReason = Literal["STOP_LOSS", "TAKE_PROFIT", "TIME_EXIT", "EOD_EXIT"]
OrderType = Literal["MARKET", "LIMIT", "STOP"]
OrderStatus = Literal["FILLED", "PARTIAL", "PENDING", "REJECTED", "CANCELLED"]


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


@dataclass
class Order:
    """Order to submit to broker."""

    symbol: str
    direction: Direction
    size: float
    order_type: OrderType = "MARKET"
    limit_price: float | None = None
    stop_price: float | None = None
    client_id: str | None = None


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

"""Event types for the trading engine."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from tradingbot.types import Bar, Direction, Position, Signal

from ..live_risk import LiveRiskManager


class MessageLevel(Enum):
    """Semantic message levels for engine events."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    DEBUG = "debug"


@dataclass
class EngineStartedEvent:
    symbols: list[str]
    broker_name: str
    feed_name: str
    dry_run: bool


@dataclass
class EngineStoppedEvent:
    risk_manager: LiveRiskManager


@dataclass
class MessageEvent:
    message: str
    level: MessageLevel = MessageLevel.INFO


@dataclass
class BarEvent:
    bar: Bar
    signal: Signal
    trend: str
    position: Position | None


@dataclass
class SignalEvent:
    direction: Direction
    symbol: str
    entry: float
    stop: float
    tp: float
    size: float
    blocked: bool
    reason: str
    was_capped: bool


@dataclass
class TradeClosedEvent:
    direction: Direction
    symbol: str
    entry: float
    exit_price: float
    size: float
    pnl: float
    reason: str


@dataclass
class StatsUpdatedEvent:
    pnl: float
    trades: int
    winners: int
    losers: int


@dataclass
class AccountEvent:
    equity: float
    cash: float
    buying_power: float
    day_pnl: float


@dataclass
class RiskEvent:
    daily_loss_pct: float
    max_daily_loss_pct: float
    open_positions: int
    max_positions: int
    circuit_breaker_active: bool
    can_trade: bool
    blocked_reason: str | None


@dataclass
class ClockEvent:
    is_open: bool
    next_open: datetime | None
    next_close: datetime | None

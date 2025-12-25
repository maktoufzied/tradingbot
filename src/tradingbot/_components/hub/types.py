"""UI message types for the Event Hub.

All types are JSON-serializable dataclasses for WebSocket transmission.
These represent the data that flows from the engine to any UI client.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal


class UIChannel(Enum):
    """Message channels for subscription filtering."""

    TICKER = "ticker"
    POSITION = "position"
    TRADE = "trade"
    STATS = "stats"
    ACCOUNT = "account"
    RISK = "risk"
    STATUS = "status"
    CHART = "chart"


@dataclass(slots=True)
class TickerUpdate:
    """Real-time price update for a symbol."""

    symbol: str
    price: float
    change: float
    change_pct: float
    high: float
    low: float
    volume: int
    timestamp: datetime
    trend: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    signal: Literal["BUY", "SELL", "HOLD"]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass(slots=True)
class PositionUpdate:
    """Open position state."""

    symbol: str
    direction: Literal["LONG", "SHORT"] | None
    entry_price: float
    current_price: float
    size: float
    stop_loss: float
    take_profit: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    holding_minutes: int
    risk_amount: float
    is_open: bool

    @classmethod
    def empty(cls, symbol: str) -> PositionUpdate:
        """Factory for no-position state."""
        return cls(
            symbol=symbol,
            direction=None,
            entry_price=0.0,
            current_price=0.0,
            size=0.0,
            stop_loss=0.0,
            take_profit=0.0,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            holding_minutes=0,
            risk_amount=0.0,
            is_open=False,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TradeAlert:
    """Trade entry/exit notification for the signal log."""

    type: Literal["ENTRY", "EXIT", "BLOCKED"]
    symbol: str
    direction: Literal["LONG", "SHORT"]
    price: float
    size: float
    stop_loss: float | None
    take_profit: float | None
    pnl: float | None
    pnl_pct: float | None
    reason: str | None
    strategy: str | None
    timestamp: datetime
    is_winner: bool | None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass(slots=True)
class SessionStats:
    """Aggregated session performance."""

    total_pnl: float
    total_pnl_pct: float
    trade_count: int
    win_count: int
    loss_count: int
    win_rate: float
    profit_factor: float
    largest_win: float
    largest_loss: float
    current_streak: int
    equity_curve: list[float] = field(default_factory=list)

    @classmethod
    def empty(cls) -> SessionStats:
        return cls(
            total_pnl=0.0,
            total_pnl_pct=0.0,
            trade_count=0,
            win_count=0,
            loss_count=0,
            win_rate=0.0,
            profit_factor=0.0,
            largest_win=0.0,
            largest_loss=0.0,
            current_streak=0,
            equity_curve=[],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AccountSnapshot:
    """Broker account state."""

    equity: float
    cash: float
    buying_power: float
    realized_pnl: float
    unrealized_pnl: float
    positions_value: float

    @classmethod
    def empty(cls) -> AccountSnapshot:
        return cls(
            equity=0.0,
            cash=0.0,
            buying_power=0.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            positions_value=0.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RiskStatus:
    """Risk management state."""

    daily_loss_pct: float
    max_daily_loss_pct: float
    open_positions: int
    max_positions: int
    circuit_breaker_active: bool
    can_trade: bool
    blocked_reason: str | None

    @classmethod
    def default(cls) -> RiskStatus:
        return cls(
            daily_loss_pct=0.0,
            max_daily_loss_pct=0.05,
            open_positions=0,
            max_positions=5,
            circuit_breaker_active=False,
            can_trade=True,
            blocked_reason=None,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SystemStatus:
    """Connection and system health."""

    feed_connected: bool
    broker_connected: bool
    market_open: bool
    market_next_change: datetime | None
    uptime_seconds: int
    bars_received: int
    errors_count: int
    is_replay: bool = False
    replay_time: datetime | None = None

    @classmethod
    def default(cls) -> SystemStatus:
        return cls(
            feed_connected=False,
            broker_connected=False,
            market_open=False,
            market_next_change=None,
            uptime_seconds=0,
            bars_received=0,
            errors_count=0,
            is_replay=False,
            replay_time=None,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.market_next_change:
            d["market_next_change"] = self.market_next_change.isoformat()
        if self.replay_time:
            d["replay_time"] = self.replay_time.isoformat()
        return d


@dataclass(slots=True)
class ChartUpdate:
    """Price history for sparkline charts."""

    symbol: str
    prices: list[float]
    timestamps: list[datetime]
    swing_highs: list[float]
    swing_lows: list[float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "prices": self.prices,
            "timestamps": [t.isoformat() for t in self.timestamps],
            "swing_highs": self.swing_highs,
            "swing_lows": self.swing_lows,
        }


@dataclass(slots=True)
class StrategyInfo:
    """Strategy/preset configuration info."""

    preset_name: str
    entry_strategy: str
    exit_strategy: str
    risk_pct: float
    rr_ratio: float
    indicators: list[str]

    @classmethod
    def default(cls) -> StrategyInfo:
        return cls(
            preset_name="custom",
            entry_strategy="swing_break",
            exit_strategy="swing",
            risk_pct=0.01,
            rr_ratio=1.5,
            indicators=[],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GlobalState:
    """Complete state snapshot for new client sync."""

    tickers: dict[str, TickerUpdate] = field(default_factory=dict)
    positions: dict[str, PositionUpdate] = field(default_factory=dict)
    stats: SessionStats = field(default_factory=SessionStats.empty)
    account: AccountSnapshot = field(default_factory=AccountSnapshot.empty)
    risk: RiskStatus = field(default_factory=RiskStatus.default)
    status: SystemStatus = field(default_factory=SystemStatus.default)
    charts: dict[str, ChartUpdate] = field(default_factory=dict)
    recent_trades: list[TradeAlert] = field(default_factory=list)
    strategy: StrategyInfo = field(default_factory=StrategyInfo.default)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tickers": {k: v.to_dict() for k, v in self.tickers.items()},
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "stats": self.stats.to_dict(),
            "account": self.account.to_dict(),
            "risk": self.risk.to_dict(),
            "status": self.status.to_dict(),
            "charts": {k: v.to_dict() for k, v in self.charts.items()},
            "recent_trades": [t.to_dict() for t in self.recent_trades],
            "strategy": self.strategy.to_dict(),
        }

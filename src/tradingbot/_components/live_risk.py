"""Live trading risk controls and safety measures."""

from datetime import date, datetime, time
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from .config import LiveRiskConfig

MARKET_OPEN: Final[time] = time(9, 30)
MARKET_CLOSE: Final[time] = time(16, 0)


class LiveRiskManager:
    """Risk management for live trading with safety controls."""

    def __init__(self, config: LiveRiskConfig, initial_equity: float) -> None:
        self._config = config
        self._initial_equity = initial_equity
        self._daily_start_equity = initial_equity
        self._realized_pnl_today = 0.0
        self._last_reset_date: date | None = None
        self._circuit_breaker_triggered = False
        self._open_positions = 0

    def reset_daily(self, current_equity: float) -> None:
        """Reset daily tracking (call at market open)."""
        today = datetime.now().date()
        if self._last_reset_date != today:
            self._daily_start_equity = current_equity
            self._realized_pnl_today = 0.0
            self._circuit_breaker_triggered = False
            self._last_reset_date = today

    def record_trade_pnl(self, pnl: float) -> None:
        """Record P&L from a closed trade."""
        self._realized_pnl_today += pnl

        # Check circuit breaker
        loss_pct = -self._realized_pnl_today / self._daily_start_equity
        if loss_pct >= self._config.circuit_breaker_loss_pct:
            self._circuit_breaker_triggered = True

    def update_position_count(self, count: int) -> None:
        """Update the current number of open positions."""
        self._open_positions = count

    def can_open_position(self, position_value: float, current_equity: float) -> tuple[bool, str]:
        """Check if a new position can be opened.

        Returns:
            Tuple of (allowed, reason_if_blocked)
        """
        # Check circuit breaker
        if self._circuit_breaker_triggered:
            return False, "Circuit breaker triggered - daily loss limit reached"

        # Check max positions
        if self._open_positions >= self._config.max_open_positions:
            return False, f"Max open positions ({self._config.max_open_positions}) reached"

        # Check position size
        position_pct = position_value / current_equity
        if position_pct > self._config.max_position_size_pct:
            return False, f"Position size ({position_pct:.1%}) exceeds limit ({self._config.max_position_size_pct:.1%})"

        # Check daily loss limit
        unrealized_loss_pct = -self._realized_pnl_today / self._daily_start_equity
        if unrealized_loss_pct >= self._config.max_daily_loss_pct:
            return False, f"Daily loss limit ({self._config.max_daily_loss_pct:.1%}) reached"

        # Check trading hours
        if self._config.trading_hours_only and not self.is_trading_hours():
            return False, "Outside trading hours"

        return True, ""

    def is_trading_hours(self) -> bool:
        """Check if current time is within trading hours (US Eastern)."""
        now = datetime.now().time()
        return MARKET_OPEN <= now <= MARKET_CLOSE

    def check_circuit_breaker(self) -> bool:
        """Check if circuit breaker is triggered."""
        return self._circuit_breaker_triggered

    @property
    def daily_pnl(self) -> float:
        """Get realized P&L for today."""
        return self._realized_pnl_today

    @property
    def daily_pnl_pct(self) -> float:
        """Get realized P&L percentage for today."""
        if self._daily_start_equity == 0:
            return 0.0
        return self._realized_pnl_today / self._daily_start_equity

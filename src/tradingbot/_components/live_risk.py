"""Live trading risk controls and safety measures."""

from datetime import date, datetime, time
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from tradingbot.config import EngineRiskConfig

MARKET_OPEN: Final[time] = time(9, 30)
MARKET_CLOSE: Final[time] = time(16, 0)


class LiveRiskManager:
    """Risk management for live trading with safety controls."""

    def __init__(self, config: EngineRiskConfig, initial_equity: float) -> None:
        self._config = config
        self._initial_equity = initial_equity
        self._daily_start_equity = initial_equity
        self._realized_pnl_today = 0.0
        self._last_reset_date: date | None = None
        self._circuit_breaker_triggered = False
        self._open_positions = 0

        # Session-level tracking (for replay/live summary)
        self._session_pnl = 0.0
        self._session_trades = 0
        self._session_winners = 0
        self._session_losers = 0
        self._session_gross_profit = 0.0
        self._session_gross_loss = 0.0

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

        # Session-level tracking
        self._session_pnl += pnl
        self._session_trades += 1
        if pnl > 0:
            self._session_winners += 1
            self._session_gross_profit += pnl
        else:
            self._session_losers += 1
            self._session_gross_loss += abs(pnl)

        # Check circuit breaker
        loss_pct = -self._realized_pnl_today / self._daily_start_equity
        if loss_pct >= self._config.circuit_breaker_loss_pct:
            self._circuit_breaker_triggered = True

    def update_position_count(self, count: int) -> None:
        """Update the current number of open positions."""
        self._open_positions = count

    def can_open_position(self) -> tuple[bool, str]:
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

        # Check daily loss limit
        unrealized_loss_pct = -self._realized_pnl_today / self._daily_start_equity
        if unrealized_loss_pct >= self._config.max_daily_loss_pct:
            return False, f"Daily loss limit ({self._config.max_daily_loss_pct:.1%}) reached"

        # Check trading hours
        if self._config.trading_hours_only and not self.is_trading_hours():
            return False, "Outside trading hours"

        return True, ""

    def cap_position_size(self, size: float, price: float, current_equity: float) -> tuple[float, bool]:
        """Cap position size to max allowed percentage of equity.

        Returns:
            Tuple of (adjusted_size, was_capped)
        """
        position_value = size * price
        position_pct = position_value / current_equity
        max_pct = self._config.max_position_size_pct

        if position_pct > max_pct:
            max_value = current_equity * max_pct
            capped_size = max_value / price
            return capped_size, True

        return size, False

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

    @property
    def session_pnl(self) -> float:
        """Get total P&L for the session."""
        return self._session_pnl

    @property
    def session_trades(self) -> int:
        """Get total number of trades in the session."""
        return self._session_trades

    @property
    def session_winners(self) -> int:
        """Get number of winning trades in the session."""
        return self._session_winners

    @property
    def session_losers(self) -> int:
        """Get number of losing trades in the session."""
        return self._session_losers

    @property
    def session_win_rate(self) -> float:
        """Get win rate for the session."""
        if self._session_trades == 0:
            return 0.0
        return self._session_winners / self._session_trades

    @property
    def session_profit_factor(self) -> float:
        """Get profit factor for the session."""
        if self._session_gross_loss == 0:
            return 999.0 if self._session_gross_profit > 0 else 0.0
        return self._session_gross_profit / self._session_gross_loss

    @property
    def session_return_pct(self) -> float:
        """Get session return as percentage of initial equity."""
        if self._initial_equity == 0:
            return 0.0
        return self._session_pnl / self._initial_equity

    @property
    def final_equity(self) -> float:
        """Get final equity after session P&L."""
        return self._initial_equity + self._session_pnl

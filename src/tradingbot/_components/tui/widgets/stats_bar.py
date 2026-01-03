"""Stats Bar widget - Session, Account, and Risk panels."""

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from tradingbot._components.hub.types import (
    AccountSnapshot,
    RiskStatus,
    SessionStats,
)

from ..theme import THEME


class SessionPanel(Widget):
    """Session statistics panel."""

    DEFAULT_CSS = """
    SessionPanel {
        height: 100%;
        width: 1fr;
        padding: 0 1;
        border-right: solid #1a1a2a;
    }

    SessionPanel Static {
        height: 1;
    }
    """

    stats: reactive[SessionStats | None] = reactive(None)

    def compose(self) -> ComposeResult:
        yield Static("SESSION", classes="panel-title")
        yield Static("", id="pnl-line")
        yield Static("", id="trades-line")
        yield Static("", id="metrics-line")
        yield Static("", id="streak-line")

    def on_mount(self) -> None:
        self._update_display()

    def watch_stats(self, stats: SessionStats | None) -> None:
        self._update_display()

    def _update_display(self) -> None:
        stats = self.stats

        try:
            pnl_line = self.query_one("#pnl-line", Static)
            trades_line = self.query_one("#trades-line", Static)
            metrics_line = self.query_one("#metrics-line", Static)
            streak_line = self.query_one("#streak-line", Static)
        except NoMatches:
            return

        if not stats:
            pnl_line.update(Text("P&L --", style=THEME.text_dim))
            trades_line.update(Text("Trades --", style=THEME.text_dim))
            metrics_line.update(Text("Win -- PF --", style=THEME.text_dim))
            streak_line.update("")
            return

        # P&L line
        pnl_color = THEME.positive if stats.total_pnl >= 0 else THEME.negative
        pnl_sign = "+" if stats.total_pnl >= 0 else ""
        pnl_text = Text()
        pnl_text.append("P&L ", style=THEME.text_dim)
        pnl_text.append(
            f"{pnl_sign}${stats.total_pnl:,.2f}",
            style=f"bold {pnl_color}",
        )
        if stats.total_pnl_pct != 0:
            pnl_text.append(
                f" ({pnl_sign}{stats.total_pnl_pct:.1f}%)",
                style=pnl_color,
            )
        pnl_line.update(pnl_text)

        # Trades line
        trades_text = Text()
        trades_text.append(f"{stats.trade_count} trades ", style=THEME.text)
        trades_text.append(f"({stats.win_count}W", style=THEME.positive_dim)
        trades_text.append("/", style=THEME.text_dim)
        trades_text.append(f"{stats.loss_count}L)", style=THEME.negative_dim)
        trades_line.update(trades_text)

        # Metrics line
        metrics_text = Text()
        metrics_text.append("Win ", style=THEME.text_dim)
        win_color = THEME.positive if stats.win_rate >= 50 else THEME.text
        metrics_text.append(f"{stats.win_rate:.0f}%", style=win_color)
        metrics_text.append("  PF ", style=THEME.text_dim)
        # PF < 0 is sentinel for "not applicable" (no losses yet)
        if stats.profit_factor < 0:
            metrics_text.append("-", style=THEME.text_dim)
        else:
            pf_color = THEME.positive if stats.profit_factor >= 1.5 else THEME.text
            metrics_text.append(f"{stats.profit_factor:.1f}", style=pf_color)
        metrics_line.update(metrics_text)

        # Streak line with visual indicator
        if stats.current_streak != 0:
            streak_text = Text()
            if stats.current_streak > 0:
                bars = "\u2588" * min(stats.current_streak, 5)
                streak_text.append(f"{bars} +{stats.current_streak}", style=THEME.positive)
            else:
                bars = "\u2588" * min(abs(stats.current_streak), 5)
                streak_text.append(f"{bars} {stats.current_streak}", style=THEME.negative)
            streak_line.update(streak_text)
        else:
            streak_line.update("")


class AccountPanel(Widget):
    """Account information panel."""

    DEFAULT_CSS = """
    AccountPanel {
        height: 100%;
        width: 1fr;
        padding: 0 1;
        border-right: solid #1a1a2a;
    }

    AccountPanel Static {
        height: 1;
    }
    """

    account: reactive[AccountSnapshot | None] = reactive(None)

    def compose(self) -> ComposeResult:
        yield Static("ACCOUNT", classes="panel-title")
        yield Static("", id="equity-line")
        yield Static("", id="cash-line")
        yield Static("", id="pnl-line")

    def on_mount(self) -> None:
        self._update_display()

    def watch_account(self, account: AccountSnapshot | None) -> None:
        self._update_display()

    def _update_display(self) -> None:
        account = self.account

        try:
            equity_line = self.query_one("#equity-line", Static)
            cash_line = self.query_one("#cash-line", Static)
            pnl_line = self.query_one("#pnl-line", Static)
        except NoMatches:
            return

        if not account:
            equity_line.update(Text("Equity --", style=THEME.text_dim))
            cash_line.update(Text("Cash --", style=THEME.text_dim))
            pnl_line.update(Text("P&L --", style=THEME.text_dim))
            return

        # Equity
        equity_text = Text()
        equity_text.append("Equity ", style=THEME.text_dim)
        equity_text.append(f"${account.equity:,.0f}", style=f"bold {THEME.text}")
        equity_line.update(equity_text)

        # Cash
        cash_text = Text()
        cash_text.append("Cash ", style=THEME.text_dim)
        cash_text.append(f"${account.cash:,.0f}", style=THEME.text)
        cash_line.update(cash_text)

        # P&L line: Rlzd +$X  Urlzd +$Y
        pnl_text = Text()
        pnl_text.append("Rlzd ", style=THEME.text_dim)
        realized_color = THEME.positive if account.realized_pnl >= 0 else THEME.negative
        realized_sign = "+" if account.realized_pnl >= 0 else ""
        pnl_text.append(f"{realized_sign}${abs(account.realized_pnl):,.2f}", style=realized_color)
        pnl_text.append("  Urlzd ", style=THEME.text_dim)
        unrealized_color = THEME.positive if account.unrealized_pnl >= 0 else THEME.negative
        unrealized_sign = "+" if account.unrealized_pnl >= 0 else ""
        pnl_text.append(f"{unrealized_sign}${abs(account.unrealized_pnl):,.2f}", style=unrealized_color)
        pnl_line.update(pnl_text)


class RiskPanel(Widget):
    """Risk status panel."""

    DEFAULT_CSS = """
    RiskPanel {
        height: 100%;
        width: 1fr;
        padding: 0 1;
    }

    RiskPanel Static {
        height: 1;
    }
    """

    risk: reactive[RiskStatus | None] = reactive(None)

    def compose(self) -> ComposeResult:
        yield Static("RISK", classes="panel-title")
        yield Static("", id="daily-line")
        yield Static("", id="positions-line")
        yield Static("", id="status-line")

    def on_mount(self) -> None:
        self._update_display()

    def watch_risk(self, risk: RiskStatus | None) -> None:
        self._update_display()

    def _update_display(self) -> None:
        risk = self.risk

        try:
            daily_line = self.query_one("#daily-line", Static)
            positions_line = self.query_one("#positions-line", Static)
            status_line = self.query_one("#status-line", Static)
        except NoMatches:
            return

        if not risk:
            daily_line.update(Text("Daily --", style=THEME.text_dim))
            positions_line.update(Text("Positions --", style=THEME.text_dim))
            status_line.update("")
            return

        # Daily loss limit meter
        daily_text = Text()
        daily_text.append("Limit ", style=THEME.text_dim)

        # Only actual losses count toward the limit (negative = loss)
        actual_loss = max(0.0, -risk.daily_loss_pct)
        max_pct = risk.max_daily_loss_pct if risk.max_daily_loss_pct > 0 else 5.0

        # Show loss toward limit
        daily_text.append(f"{actual_loss:.1f}%", style=THEME.text)
        daily_text.append(f"/{max_pct:.0f}%", style=THEME.text_dim)

        # Progress bar
        pct_used = actual_loss / max_pct
        pct_used = min(1.0, pct_used)
        filled = int(pct_used * 8)
        empty = 8 - filled
        bar_color = THEME.negative if pct_used > 0.6 else THEME.warning if pct_used > 0.3 else THEME.positive
        daily_text.append(" ")
        daily_text.append("\u2588" * filled, style=bar_color)
        daily_text.append("\u2591" * empty, style=THEME.text_muted)
        daily_line.update(daily_text)

        # Positions
        pos_text = Text()
        pos_text.append("Positions ", style=THEME.text_dim)
        pos_text.append(f"{risk.open_positions}", style=THEME.text)
        pos_text.append(f"/{risk.max_positions}", style=THEME.text_secondary)
        positions_line.update(pos_text)

        # Trading status
        if risk.circuit_breaker_active:
            status_text = Text("\u2717 CIRCUIT BREAKER", style=f"bold {THEME.negative}")
        elif not risk.can_trade:
            reason = risk.blocked_reason or "Blocked"
            status_text = Text(f"\u2717 {reason}", style=THEME.warning)
        else:
            status_text = Text("\u2713 Can Trade", style=THEME.positive)
        status_line.update(status_text)


class StatsBar(Widget):
    """Combined stats bar with Session, Account, and Risk panels."""

    DEFAULT_CSS = """
    StatsBar {
        height: 6;
        width: 100%;
        border: round #2a2a3a;
        background: #0f0f18;
    }

    StatsBar .panel-title {
        color: #ffaa00;
        text-style: bold;
        height: 1;
    }

    StatsBar Horizontal {
        height: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield SessionPanel(id="session-panel")
            yield AccountPanel(id="account-panel")
            yield RiskPanel(id="risk-panel")

    def update_stats(self, stats: SessionStats) -> None:
        """Update session stats."""
        try:
            panel = self.query_one("#session-panel", SessionPanel)
            panel.stats = stats
        except NoMatches:
            pass

    def update_account(self, account: AccountSnapshot) -> None:
        """Update account info."""
        try:
            panel = self.query_one("#account-panel", AccountPanel)
            panel.account = account
        except NoMatches:
            pass

    def update_risk(self, risk: RiskStatus) -> None:
        """Update risk status."""
        try:
            panel = self.query_one("#risk-panel", RiskPanel)
            panel.risk = risk
        except NoMatches:
            pass

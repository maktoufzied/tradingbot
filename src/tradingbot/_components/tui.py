"""Terminal UI for live trading using Textual."""

from collections import deque
from datetime import datetime
from typing import Final

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import Footer, Header, Label, RichLog, Static

from .models import Bar, Direction, Position, Signal

MAX_PRICE_HISTORY: Final[int] = 60


class PriceChart(Static):  # type: ignore[misc]
    """Braille-based price chart widget for smooth line rendering."""

    prices: reactive[list[float]] = reactive(list, init=False)

    # Braille patterns for 2x4 dot matrix (each char = 2 cols x 4 rows)
    BRAILLE_BASE = 0x2800
    # Dot positions: (col, row) -> bit
    # Col 0: rows 0-3 = bits 0,1,2,6
    # Col 1: rows 0-3 = bits 3,4,5,7
    BRAILLE_DOTS = [
        [0x01, 0x02, 0x04, 0x40],  # Column 0: bits for rows 0,1,2,3
        [0x08, 0x10, 0x20, 0x80],  # Column 1: bits for rows 0,1,2,3
    ]

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._prices: deque[float] = deque(maxlen=MAX_PRICE_HISTORY)

    def add_price(self, price: float) -> None:
        """Add a price point to the chart."""
        self._prices.append(price)
        self.prices = list(self._prices)

    def watch_prices(self, prices: list[float]) -> None:
        """Re-render when prices change."""
        self.refresh()

    def _get_braille_char(self, dots: list[tuple[int, int]]) -> str:
        """Convert dot positions to braille character."""
        code = self.BRAILLE_BASE
        for col, row in dots:
            if 0 <= col < 2 and 0 <= row < 4:
                code |= self.BRAILLE_DOTS[col][row]
        return chr(code)

    def render(self) -> str:
        """Render the price chart using braille characters."""
        if len(self._prices) < 2:
            return "[dim]Waiting for price data...[/dim]"

        prices = list(self._prices)

        # Chart dimensions (in braille cells)
        chart_height = 10  # braille cells high (40 dot rows)
        chart_width = 30  # braille cells wide (60 dot cols)
        dot_rows = chart_height * 4
        dot_cols = chart_width * 2

        min_price = min(prices)
        max_price = max(prices)
        price_range = max_price - min_price
        if price_range == 0:
            price_range = 1.0

        # Map prices to dot coordinates
        num_points = min(len(prices), dot_cols)
        points: list[tuple[int, int]] = []

        for i in range(num_points):
            price_idx = len(prices) - num_points + i
            price = prices[price_idx]

            x = i
            # Invert y so higher prices are at top
            y = int((1 - (price - min_price) / price_range) * (dot_rows - 1))
            y = max(0, min(dot_rows - 1, y))
            points.append((x, y))

        # Create dot grid
        grid: list[list[int]] = [[0] * chart_width for _ in range(chart_height)]

        # Draw line between consecutive points
        for i in range(len(points) - 1):
            x0, y0 = points[i]
            x1, y1 = points[i + 1]

            # Bresenham's line algorithm
            dx = abs(x1 - x0)
            dy = abs(y1 - y0)
            sx = 1 if x0 < x1 else -1
            sy = 1 if y0 < y1 else -1
            err = dx - dy

            x, y = x0, y0
            while True:
                # Set dot in grid
                cell_x = x // 2
                cell_y = y // 4
                dot_x = x % 2
                dot_y = y % 4

                if 0 <= cell_x < chart_width and 0 <= cell_y < chart_height:
                    grid[cell_y][cell_x] |= self.BRAILLE_DOTS[dot_x][dot_y]

                if x == x1 and y == y1:
                    break

                e2 = 2 * err
                if e2 > -dy:
                    err -= dy
                    x += sx
                if e2 < dx:
                    err += dx
                    y += sy

        # Build output with y-axis labels
        lines: list[str] = []

        # Current price indicator
        current = prices[-1]
        change = current - prices[0] if len(prices) > 1 else 0
        change_pct = (change / prices[0] * 100) if prices[0] != 0 else 0
        color = "green" if change >= 0 else "red"

        lines.append(f"[bold]${current:,.2f}[/bold] [{color}]{change:+.2f} ({change_pct:+.1f}%)[/{color}]")
        lines.append("")

        for row_idx, row in enumerate(grid):
            # Y-axis label (show price at this row)
            row_price = max_price - (row_idx / (chart_height - 1)) * price_range
            label = f"[dim]${row_price:>7.2f}[/dim] │"

            # Convert dots to braille characters with color
            chars: list[str] = []
            for cell in row:
                if cell == 0:
                    chars.append(" ")
                else:
                    char = chr(self.BRAILLE_BASE | cell)
                    chars.append(f"[{color}]{char}[/{color}]")

            lines.append(label + "".join(chars))

        # X-axis
        lines.append("[dim]" + "─" * 10 + "┴" + "─" * chart_width + "[/dim]")

        return "\n".join(lines)


class StatsPanel(Static):  # type: ignore[misc]
    """Statistics panel showing trading metrics."""

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._symbol = "---"
        self._price = 0.0
        self._trend = "---"
        self._signal = "HOLD"
        self._position: Position | None = None
        self._pnl = 0.0
        self._trades = 0
        self._winners = 0
        self._losers = 0

    def update_stats(
        self,
        symbol: str | None = None,
        price: float | None = None,
        trend: str | None = None,
        signal: str | None = None,
        position: Position | None = None,
        pnl: float | None = None,
        trades: int | None = None,
        winners: int | None = None,
        losers: int | None = None,
        clear_position: bool = False,
    ) -> None:
        """Update statistics."""
        if symbol is not None:
            self._symbol = symbol
        if price is not None:
            self._price = price
        if trend is not None:
            self._trend = trend
        if signal is not None:
            self._signal = signal
        if position is not None:
            self._position = position
        if clear_position:
            self._position = None
        if pnl is not None:
            self._pnl = pnl
        if trades is not None:
            self._trades = trades
        if winners is not None:
            self._winners = winners
        if losers is not None:
            self._losers = losers
        self.refresh()

    def render(self) -> str:
        """Render the stats panel."""
        # Signal color
        signal_display = {
            "BUY": "[green]▲ BUY[/green]",
            "SELL": "[red]▼ SELL[/red]",
            "HOLD": "[dim]● HOLD[/dim]",
        }.get(self._signal, self._signal)

        # Trend color
        trend_display = {
            "BULLISH": "[green]↑ BULLISH[/green]",
            "BEARISH": "[red]↓ BEARISH[/red]",
        }.get(self._trend, f"[dim]{self._trend}[/dim]")

        # P&L color
        pnl_color = "green" if self._pnl >= 0 else "red"

        # Win rate
        win_rate = self._winners / self._trades * 100 if self._trades > 0 else 0

        lines = [
            f"[bold]{self._symbol}[/bold]",
            "",
            f"Price:    [bold]${self._price:.2f}[/bold]",
            f"Trend:    {trend_display}",
            f"Signal:   {signal_display}",
            "",
            "─" * 20,
            "",
        ]

        pos = self._position
        if pos:
            direction_color = "green" if pos.direction == "LONG" else "red"
            unrealized = (self._price - pos.entry_price) * pos.size
            if pos.direction == "SHORT":
                unrealized = -unrealized
            unreal_color = "green" if unrealized >= 0 else "red"

            lines.extend(
                [
                    "[bold]Position[/bold]",
                    f"  [{direction_color}]{pos.direction}[/{direction_color}] @ ${pos.entry_price:.2f}",
                    f"  Size: {pos.size:.1f}",
                    f"  Stop: ${pos.stop_loss:.2f}",
                    f"  TP:   ${pos.take_profit:.2f}",
                    f"  P&L:  [{unreal_color}]${unrealized:+,.2f}[/{unreal_color}]",
                    "",
                    "─" * 20,
                    "",
                ]
            )

        lines.extend(
            [
                "[bold]Session[/bold]",
                f"  Trades:   {self._trades}",
                f"  Win Rate: {win_rate:.1f}%",
                f"  P&L:      [{pnl_color}]${self._pnl:+,.2f}[/{pnl_color}]",
            ]
        )

        return "\n".join(lines)


class TradingTUI(App[None]):  # type: ignore[misc]
    """Trading bot TUI application."""

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 2;
        grid-columns: 3fr 1fr;
        grid-rows: 2fr 1fr;
    }

    #chart-container {
        column-span: 1;
        row-span: 1;
        border: solid green;
        padding: 1;
    }

    #stats-container {
        column-span: 1;
        row-span: 2;
        border: solid cyan;
        padding: 1;
    }

    #log-container {
        column-span: 1;
        row-span: 1;
        border: solid yellow;
    }

    PriceChart {
        height: 100%;
    }

    StatsPanel {
        height: 100%;
    }

    RichLog {
        height: 100%;
    }

    .title {
        text-style: bold;
        color: $text;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "toggle_dark", "Toggle dark mode"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._chart: PriceChart | None = None
        self._stats: StatsPanel | None = None
        self._signal_log: RichLog | None = None

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()

        with Container(id="chart-container"):
            yield Label("Price Chart", classes="title")
            yield PriceChart(id="price-chart")

        with Container(id="stats-container"):
            yield Label("Statistics", classes="title")
            yield StatsPanel(id="stats-panel")

        with Container(id="log-container"):
            yield Label("Signals & Trades", classes="title")
            yield RichLog(id="signal-log", highlight=True, markup=True)

        yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted."""
        self._chart = self.query_one("#price-chart", PriceChart)
        self._stats = self.query_one("#stats-panel", StatsPanel)
        self._signal_log = self.query_one("#signal-log", RichLog)
        self.title = "Trading Bot"
        self.sub_title = "Live Trading"

    def action_toggle_dark(self) -> None:
        """Toggle dark mode."""
        self.theme = "textual-dark" if self.theme == "textual-light" else "textual-light"  # type: ignore[has-type]

    def log_bar(self, bar: Bar, signal: Signal, trend: str, position: Position | None = None) -> None:
        """Log a new bar update."""
        if self._chart:
            self._chart.add_price(bar.close)

        if self._stats:
            self._stats.update_stats(
                symbol=bar.symbol,
                price=bar.close,
                trend=trend,
                signal=signal.value,
                position=position,
                clear_position=position is None,
            )

    def log_signal(
        self,
        direction: Direction,
        symbol: str,
        entry: float,
        stop: float,
        tp: float,
        size: float,
        blocked: bool = False,
        reason: str = "",
        was_capped: bool = False,
    ) -> None:
        """Log a trading signal."""
        if not self._signal_log:
            return

        arrow = "🔼" if direction == "LONG" else "🔽"
        action = "BUY" if direction == "LONG" else "SELL"
        color = "green" if direction == "LONG" else "red"
        time_str = datetime.now().strftime("%H:%M:%S")

        if blocked:
            self._signal_log.write(
                f"[dim]{time_str}[/dim] [{color}]{arrow} {action} {symbol}[/{color}] [red]✗ {reason}[/red]"
            )
        else:
            capped_note = " [yellow](capped)[/yellow]" if was_capped else ""
            self._signal_log.write(
                f"[dim]{time_str}[/dim] [{color}]{arrow} {action} {size:.1f} {symbol} @ ${entry:.2f}[/{color}]{capped_note}"
            )
            self._signal_log.write(f"  [dim]Stop: ${stop:.2f}  TP: ${tp:.2f}[/dim]")

    def log_trade_close(
        self,
        direction: Direction,
        symbol: str,
        entry: float,
        exit_price: float,
        pnl: float,
        reason: str,
    ) -> None:
        """Log a trade close."""
        if not self._signal_log:
            return

        time_str = datetime.now().strftime("%H:%M:%S")
        pnl_color = "green" if pnl >= 0 else "red"
        result = "WIN" if pnl >= 0 else "LOSS"

        self._signal_log.write(f"[dim]{time_str}[/dim] [bold]CLOSED[/bold] {direction} {symbol}")
        self._signal_log.write(f"  Entry: ${entry:.2f} → Exit: ${exit_price:.2f}")
        self._signal_log.write(f"  [{pnl_color}]{result}: ${pnl:+,.2f}[/{pnl_color}] ({reason})")

    def update_session_stats(self, pnl: float, trades: int, winners: int, losers: int) -> None:
        """Update session statistics."""
        if self._stats:
            self._stats.update_stats(pnl=pnl, trades=trades, winners=winners, losers=losers)

    def log_message(self, message: str, style: str = "") -> None:
        """Log a general message."""
        if self._signal_log:
            if style:
                self._signal_log.write(f"[{style}]{message}[/{style}]")
            else:
                self._signal_log.write(message)

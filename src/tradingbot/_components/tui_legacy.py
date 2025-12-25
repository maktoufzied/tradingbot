"""Terminal UI for live trading using Textual."""

import asyncio
import contextlib
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Final, Literal

import polars as pl
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Label, ProgressBar, RichLog, Static

from tradingbot.interfaces import BrokerProtocol, DataFeedProtocol
from tradingbot.types import Bar, BrokerPosition, Direction, Position, Signal

MAX_PRICE_HISTORY: Final[int] = 60
MAX_SYMBOLS: Final[int] = 9  # Support keys 1-9 for switching
REFRESH_INTERVAL: Final[float] = 5.0


def _utc_to_local(dt: datetime) -> datetime:
    """Convert UTC datetime to local time for display."""
    if dt.tzinfo is None:
        # Assume naive datetime is UTC
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone().replace(tzinfo=None)


class PriceChart(Static):
    """Braille-based price chart widget with timestamps."""

    prices: reactive[list[tuple[datetime, float]]] = reactive(list, init=False)

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
        self._data: deque[tuple[datetime, float]] = deque(maxlen=MAX_PRICE_HISTORY)

    def add_price(self, price: float, timestamp: datetime | None = None) -> None:
        """Add a price point with timestamp."""
        ts = timestamp or datetime.now()
        self._data.append((ts, price))
        self.prices = list(self._data)

    def watch_prices(self, prices: list[tuple[datetime, float]]) -> None:
        """Re-render when prices change."""
        self.refresh()

    def render(self) -> str:
        """Render the price chart using braille characters."""
        if len(self._data) < 2:
            return "[dim]Waiting for price data...[/dim]"

        data = list(self._data)
        times = [d[0] for d in data]
        prices = [d[1] for d in data]

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

        # X-axis with timestamps (convert UTC to local time)
        first_time = _utc_to_local(times[0]).strftime("%H:%M")
        mid_time = _utc_to_local(times[len(times) // 2]).strftime("%H:%M")
        last_time = _utc_to_local(times[-1]).strftime("%H:%M")

        lines.append("[dim]" + "─" * 10 + "┴" + "─" * chart_width + "[/dim]")

        # Build X-axis: first (left), middle (center), last (right)
        padding = " " * 11  # Y-axis label width
        mid_pos = chart_width // 2 - len(mid_time) // 2
        end_pos = chart_width - len(last_time)
        # Ensure no overlap: first takes 5 chars, need gap before mid and last
        gap1 = mid_pos - len(first_time)
        gap2 = end_pos - mid_pos - len(mid_time)
        x_axis = f"{padding}{first_time}{' ' * max(1, gap1)}{mid_time}{' ' * max(1, gap2)}{last_time}"
        lines.append(f"[dim]{x_axis}[/dim]")

        return "\n".join(lines)


class StatsPanel(Static):
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


class AccountPanel(Static):
    """Real-time account information panel."""

    equity: reactive[float] = reactive(0.0)
    cash: reactive[float] = reactive(0.0)
    buying_power: reactive[float] = reactive(0.0)
    start_equity: reactive[float] = reactive(0.0)

    def watch_equity(self, value: float) -> None:
        self.refresh()

    def watch_cash(self, value: float) -> None:
        self.refresh()

    def watch_buying_power(self, value: float) -> None:
        self.refresh()

    def render(self) -> str:
        day_pnl = self.equity - self.start_equity if self.start_equity > 0 else 0.0
        day_pnl_pct = (day_pnl / self.start_equity * 100) if self.start_equity > 0 else 0.0
        pnl_color = "green" if day_pnl >= 0 else "red"

        return "\n".join(
            [
                "[bold]Account[/bold]",
                "─" * 22,
                f"Equity:    [bold]${self.equity:,.2f}[/bold]",
                f"Cash:      ${self.cash:,.2f}",
                f"Buy Power: ${self.buying_power:,.2f}",
                f"Day P&L:   [{pnl_color}]${day_pnl:+,.2f} ({day_pnl_pct:+.1f}%)[/{pnl_color}]",
            ]
        )


class PositionsPanel(Static):
    """List of all open positions with real-time P&L."""

    positions: reactive[list[BrokerPosition]] = reactive(list)

    def watch_positions(self, positions: list[BrokerPosition]) -> None:
        self.refresh()

    def render(self) -> str:
        lines = [
            f"[bold]Positions ({len(self.positions)})[/bold]",
            "─" * 22,
        ]

        if not self.positions:
            lines.append("[dim]No open positions[/dim]")
            return "\n".join(lines)

        for pos in self.positions:
            dir_color = "green" if pos.direction == "LONG" else "red"
            pnl_color = "green" if pos.unrealized_pnl >= 0 else "red"
            pnl_pct = (pos.unrealized_pnl / (pos.avg_entry_price * pos.size) * 100) if pos.size > 0 else 0

            lines.extend(
                [
                    f"[{dir_color}]{pos.symbol} {pos.direction}[/{dir_color}] {pos.size:.0f} @ ${pos.avg_entry_price:.2f}",
                    f"  P&L: [{pnl_color}]${pos.unrealized_pnl:+,.2f} ({pnl_pct:+.1f}%)[/{pnl_color}]",
                ]
            )

        return "\n".join(lines)


class AggregationPanel(Static):
    """Shows raw 1m bar aggregation progress."""

    symbol: reactive[str] = reactive("")
    price: reactive[float] = reactive(0.0)
    collected: reactive[int] = reactive(0)
    target: reactive[int] = reactive(5)

    def watch_collected(self, value: int) -> None:
        self.refresh()

    def watch_price(self, value: float) -> None:
        self.refresh()

    def render(self) -> str:
        # Show waiting state if no data yet
        if not self.symbol:
            return "[bold]Live Feed[/bold]\n[dim]Waiting for 1m bars...[/dim]"

        # No aggregation needed for 1m interval
        if self.target <= 1:
            return f"[bold]Live Feed[/bold] {self.symbol}\n[cyan]${self.price:.2f}[/cyan]"

        # Progress bar for aggregation
        filled = self.collected
        empty = self.target - self.collected
        bar = "[cyan]█[/cyan]" * filled + "[dim]░[/dim]" * empty

        return (
            f"[bold]Live Feed[/bold] {self.symbol}\n"
            f"[cyan]${self.price:.2f}[/cyan]  {bar} {self.collected}/{self.target}"
        )


class SymbolTabs(Static):
    """Tab bar for switching between symbols."""

    symbols: reactive[list[str]] = reactive(list, init=False)
    active_index: reactive[int] = reactive(0)
    # Per-symbol data: signal, price, direction (for position indicator)
    symbol_data: reactive[dict[str, tuple[str, float, str | None]]] = reactive(dict, init=False)

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._symbols: list[str] = []
        self._active = 0
        self._data: dict[str, tuple[str, float, str | None]] = {}

    def set_symbols(self, symbols: list[str]) -> None:
        """Set the list of symbols."""
        self._symbols = symbols[:MAX_SYMBOLS]
        self.symbols = self._symbols
        self.refresh()

    def set_active(self, index: int) -> None:
        """Set the active symbol index."""
        if 0 <= index < len(self._symbols):
            self._active = index
            self.active_index = index
            self.refresh()

    def update_symbol_data(self, symbol: str, signal: str, price: float, direction: str | None = None) -> None:
        """Update display data for a symbol."""
        self._data[symbol] = (signal, price, direction)
        self.symbol_data = self._data.copy()
        self.refresh()

    def watch_symbols(self, symbols: list[str]) -> None:
        self.refresh()

    def watch_active_index(self, index: int) -> None:
        self.refresh()

    def render(self) -> str:
        if not self._symbols:
            return ""

        tabs: list[str] = []
        for i, symbol in enumerate(self._symbols):
            key = i + 1
            signal, price, direction = self._data.get(symbol, ("HOLD", 0.0, None))

            # Signal indicator
            if direction == "LONG":
                indicator = "[green]▲[/green]"
            elif direction == "SHORT":
                indicator = "[red]▼[/red]"
            elif signal == "BUY":
                indicator = "[green]●[/green]"
            elif signal == "SELL":
                indicator = "[red]●[/red]"
            else:
                indicator = "[dim]●[/dim]"

            # Format price
            price_str = f"${price:.2f}" if price > 0 else ""

            # Active tab styling
            if i == self._active:
                tabs.append(f"[reverse] [{key}] {symbol} {price_str} {indicator} [/reverse]")
            else:
                tabs.append(f"[dim][{key}][/dim] {symbol} {price_str} {indicator}")

        return " │ ".join(tabs)


class StatusBar(Static):
    """Bottom status bar with clock and connection info."""

    time_str: reactive[str] = reactive("")
    feed_status: reactive[str] = reactive("Disconnected")
    broker_status: reactive[str] = reactive("Disconnected")
    market_status: reactive[str] = reactive("")

    def on_mount(self) -> None:
        self.set_interval(1, self._update_time)

    def _update_time(self) -> None:
        self.time_str = datetime.now().strftime("%H:%M:%S")

    def watch_time_str(self, value: str) -> None:
        self.refresh()

    def watch_feed_status(self, value: str) -> None:
        self.refresh()

    def watch_broker_status(self, value: str) -> None:
        self.refresh()

    def watch_market_status(self, value: str) -> None:
        self.refresh()

    def render(self) -> str:
        feed_color = "green" if self.feed_status == "Connected" else "red"
        broker_color = "green" if self.broker_status == "Connected" else "red"

        parts = [
            f"[bold]{self.time_str}[/bold]",
            f"Feed: [{feed_color}]{self.feed_status}[/{feed_color}]",
            f"Broker: [{broker_color}]{self.broker_status}[/{broker_color}]",
        ]

        if self.market_status:
            parts.append(self.market_status)

        return " │ ".join(parts)


class LoadingScreen(ModalScreen[None]):
    """Modal screen showing cache population progress."""

    CSS = """
    LoadingScreen {
        align: center middle;
    }

    #loading-container {
        width: 80;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #loading-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #loading-progress {
        margin: 1 0;
    }

    #loading-status {
        height: auto;
        max-height: 10;
    }

    .symbol-status {
        margin-left: 2;
    }
    """

    def __init__(self, symbols: list[str], on_ready: Callable[[], None] | None = None) -> None:
        super().__init__()
        self._symbols = symbols
        self._status_labels: dict[str, Label] = {}
        self._on_ready = on_ready

    def compose(self) -> ComposeResult:
        with Container(id="loading-container"):
            yield Label("Populating Cache", id="loading-title")
            yield ProgressBar(id="loading-progress", total=len(self._symbols), show_eta=False)
            with Container(id="loading-status"):
                for symbol in self._symbols:
                    label = Label(f"  {symbol}: [dim]waiting...[/dim]", classes="symbol-status")
                    self._status_labels[symbol] = label
                    yield label

    def on_mount(self) -> None:
        """Called when screen is mounted - start the cache population."""
        if self._on_ready:
            self._on_ready()

    def update_symbol(self, symbol: str, status: str, style: str = "") -> None:
        """Update the status of a symbol."""
        if symbol in self._status_labels:
            styled = f"[{style}]{status}[/{style}]" if style else status
            self._status_labels[symbol].update(f"  {symbol}: {styled}")

    def advance_progress(self) -> None:
        """Advance the progress bar by one step."""
        try:
            progress = self.query_one("#loading-progress", ProgressBar)
            progress.advance(1)
        except Exception:
            pass  # Screen might be dismissed


class TradingTUI(App[None]):
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

    #right-panel {
        column-span: 1;
        row-span: 2;
        layout: vertical;
    }

    #account-container {
        height: auto;
        border: solid blue;
        padding: 1;
    }

    #positions-container {
        height: auto;
        border: solid magenta;
        padding: 1;
    }

    #aggregation-container {
        height: auto;
        border: solid $primary;
        padding: 1;
    }

    #stats-container {
        height: 1fr;
        border: solid cyan;
        padding: 1;
    }

    #log-container {
        column-span: 1;
        row-span: 1;
        border: solid yellow;
        layout: vertical;
    }

    #symbol-tabs {
        height: 1;
        background: $surface-darken-2;
        padding: 0 1;
    }

    #status-bar {
        height: 1;
        dock: bottom;
        background: $surface-darken-1;
        padding: 0 1;
    }

    PriceChart {
        height: 100%;
    }

    StatsPanel {
        height: 100%;
    }

    RichLog {
        height: 1fr;
    }

    .title {
        text-style: bold;
        color: $text;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "toggle_dark", "Dark mode"),
        ("r", "refresh", "Refresh"),
        ("1", "switch_symbol(0)", "Symbol 1"),
        ("2", "switch_symbol(1)", "Symbol 2"),
        ("3", "switch_symbol(2)", "Symbol 3"),
        ("4", "switch_symbol(3)", "Symbol 4"),
        ("5", "switch_symbol(4)", "Symbol 5"),
        ("6", "switch_symbol(5)", "Symbol 6"),
        ("7", "switch_symbol(6)", "Symbol 7"),
        ("8", "switch_symbol(7)", "Symbol 8"),
        ("9", "switch_symbol(8)", "Symbol 9"),
    ]

    def __init__(self, broker: BrokerProtocol | None = None, symbols: list[str] | None = None) -> None:
        super().__init__()
        self._broker = broker
        self._symbols = symbols or []
        self._active_symbol_idx = 0
        self._chart: PriceChart | None = None
        self._chart_title: Label | None = None
        self._stats: StatsPanel | None = None
        self._signal_log: RichLog | None = None
        self._account_panel: AccountPanel | None = None
        self._positions_panel: PositionsPanel | None = None
        self._aggregation_panel: AggregationPanel | None = None
        self._symbol_tabs: SymbolTabs | None = None
        self._status_bar: StatusBar | None = None
        self._start_equity = 0.0
        self._cache_loaded_symbols: set[str] = set()
        self._loading_screen: LoadingScreen | None = None

        # Per-symbol data storage
        self._symbol_charts: dict[str, deque[tuple[datetime, float]]] = {}
        self._symbol_signals: dict[str, str] = {}  # symbol -> last signal
        self._symbol_positions: dict[str, Position | None] = {}  # symbol -> position
        self._symbol_aggregation: dict[str, tuple[float, int, int]] = {}  # symbol -> (price, collected, target)

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()

        with Container(id="chart-container"):
            yield Label("Price Chart", classes="title", id="chart-title")
            yield PriceChart(id="price-chart")

        with Container(id="right-panel"):
            with Container(id="account-container"):
                yield AccountPanel(id="account-panel")

            with Container(id="positions-container"):
                yield PositionsPanel(id="positions-panel")

            with Container(id="aggregation-container"):
                yield AggregationPanel(id="aggregation-panel")

            with Container(id="stats-container"):
                yield Label("Session", classes="title")
                yield StatsPanel(id="stats-panel")

        with Container(id="log-container"):
            yield Label("Signals & Trades", classes="title")
            yield RichLog(id="signal-log", highlight=True, markup=True)
            yield SymbolTabs(id="symbol-tabs")
            yield StatusBar(id="status-bar")

        yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted."""
        self._chart = self.query_one("#price-chart", PriceChart)
        self._stats = self.query_one("#stats-panel", StatsPanel)
        self._signal_log = self.query_one("#signal-log", RichLog)
        self._account_panel = self.query_one("#account-panel", AccountPanel)
        self._positions_panel = self.query_one("#positions-panel", PositionsPanel)
        self._aggregation_panel = self.query_one("#aggregation-panel", AggregationPanel)
        self._symbol_tabs = self.query_one("#symbol-tabs", SymbolTabs)
        self._status_bar = self.query_one("#status-bar", StatusBar)
        self._chart_title = self.query_one("#chart-title", Label)
        self.title = "Trading Bot"
        self.sub_title = "Live Trading"

        # Initialize per-symbol data storage
        for symbol in self._symbols:
            self._symbol_charts[symbol] = deque(maxlen=MAX_PRICE_HISTORY)
            self._symbol_signals[symbol] = "HOLD"
            self._symbol_positions[symbol] = None

        # Initialize symbol tabs
        if self._symbol_tabs and self._symbols:
            self._symbol_tabs.set_symbols(self._symbols)
            self._update_chart_title()

        if self._broker:
            self.run_worker(self._account_refresh_loop, exclusive=False)  # type: ignore[arg-type]
            self._status_bar.broker_status = "Connected"

        # Show loading screen and populate cache
        if self._symbols:

            def start_cache_worker() -> None:
                self.run_worker(self._populate_cache_with_progress, exclusive=False)  # type: ignore[arg-type]

            self._loading_screen = LoadingScreen(self._symbols, on_ready=start_cache_worker)
            self.push_screen(self._loading_screen)

    async def _populate_cache_with_progress(self) -> None:
        """Populate cache for all symbols with progress updates."""
        import io
        import sys

        if not self._loading_screen:
            return

        loading_screen = self._loading_screen  # Local reference for type checker

        from tradingbot import get_feed_registry
        from tradingbot.config import get_engine_config

        from .cache.db import get_date_range, insert_bars, query_bars

        engine_cfg = get_engine_config()
        interval = engine_cfg.bar_interval

        # Get today's local midnight in UTC
        local_midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        local_tz = datetime.now().astimezone().tzinfo
        today_start_utc = local_midnight.replace(tzinfo=local_tz).astimezone(UTC).replace(tzinfo=None)
        now_utc = datetime.now(UTC).replace(tzinfo=None)

        feed = None
        has_errors = False

        for symbol in self._symbols:
            try:
                # Update modal status
                loading_screen.update_symbol(symbol, "checking cache...", "dim")

                # Check cache status
                _, cached_end = await asyncio.to_thread(get_date_range, symbol, interval)

                need_fetch = False
                fetch_start = today_start_utc

                if cached_end is None or cached_end < today_start_utc:
                    need_fetch = True
                elif (now_utc - cached_end).total_seconds() > 300:
                    need_fetch = True
                    fetch_start = cached_end

                if need_fetch:
                    loading_screen.update_symbol(symbol, f"fetching from {engine_cfg.feed}...", "yellow")

                    # Lazy-load feed
                    if feed is None:
                        feed = get_feed_registry().get(engine_cfg.feed)
                    current_feed = feed  # Capture for closure with correct type

                    # Fetch in thread to not block UI (suppress print output)
                    def fetch_with_suppressed_output(
                        f: DataFeedProtocol = current_feed,
                        sym: str = symbol,
                        start: datetime = fetch_start,
                    ) -> pl.DataFrame:
                        old_stdout = sys.stdout
                        sys.stdout = io.StringIO()
                        try:
                            return f.history(
                                sym,
                                start.isoformat(),
                                now_utc.isoformat(),
                                "1d",
                                interval,
                            )
                        finally:
                            sys.stdout = old_stdout

                    df_new = await asyncio.to_thread(fetch_with_suppressed_output)

                    if not df_new.is_empty():
                        await asyncio.to_thread(insert_bars, df_new, symbol, interval, engine_cfg.feed)
                        loading_screen.update_symbol(symbol, f"fetched {len(df_new)} bars", "green")
                    else:
                        loading_screen.update_symbol(symbol, "no new data", "dim")
                else:
                    loading_screen.update_symbol(symbol, "cache up to date", "green")

                # Load bars into chart
                df = await asyncio.to_thread(query_bars, symbol, interval, today_start_utc)
                if not df.is_empty():
                    for row in df.iter_rows(named=True):
                        ts = row["datetime"]
                        price = float(row["close"])
                        self._symbol_charts[symbol].append((ts, price))

                    # Update visible chart if this is the active symbol
                    is_active = self._symbols and self._symbols[self._active_symbol_idx] == symbol
                    if is_active and self._chart:
                        for ts, price in self._symbol_charts[symbol]:
                            self._chart.add_price(price, ts)

                self._cache_loaded_symbols.add(symbol)

            except Exception as e:
                # Show more of the error message (80 chars)
                err_msg = str(e)[:80] + "..." if len(str(e)) > 80 else str(e)
                loading_screen.update_symbol(symbol, f"error: {err_msg}", "red")
                has_errors = True

            # Advance progress bar
            loading_screen.advance_progress()

        # Longer delay if there were errors so user can read them
        await asyncio.sleep(3.0 if has_errors else 0.5)
        self.pop_screen()

    async def _account_refresh_loop(self) -> None:
        """Periodically refresh account and positions from broker."""
        while True:
            with contextlib.suppress(Exception):
                await self._refresh_account()
            await asyncio.sleep(REFRESH_INTERVAL)

    async def _refresh_account(self) -> None:
        """Fetch latest account info from broker."""
        if not self._broker:
            return

        account = self._broker.get_account()
        positions = self._broker.get_positions()
        clock = self._broker.get_clock()

        if self._start_equity == 0.0:
            self._start_equity = account.equity

        if self._account_panel:
            self._account_panel.equity = account.equity
            self._account_panel.cash = account.cash
            self._account_panel.buying_power = account.buying_power
            self._account_panel.start_equity = self._start_equity

        if self._positions_panel:
            self._positions_panel.positions = positions

        if self._status_bar and clock:
            if clock.is_open:
                if clock.next_close:
                    close_local = _utc_to_local(clock.next_close)
                    self._status_bar.market_status = (
                        f"[green]Market Open[/green] (closes {close_local.strftime('%H:%M')})"
                    )
                else:
                    self._status_bar.market_status = "[green]Market Open[/green]"
            else:
                if clock.next_open:
                    open_local = _utc_to_local(clock.next_open)
                    self._status_bar.market_status = f"[red]Market Closed[/red] (opens {open_local.strftime('%H:%M')})"
                else:
                    self._status_bar.market_status = "[red]Market Closed[/red]"

    def action_toggle_dark(self) -> None:
        """Toggle dark mode."""
        self.theme = "textual-dark" if self.theme == "textual-light" else "textual-light"

    def action_refresh(self) -> None:
        """Manually refresh account and positions."""
        if self._broker:
            self.run_worker(self._refresh_account, exclusive=False)  # type: ignore[arg-type]
            self.notify("Refreshed", severity="information")
        else:
            self.notify("No broker connected", severity="warning")

    def action_switch_symbol(self, index: int) -> None:
        """Switch to a different symbol by index."""
        if index >= len(self._symbols):
            return

        self._active_symbol_idx = index
        symbol = self._symbols[index]

        # Update symbol tabs
        if self._symbol_tabs:
            self._symbol_tabs.set_active(index)

        # Update chart title
        self._update_chart_title()

        # Reload chart data for this symbol
        self._switch_chart_to_symbol(symbol)

        # Update stats panel with current symbol data
        if self._stats:
            signal = self._symbol_signals.get(symbol, "HOLD")
            position = self._symbol_positions.get(symbol)
            prices = self._symbol_charts.get(symbol, deque())
            price = prices[-1][1] if prices else 0.0
            self._stats.update_stats(
                symbol=symbol,
                price=price,
                signal=signal,
                position=position,
                clear_position=position is None,
            )

        # Update aggregation panel with current symbol data
        if self._aggregation_panel and symbol in self._symbol_aggregation:
            agg_price, collected, target = self._symbol_aggregation[symbol]
            self._aggregation_panel.symbol = symbol
            self._aggregation_panel.price = agg_price
            self._aggregation_panel.collected = collected
            self._aggregation_panel.target = target

    def _update_chart_title(self) -> None:
        """Update the chart title with the active symbol."""
        if hasattr(self, "_chart_title") and self._chart_title and self._symbols:
            symbol = self._symbols[self._active_symbol_idx]
            self._chart_title.update(f"Price Chart: [bold]{symbol}[/bold]")

    def _switch_chart_to_symbol(self, symbol: str) -> None:
        """Switch the chart display to a different symbol."""
        if not self._chart:
            return

        # Clear current chart
        self._chart._data.clear()

        # Load data from symbol's history
        symbol_data = self._symbol_charts.get(symbol, deque())
        for ts, price in symbol_data:
            self._chart._data.append((ts, price))

        # Trigger refresh
        self._chart.prices = list(self._chart._data)

    def set_feed_status(self, connected: bool) -> None:
        """Update feed connection status."""
        if self._status_bar:
            self._status_bar.feed_status = "Connected" if connected else "Disconnected"

    def set_broker_status(self, connected: bool) -> None:
        """Update broker connection status."""
        if self._status_bar:
            self._status_bar.broker_status = "Connected" if connected else "Disconnected"

    def log_bar(self, bar: Bar, signal: Signal, trend: str, position: Position | None = None) -> None:
        """Log a new bar update."""
        symbol = bar.symbol

        # Initialize storage if needed
        if symbol not in self._symbol_charts:
            self._symbol_charts[symbol] = deque(maxlen=MAX_PRICE_HISTORY)

        # Store in per-symbol data
        self._symbol_charts[symbol].append((bar.datetime, bar.close))
        self._symbol_signals[symbol] = signal.value
        self._symbol_positions[symbol] = position

        # Update symbol tabs with latest data
        if self._symbol_tabs:
            direction = position.direction if position else None
            self._symbol_tabs.update_symbol_data(symbol, signal.value, bar.close, direction)

        # Only update visible chart if this is the active symbol
        is_active = self._symbols and self._symbols[self._active_symbol_idx] == symbol
        if is_active:
            if self._chart:
                self._chart.add_price(bar.close, bar.datetime)

            if self._stats:
                self._stats.update_stats(
                    symbol=bar.symbol,
                    price=bar.close,
                    trend=trend,
                    signal=signal.value,
                    position=position,
                    clear_position=position is None,
                )

        self.set_feed_status(True)

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
        """Log a trading signal with visual notification."""
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
            self.notify(f"{action} {symbol} @ ${entry:.2f}", title="Signal", severity="information")

    def log_trade_close(
        self,
        direction: Direction,
        symbol: str,
        entry: float,
        exit_price: float,
        pnl: float,
        reason: str,
    ) -> None:
        """Log a trade close with result notification."""
        if not self._signal_log:
            return

        time_str = datetime.now().strftime("%H:%M:%S")
        pnl_color = "green" if pnl >= 0 else "red"
        result = "WIN" if pnl >= 0 else "LOSS"

        self._signal_log.write(f"[dim]{time_str}[/dim] [bold]CLOSED[/bold] {direction} {symbol}")
        self._signal_log.write(f"  Entry: ${entry:.2f} → Exit: ${exit_price:.2f}")
        self._signal_log.write(f"  [{pnl_color}]{result}: ${pnl:+,.2f}[/{pnl_color}] ({reason})")

        severity: Literal["information", "warning", "error"] = "information" if pnl >= 0 else "error"
        self.notify(f"{symbol}: ${pnl:+,.2f}", title="Trade Closed", severity=severity)

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

    def update_aggregation(self, symbol: str, price: float, collected: int, target: int) -> None:
        """Update the bar aggregation progress display (thread-safe)."""
        if self._aggregation_panel:
            # Use call_from_thread to safely update from non-Textual threads
            self.call_from_thread(self._do_update_aggregation, symbol, price, collected, target)

    def _do_update_aggregation(self, symbol: str, price: float, collected: int, target: int) -> None:
        """Internal method to update aggregation panel on main thread."""
        # Store aggregation data for all symbols
        self._symbol_aggregation[symbol] = (price, collected, target)

        # Only show aggregation for the active symbol
        is_active = self._symbols and self._symbols[self._active_symbol_idx] == symbol
        if self._aggregation_panel and is_active:
            self._aggregation_panel.symbol = symbol
            self._aggregation_panel.price = price
            self._aggregation_panel.collected = collected
            self._aggregation_panel.target = target
        # Mark feed as connected when receiving raw bars
        self.set_feed_status(True)

"""Live trading engine for real-time trading."""

import asyncio
import contextlib
from collections import deque
from collections.abc import Mapping
from typing import Final

import polars as pl
from rich.console import Console

from ._brokers import get_registry as get_broker_registry
from ._brokers.plugins.paper import PaperBroker
from ._feeds import get_registry as get_feed_registry
from ._fetchers import DataFetcher
from .config import get_bot_config, get_live_config
from .live_risk import LiveRiskManager
from .models import Bar, Direction, Order, Position, Signal, SwingPoint
from .risk import RiskManager
from .signals import SignalGenerator
from .swing import find_swing_points

console = Console()

MIN_BARS_REQUIRED: Final[int] = 50
MAX_BARS_HISTORY: Final[int] = 500


class LiveTradingEngine:
    """Event-driven engine for live trading."""

    def __init__(
        self,
        symbols: list[str],
        broker: str | None = None,
        feed: str | None = None,
        dry_run: bool = False,
    ) -> None:
        cfg = get_bot_config()
        live_cfg = get_live_config()

        self.symbols = symbols
        self.dry_run = dry_run

        # Get broker and feed from registries
        self._broker = get_broker_registry().get(broker or live_cfg.broker)
        self._feed = get_feed_registry().get(feed or live_cfg.feed)

        # Trading components (reuse backtest logic)
        self._sig_gen = SignalGenerator(cfg.swing_lb)
        self._risk_mgr = RiskManager(cfg.capital, cfg.risk_pct, cfg.rr_ratio)

        # Live risk controls
        self._live_risk = LiveRiskManager(live_cfg.risk, cfg.capital)

        # State tracking
        self._positions: dict[str, Position] = {}
        self._bars: dict[str, deque[Bar]] = {sym: deque(maxlen=MAX_BARS_HISTORY) for sym in symbols}
        self._running = False

    async def start(self) -> None:
        """Start live trading."""
        live_cfg = get_live_config()

        console.print()
        console.rule("[bold green]LIVE TRADING ENGINE[/bold green]")
        console.print(f"Symbols: [cyan]{', '.join(self.symbols)}[/cyan]")
        console.print(f"Broker: [cyan]{self._broker.name}[/cyan]")
        console.print(f"Feed: [cyan]{self._feed.name}[/cyan]")
        console.print(f"Dry run: [yellow]{self.dry_run}[/yellow]")
        console.print()
        console.print("[bold]Risk Controls:[/bold]")
        console.print(f"  Max daily loss: [cyan]{live_cfg.risk.max_daily_loss_pct:.1%}[/cyan]")
        console.print(f"  Circuit breaker: [cyan]{live_cfg.risk.circuit_breaker_loss_pct:.1%}[/cyan]")
        console.print(f"  Max positions: [cyan]{live_cfg.risk.max_open_positions}[/cyan]")
        console.print(f"  Max position size: [cyan]{live_cfg.risk.max_position_size_pct:.1%}[/cyan]")
        console.print(f"  Trading hours only: [cyan]{live_cfg.risk.trading_hours_only}[/cyan]")
        console.print()

        # Reset daily tracking
        account = self._broker.get_account()
        self._live_risk.reset_daily(account.equity)

        # Load historical data to bootstrap
        await self._load_history()

        # Subscribe to feed
        await self._feed.subscribe(self.symbols, self._on_bar)

        # Start feed
        self._running = True
        console.print("[green]Starting live feed...[/green]")
        await self._feed.start()

    async def stop(self) -> None:
        """Stop live trading gracefully."""
        self._running = False
        await self._feed.stop()
        console.print("[yellow]Live trading stopped[/yellow]")

    async def _load_history(self) -> None:
        """Load historical data for each symbol to bootstrap indicators."""
        console.print("[dim]Loading historical data...[/dim]")

        for symbol in self.symbols:
            try:
                df: pl.DataFrame = DataFetcher.fetch(symbol, period="3mo", interval="1d")

                for row in df.iter_rows(named=True):
                    bar = Bar(
                        symbol=symbol,
                        datetime=row["datetime"],
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=int(row["volume"]),
                    )
                    self._bars[symbol].append(bar)

                console.print(f"  [green]✓[/green] {symbol}: {len(self._bars[symbol])} bars loaded")

            except Exception as e:
                console.print(f"  [red]✗[/red] {symbol}: {e}")

    async def _on_bar(self, bar: Bar) -> None:
        """Process new bar - main trading logic."""
        if not self._running:
            return

        # Update bar history
        self._bars[bar.symbol].append(bar)

        # Update broker price (for paper trading)
        if isinstance(self._broker, PaperBroker):
            self._broker.set_price(bar.symbol, bar.close)

        # Reset daily tracking if new day
        account = self._broker.get_account()
        self._live_risk.reset_daily(account.equity)

        # Check circuit breaker
        if self._live_risk.check_circuit_breaker():
            return

        # Need enough history for signals
        if len(self._bars[bar.symbol]) < MIN_BARS_REQUIRED:
            return

        # Convert bars to DataFrame for signal generation
        df = self._bars_to_df(bar.symbol)

        # Check for exit signals first
        position = self._positions.get(bar.symbol)
        if position:
            await self._check_exit(bar, position)

        # Generate entry signals
        signal, details = self._sig_gen.generate(df, len(df) - 1, position)

        self._log_bar(bar, signal, details)

        if position is None and signal in (Signal.BUY, Signal.SELL):
            await self._open_position(bar, signal, df)

    def _bars_to_df(self, symbol: str) -> pl.DataFrame:
        """Convert bar deque to DataFrame."""
        bars = list(self._bars[symbol])
        return pl.DataFrame(
            {
                "datetime": [b.datetime for b in bars],
                "open": [b.open for b in bars],
                "high": [b.high for b in bars],
                "low": [b.low for b in bars],
                "close": [b.close for b in bars],
                "volume": [b.volume for b in bars],
            }
        )

    async def _open_position(self, bar: Bar, signal: Signal, df: pl.DataFrame) -> None:
        """Open a new position."""
        direction: Direction = "LONG" if signal == Signal.BUY else "SHORT"
        price = bar.close
        idx = len(df) - 1

        # Calculate stop and size
        swings: list[SwingPoint] = find_swing_points(df, self._sig_gen.swing_lookback)
        stop = self._risk_mgr.calc_stop(direction, price, df, idx, swings)
        tp = self._risk_mgr.calc_tp(direction, price, stop)
        size = self._risk_mgr.calc_size(price, stop)
        position_value = price * size

        # Check live risk rules
        account = self._broker.get_account()
        self._live_risk.update_position_count(len(self._positions))
        can_trade, reason = self._live_risk.can_open_position(position_value, account.equity)

        console.print()
        console.print(
            f"[bold cyan]{'🔼' if direction == 'LONG' else '🔽'} {direction} SIGNAL: {bar.symbol}[/bold cyan]"
        )
        console.print(f"  Entry: ${price:.2f}  Stop: ${stop:.2f}  TP: ${tp:.2f}  Size: {size:.2f}")

        if not can_trade:
            console.print(f"  [red]✗ BLOCKED: {reason}[/red]")
            return

        if self.dry_run:
            console.print("  [yellow](DRY RUN - no order submitted)[/yellow]")
            return

        # Submit order
        order = Order(
            symbol=bar.symbol,
            direction=direction,
            size=size,
            order_type="MARKET",
        )

        result = self._broker.submit_order(order)

        if result.status == "FILLED":
            self._positions[bar.symbol] = Position(
                entry_price=result.filled_price or price,
                entry_index=idx,
                entry_time=bar.datetime,
                direction=direction,
                size=result.filled_size,
                stop_loss=stop,
                take_profit=tp,
                initial_stop_loss=stop,
            )
            self._live_risk.update_position_count(len(self._positions))
            console.print(f"  [green]✓ Order filled at ${result.filled_price:.2f}[/green]")
        else:
            console.print(f"  [red]✗ Order {result.status}: {result.message}[/red]")

    async def _check_exit(self, bar: Bar, position: Position) -> None:
        """Check if position should be exited."""
        should_exit = False
        exit_reason = ""

        if position.direction == "LONG":
            if bar.low <= position.stop_loss:
                should_exit = True
                exit_reason = "STOP_LOSS"
            elif bar.high >= position.take_profit:
                should_exit = True
                exit_reason = "TAKE_PROFIT"
        else:
            if bar.high >= position.stop_loss:
                should_exit = True
                exit_reason = "STOP_LOSS"
            elif bar.low <= position.take_profit:
                should_exit = True
                exit_reason = "TAKE_PROFIT"

        if should_exit:
            await self._close_position(bar, position, exit_reason)

    async def _close_position(self, bar: Bar, position: Position, reason: str) -> None:
        """Close an existing position."""
        exit_price = position.stop_loss if reason == "STOP_LOSS" else position.take_profit

        console.print()
        emoji = "🛑" if reason == "STOP_LOSS" else "✅"
        console.print(f"[bold]{emoji} EXIT {bar.symbol}: {reason}[/bold]")
        console.print(f"  Entry: ${position.entry_price:.2f}  Exit: ${exit_price:.2f}")

        if self.dry_run:
            pnl = (exit_price - position.entry_price) * position.size
            if position.direction == "SHORT":
                pnl = -pnl
            self._live_risk.record_trade_pnl(pnl)
            color = "green" if pnl > 0 else "red"
            console.print(f"  P&L: [{color}]${pnl:+,.2f}[/{color}]")
            console.print(
                f"  Daily P&L: [{color}]${self._live_risk.daily_pnl:+,.2f}[/{color}] ({self._live_risk.daily_pnl_pct:+.2%})"
            )
            console.print("  [yellow](DRY RUN - no order submitted)[/yellow]")
            del self._positions[bar.symbol]
            self._live_risk.update_position_count(len(self._positions))
            return

        # Submit closing order (opposite direction)
        close_direction: Direction = "SHORT" if position.direction == "LONG" else "LONG"
        order = Order(
            symbol=bar.symbol,
            direction=close_direction,
            size=position.size,
            order_type="MARKET",
        )

        result = self._broker.submit_order(order)

        if result.status == "FILLED":
            actual_exit = result.filled_price or exit_price
            pnl = (actual_exit - position.entry_price) * position.size
            if position.direction == "SHORT":
                pnl = -pnl
            self._live_risk.record_trade_pnl(pnl)
            color = "green" if pnl > 0 else "red"
            console.print(f"  [green]✓ Closed at ${actual_exit:.2f}[/green]")
            console.print(f"  P&L: [{color}]${pnl:+,.2f}[/{color}]")
            console.print(
                f"  Daily P&L: [{color}]${self._live_risk.daily_pnl:+,.2f}[/{color}] ({self._live_risk.daily_pnl_pct:+.2%})"
            )
            del self._positions[bar.symbol]
            self._live_risk.update_position_count(len(self._positions))

            # Check if circuit breaker triggered
            if self._live_risk.check_circuit_breaker():
                console.print("[bold red]⚠ CIRCUIT BREAKER TRIGGERED - Trading paused for today[/bold red]")
        else:
            console.print(f"  [red]✗ Close order {result.status}: {result.message}[/red]")

    def _log_bar(self, bar: Bar, signal: Signal, details: Mapping[str, object]) -> None:
        """Log incoming bar information."""
        trend = details.get("trend", "N/A")
        position = self._positions.get(bar.symbol)
        pos_str = f"[{position.direction}]" if position else ""

        signal_color = {"BUY": "green", "SELL": "red", "HOLD": "dim"}.get(signal.value, "white")

        console.print(
            f"[dim]{bar.datetime.strftime('%Y-%m-%d %H:%M')}[/dim] "
            f"{bar.symbol} ${bar.close:.2f} "
            f"[{signal_color}]{signal.value}[/{signal_color}] "
            f"[dim]{trend}[/dim] {pos_str}"
        )


async def run_live(
    symbols: list[str],
    broker: str | None = None,
    feed: str | None = None,
    dry_run: bool = False,
) -> None:
    """Run live trading engine."""
    engine = LiveTradingEngine(
        symbols=symbols,
        broker=broker,
        feed=feed,
        dry_run=dry_run,
    )

    try:
        await engine.start()
        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass  # Handled in finally
    finally:
        await engine.stop()


def main() -> None:
    """CLI entry point for live trading."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run live trading bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  tradingbot-live SPY
  tradingbot-live SPY QQQ --dry-run
  tradingbot-live AAPL --broker paper --feed polling
        """,
    )

    parser.add_argument("symbols", nargs="+", help="Symbols to trade (e.g., SPY AAPL)")
    parser.add_argument("--broker", default=None, help="Broker to use (default: from config)")
    parser.add_argument("--feed", default=None, help="Data feed to use (default: from config)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log signals without executing trades",
    )

    args = parser.parse_args()

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(
            run_live(
                symbols=args.symbols,
                broker=args.broker,
                feed=args.feed,
                dry_run=args.dry_run,
            )
        )

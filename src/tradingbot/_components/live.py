"""Live trading engine for real-time trading."""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import Mapping
from datetime import date
from typing import TYPE_CHECKING, Final

import polars as pl
from rich.console import Console

from . import sounds
from ._brokers import get_registry as get_broker_registry
from ._brokers.plugins.paper import PaperBroker
from ._feeds import get_registry as get_feed_registry
from ._feeds.plugins.replay import ReplayFeed
from ._feeds.protocol import DataFeedProtocol
from ._fetchers import DataFetcher
from .config import get_bot_config, get_live_config
from .live_risk import LiveRiskManager
from .models import Bar, Direction, Order, Position, Signal, SwingPoint
from .risk import RiskManager
from .signals import SignalGenerator
from .swing import find_swing_points

if TYPE_CHECKING:
    from .tui import TradingTUI

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
        feed_instance: DataFeedProtocol | None = None,
        dry_run: bool = False,
        tui: TradingTUI | None = None,
    ) -> None:
        cfg = get_bot_config()
        live_cfg = get_live_config()

        self.symbols = symbols
        self.dry_run = dry_run
        self._tui = tui

        # Get broker and feed from registries (or use provided feed instance)
        self._broker = get_broker_registry().get(broker or live_cfg.broker)
        self._feed = feed_instance or get_feed_registry().get(feed or live_cfg.feed)

        # Trading components (reuse backtest logic)
        self._sig_gen = SignalGenerator(cfg.swing_lb)
        self._risk_mgr = RiskManager(cfg.capital, cfg.risk_pct, cfg.rr_ratio)

        # Live risk controls
        self._live_risk = LiveRiskManager(live_cfg.risk, cfg.capital)

        # State tracking
        self._positions: dict[str, Position] = {}
        self._pending_orders: set[str] = set()  # Symbols with orders in flight
        self._bars: dict[str, deque[Bar]] = {sym: deque(maxlen=MAX_BARS_HISTORY) for sym in symbols}
        self._running = False

    async def start(self) -> None:
        """Start live trading."""
        live_cfg = get_live_config()

        if not self._tui:
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
        else:
            self._tui.log_message(f"Starting: {', '.join(self.symbols)}", "bold")
            self._tui.log_message(f"Broker: {self._broker.name}, Feed: {self._feed.name}")

        # Reset daily tracking
        account = self._broker.get_account()
        self._live_risk.reset_daily(account.equity)

        # Load historical data to bootstrap
        await self._load_history()

        # Sync existing positions from broker
        await self._sync_broker_positions()

        # Subscribe to feed
        await self._feed.subscribe(self.symbols, self._on_bar)

        # Start feed
        self._running = True
        if not self._tui:
            console.print("[green]Starting live feed...[/green]")
        else:
            self._tui.log_message("Live feed started", "green")
        await self._feed.start()

    async def stop(self) -> None:
        """Stop live trading gracefully."""
        self._running = False
        await self._feed.stop()
        self._print_session_summary()

    def _print_session_summary(self) -> None:
        """Print session performance summary."""
        console.print()
        console.rule("[bold]SESSION SUMMARY[/bold]")

        risk = self._live_risk
        trades = risk.session_trades

        if trades == 0:
            console.print("[dim]No trades executed during this session[/dim]")
            return

        pnl = risk.session_pnl
        pnl_color = "green" if pnl >= 0 else "red"

        console.print()
        console.print("[bold]Performance[/bold]")
        console.print(f"  Total Trades:    {trades}")
        console.print(f"  Winners:         {risk.session_winners}")
        console.print(f"  Losers:          {risk.session_losers}")
        console.print(f"  Win Rate:        {risk.session_win_rate:.1%}")
        console.print()
        console.print(f"  Total P&L:       [{pnl_color}]${pnl:+,.2f}[/{pnl_color}]")
        console.print(f"  Total Return:    [{pnl_color}]{risk.session_return_pct:+.2%}[/{pnl_color}]")
        console.print(f"  Profit Factor:   {risk.session_profit_factor:.2f}")
        console.print()
        console.print(f"  Starting Equity: ${risk._initial_equity:,.2f}")
        console.print(f"  Final Equity:    [{pnl_color}]${risk.final_equity:,.2f}[/{pnl_color}]")
        console.print()

    async def _load_history(self) -> None:
        """Load historical data for each symbol to bootstrap indicators."""
        if not self._tui:
            console.print("[dim]Loading historical data...[/dim]")
        else:
            self._tui.log_message("Loading historical data...", "dim")

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

                if not self._tui:
                    console.print(f"  [green]✓[/green] {symbol}: {len(self._bars[symbol])} bars loaded")
                else:
                    self._tui.log_message(f"✓ {symbol}: {len(self._bars[symbol])} bars loaded", "green")

            except Exception as e:
                if not self._tui:
                    console.print(f"  [red]✗[/red] {symbol}: {e}")
                else:
                    self._tui.log_message(f"✗ {symbol}: {e}", "red")

    async def _sync_broker_positions(self) -> None:
        """Sync existing positions from broker on startup.

        This handles the case where the bot restarts while positions are open.
        Stop/TP levels are recalculated from current market structure since
        the original values aren't persisted.
        """
        broker_positions = self._broker.get_positions()

        for bp in broker_positions:
            if bp.symbol not in self.symbols:
                continue  # Only track symbols we're monitoring

            # Calculate stop/TP from current market structure
            if bp.symbol in self._bars and len(self._bars[bp.symbol]) >= MIN_BARS_REQUIRED:
                df = self._bars_to_df(bp.symbol)
                idx = len(df) - 1
                swings = find_swing_points(df, self._sig_gen.swing_lookback)
                stop = self._risk_mgr.calc_stop(bp.direction, bp.avg_entry_price, df, idx, swings)
                tp = self._risk_mgr.calc_tp(bp.direction, bp.avg_entry_price, stop)
            else:
                # Fallback: use entry price with default risk parameters
                stop = bp.avg_entry_price * (0.98 if bp.direction == "LONG" else 1.02)
                tp = bp.avg_entry_price * (1.04 if bp.direction == "LONG" else 0.96)

            from datetime import datetime

            self._positions[bp.symbol] = Position(
                entry_price=bp.avg_entry_price,
                entry_index=0,
                entry_time=datetime.now(),  # Approximate - actual entry time unknown
                direction=bp.direction,
                size=bp.size,
                stop_loss=stop,
                take_profit=tp,
                initial_stop_loss=stop,
            )

            msg = f"⚠ Synced existing position: {bp.symbol} {bp.direction} {bp.size:.1f} @ ${bp.avg_entry_price:.2f}"
            if self._tui:
                self._tui.log_message(msg, "yellow")
            else:
                console.print(f"[yellow]{msg}[/yellow]")
                console.print(f"  [dim]Stop: ${stop:.2f}  TP: ${tp:.2f} (recalculated)[/dim]")

        if broker_positions:
            self._live_risk.update_position_count(len(self._positions))

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

        # Only open if no position AND no pending order for this symbol
        if position is None and bar.symbol not in self._pending_orders and signal in (Signal.BUY, Signal.SELL):
            await self._open_position(bar, signal, df)

        # Log bar AFTER potential position change so stats show current state
        self._log_bar(bar, signal, details)

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

        # Check live risk rules
        account = self._broker.get_account()
        self._live_risk.update_position_count(len(self._positions))
        can_trade, reason = self._live_risk.can_open_position()

        # Cap position size if needed
        size, was_capped = self._live_risk.cap_position_size(size, price, account.equity)

        if self._tui:
            blocked = not can_trade and not self.dry_run
            self._tui.log_signal(direction, bar.symbol, price, stop, tp, size, blocked, reason, was_capped)
        else:
            console.print()
            console.print(
                f"[bold cyan]{'🔼' if direction == 'LONG' else '🔽'} {direction} SIGNAL: {bar.symbol}[/bold cyan]"
            )
            console.print(f"  Entry: ${price:.2f}  Stop: ${stop:.2f}  TP: ${tp:.2f}  Size: {size:.2f}")
            if was_capped:
                console.print("  [yellow]⚠ Size capped to max position limit[/yellow]")

        if not can_trade:
            if not self.dry_run:
                if not self._tui:
                    console.print(f"  [red]✗ BLOCKED: {reason}[/red]")
                return
            if not self._tui:
                console.print(f"  [yellow]⚠ Would be blocked: {reason}[/yellow]")

        if self.dry_run:
            if not self._tui:
                console.print("  [yellow](DRY RUN - simulating trade)[/yellow]")
            # Simulate position for dry run
            self._positions[bar.symbol] = Position(
                entry_price=price,
                entry_index=idx,
                entry_time=bar.datetime,
                direction=direction,
                size=size,
                stop_loss=stop,
                take_profit=tp,
                initial_stop_loss=stop,
            )
            self._live_risk.update_position_count(len(self._positions))
            return

        # Submit order
        order = Order(
            symbol=bar.symbol,
            direction=direction,
            size=size,
            order_type="MARKET",
        )

        # Mark order as pending to prevent duplicate signals
        self._pending_orders.add(bar.symbol)

        try:
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
                sounds.play(sounds.BUY if direction == "LONG" else sounds.SELL)
            else:
                console.print(f"  [red]✗ Order {result.status}: {result.message}[/red]")
        finally:
            # Always clear pending status
            self._pending_orders.discard(bar.symbol)

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

        if not self._tui:
            console.print()
            emoji = "🛑" if reason == "STOP_LOSS" else "✅"
            console.print(f"[bold]{emoji} EXIT {bar.symbol}: {reason}[/bold]")
            console.print(f"  Entry: ${position.entry_price:.2f}  Exit: ${exit_price:.2f}")

        if self.dry_run:
            pnl = (exit_price - position.entry_price) * position.size
            if position.direction == "SHORT":
                pnl = -pnl
            self._live_risk.record_trade_pnl(pnl)

            if self._tui:
                self._tui.log_trade_close(position.direction, bar.symbol, position.entry_price, exit_price, pnl, reason)
                self._tui.update_session_stats(
                    pnl=self._live_risk.session_pnl,
                    trades=self._live_risk.session_trades,
                    winners=self._live_risk.session_winners,
                    losers=self._live_risk.session_losers,
                )
            else:
                color = "green" if pnl > 0 else "red"
                console.print(f"  P&L: [{color}]${pnl:+,.2f}[/{color}]")
                console.print(
                    f"  Daily P&L: [{color}]${self._live_risk.daily_pnl:+,.2f}[/{color}] ({self._live_risk.daily_pnl_pct:+.2%})"
                )
                console.print("  [yellow](DRY RUN - no order submitted)[/yellow]")

            sounds.play(sounds.PROFIT if pnl > 0 else sounds.LOSS)
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

            if self._tui:
                self._tui.log_trade_close(
                    position.direction, bar.symbol, position.entry_price, actual_exit, pnl, reason
                )
                self._tui.update_session_stats(
                    pnl=self._live_risk.session_pnl,
                    trades=self._live_risk.session_trades,
                    winners=self._live_risk.session_winners,
                    losers=self._live_risk.session_losers,
                )
            else:
                color = "green" if pnl > 0 else "red"
                console.print(f"  [green]✓ Closed at ${actual_exit:.2f}[/green]")
                console.print(f"  P&L: [{color}]${pnl:+,.2f}[/{color}]")
                console.print(
                    f"  Daily P&L: [{color}]${self._live_risk.daily_pnl:+,.2f}[/{color}] ({self._live_risk.daily_pnl_pct:+.2%})"
                )

            sounds.play(sounds.PROFIT if pnl > 0 else sounds.LOSS)
            del self._positions[bar.symbol]
            self._live_risk.update_position_count(len(self._positions))

            # Check if circuit breaker triggered
            if self._live_risk.check_circuit_breaker():
                if self._tui:
                    self._tui.log_message("⚠ CIRCUIT BREAKER TRIGGERED - Trading paused", "bold red")
                else:
                    console.print("[bold red]⚠ CIRCUIT BREAKER TRIGGERED - Trading paused for today[/bold red]")
        else:
            if self._tui:
                self._tui.log_message(f"✗ Close order {result.status}: {result.message}", "red")
            else:
                console.print(f"  [red]✗ Close order {result.status}: {result.message}[/red]")

    def _log_bar(self, bar: Bar, signal: Signal, details: Mapping[str, object]) -> None:
        """Log incoming bar information."""
        trend = details.get("trend", "N/A")
        position = self._positions.get(bar.symbol)
        trend_str = str(trend)

        if self._tui:
            self._tui.log_bar(bar, signal, trend_str, position)
            self._tui.update_session_stats(
                pnl=self._live_risk.session_pnl,
                trades=self._live_risk.session_trades,
                winners=self._live_risk.session_winners,
                losers=self._live_risk.session_losers,
            )
        else:
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
    feed_instance: DataFeedProtocol | None = None,
    dry_run: bool = False,
    tui: TradingTUI | None = None,
) -> None:
    """Run live trading engine."""
    engine = LiveTradingEngine(
        symbols=symbols,
        broker=broker,
        feed=feed,
        feed_instance=feed_instance,
        dry_run=dry_run,
        tui=tui,
    )

    try:
        await engine.start()
        # Keep running until interrupted or replay finishes
        while engine._feed.is_connected:
            await asyncio.sleep(0.1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass  # Handled in finally
    finally:
        await engine.stop()


def _parse_date(date_str: str) -> date:
    """Parse date string in YYYY-MM-DD format."""
    from datetime import datetime

    return datetime.strptime(date_str, "%Y-%m-%d").date()


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

Replay mode (simulate live trading with historical data):
  tradingbot-live SPY --replay
  tradingbot-live SPY --replay --speed 10
  tradingbot-live SPY --replay --speed 0
  tradingbot-live SPY --replay --from 2024-01-01 --to 2024-06-30
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

    # Replay mode options
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Replay historical data as if it were live",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Replay speed: bars per second (0 = instant, default: 1.0)",
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        type=_parse_date,
        default=None,
        help="Replay start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        type=_parse_date,
        default=None,
        help="Replay end date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--period",
        default="1d",
        help="Historical period for replay (default: 1d)",
    )
    parser.add_argument(
        "--interval",
        default="15m",
        help="Bar interval for replay (default: 15m)",
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Run with terminal UI (interactive dashboard)",
    )
    args = parser.parse_args()

    # Support both space and comma-separated symbols: "BE MSFT" or "BE,MSFT"
    symbols: list[str] = []
    for sym in args.symbols:
        symbols.extend(s.strip().upper() for s in sym.split(",") if s.strip())

    # Create replay feed if requested
    feed_instance: DataFeedProtocol | None = None
    if args.replay:
        feed_instance = ReplayFeed(
            speed=args.speed,
            start_date=args.from_date,
            end_date=args.to_date,
            period=args.period,
            interval=args.interval,
        )

    if args.tui:
        _run_with_tui(
            symbols=symbols,
            broker=args.broker,
            feed=args.feed,
            feed_instance=feed_instance,
            dry_run=args.dry_run,
        )
    else:
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(
                run_live(
                    symbols=symbols,
                    broker=args.broker,
                    feed=args.feed,
                    feed_instance=feed_instance,
                    dry_run=args.dry_run,
                )
            )


def _run_with_tui(
    symbols: list[str],
    broker: str | None,
    feed: str | None,
    feed_instance: DataFeedProtocol | None,
    dry_run: bool,
) -> None:
    """Run live trading with TUI."""
    from .tui import TradingTUI

    class TradingApp(TradingTUI):
        """TUI app with trading engine worker."""

        def on_mount(self) -> None:
            """Start trading engine when app mounts."""
            super().on_mount()
            self.run_worker(self._run_engine, exclusive=True)

        async def _run_engine(self) -> None:
            """Run the trading engine."""
            await run_live(
                symbols=symbols,
                broker=broker,
                feed=feed,
                feed_instance=feed_instance,
                dry_run=dry_run,
                tui=self,
            )

    app = TradingApp()
    app.run()

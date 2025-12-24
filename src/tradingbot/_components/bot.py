import asyncio
from collections.abc import Callable
from datetime import datetime
from statistics import mean
from typing import Any, TypedDict

import plotext as plt
import polars as pl

from tradingbot.types import Direction, ExitReason, Position, Signal, SwingPoint, Trade

from .risk import PositionSizer
from .signals import SignalGenerator
from .swing import find_swing_points


class Stats(TypedDict):
    symbol: str
    total_trades: int
    winners: int
    losers: int
    win_rate: str
    total_pnl: str
    total_return: str
    profit_factor: str
    avg_win: str
    avg_loss: str
    max_drawdown: str
    final_capital: str
    avg_holding_period: str


class BacktestCallbacks:
    """Callbacks for real-time backtest output."""

    def __init__(self) -> None:
        self._on_bar: Callable[[datetime, str, float, Signal, str, Position | None], None] | None = None
        self._on_signal: Callable[[str, str, float, float, float, float], None] | None = None
        self._on_trade_closed: Callable[[str, str, float, float, float, str], None] | None = None

    def on_bar(
        self, func: Callable[[datetime, str, float, Signal, str, Position | None], None]
    ) -> Callable[[datetime, str, float, Signal, str, Position | None], None]:
        self._on_bar = func
        return func

    def on_signal(
        self, func: Callable[[str, str, float, float, float, float], None]
    ) -> Callable[[str, str, float, float, float, float], None]:
        self._on_signal = func
        return func

    def on_trade_closed(
        self, func: Callable[[str, str, float, float, float, str], None]
    ) -> Callable[[str, str, float, float, float, str], None]:
        self._on_trade_closed = func
        return func


class MarketStructureBot:
    def __init__(
        self,
        capital: float = 100000,
        risk_pct: float = 0.01,
        rr_ratio: float = 2.0,
        swing_lb: int = 5,
        trailing_stop: bool = False,
        entry_strategy: str | None = None,
        exit_strategy: str | None = None,
        allow_short: bool = False,
    ):
        self.sig_gen = SignalGenerator(swing_lb, entry_strategy=entry_strategy, exit_strategy=exit_strategy)
        self.pos_sizer = PositionSizer(capital, risk_pct)
        self.rr_ratio = rr_ratio
        self.swing_lb = swing_lb
        self.trailing_stop = trailing_stop
        self.allow_short = allow_short
        self.position: Position | None = None
        self.trades: list[Trade] = []
        self.equity: list[float] = []
        self.symbol = ""
        self.callbacks: BacktestCallbacks | None = None
        self.speed: float = 0  # bars per second, 0 = instant

    def backtest(
        self,
        df: pl.DataFrame,
        symbol: str = "UNKNOWN",
        callbacks: BacktestCallbacks | None = None,
        speed: float = 0,
    ) -> pl.DataFrame:
        self.symbol = symbol
        self.callbacks = callbacks
        self.speed = speed
        self.position = None
        self.trades = []
        self.equity = [self.pos_sizer.capital]

        results: list[dict[str, Any]] = []

        for i in range(len(df)):
            bar: dict[str, Any] = df.row(i, named=True)
            price: float = float(bar["close"])
            bar_time: datetime = bar["datetime"]

            if self.position:
                if self.trailing_stop:
                    self._trail_stop(bar)
                exit_reason: ExitReason | None = self._check_exit(bar)
                if exit_reason:
                    self._close(price, i, bar_time, exit_reason)

            signal: Signal
            details: dict[str, str | float]
            signal, details = self.sig_gen.generate(df, i, bool(self.position))

            can_trade = signal == Signal.BUY or (signal == Signal.SELL and self.allow_short)
            if not self.position and can_trade:
                self._open(
                    "LONG" if signal == Signal.BUY else "SHORT",
                    price,
                    i,
                    bar_time,
                    df,
                )

            self.equity.append(self.pos_sizer.capital)
            results.append(
                {
                    "datetime": bar_time,
                    "close": price,
                    "signal": signal.value,
                    "trend": details.get("trend", "N/A"),
                    "position": self.position.direction if self.position else "",
                    "equity": self.pos_sizer.capital,
                }
            )

            # Callback for verbose output
            if self.callbacks and self.callbacks._on_bar:
                trend = str(details.get("trend", "N/A"))
                self.callbacks._on_bar(bar_time, symbol, price, signal, trend, self.position)

            # Delay for simulated real-time
            if self.speed > 0:
                asyncio.get_event_loop().run_until_complete(asyncio.sleep(1.0 / self.speed))

        return pl.DataFrame(results)

    def _check_exit(self, bar: dict[str, Any]) -> ExitReason | None:
        assert self.position is not None
        p: Position = self.position
        if p.direction == "LONG":
            if bar["low"] <= p.stop_loss:
                return "STOP_LOSS"
            if bar["high"] >= p.take_profit:
                return "TAKE_PROFIT"
        else:
            if bar["high"] >= p.stop_loss:
                return "STOP_LOSS"
            if bar["low"] <= p.take_profit:
                return "TAKE_PROFIT"
        return None

    def _trail_stop(self, bar: dict[str, Any]) -> None:
        """Move stop to breakeven after 1R profit."""
        assert self.position is not None
        p: Position = self.position
        if p.initial_stop_loss is None:
            return

        risk: float = abs(p.entry_price - p.initial_stop_loss)
        if p.direction == "LONG":
            # If price reached 1R profit, move stop to entry
            if bar["high"] >= p.entry_price + risk and p.stop_loss < p.entry_price:
                p.stop_loss = p.entry_price
        else:
            # SHORT: if price dropped 1R, move stop to entry
            if bar["low"] <= p.entry_price - risk and p.stop_loss > p.entry_price:
                p.stop_loss = p.entry_price

    def _open(
        self,
        direction: Direction,
        price: float,
        idx: int,
        time: datetime,
        df: pl.DataFrame,
    ) -> None:
        exit_params = self.sig_gen.calc_exit(direction, price, df.head(idx + 1), self.rr_ratio)
        size = self.pos_sizer.calc_size(price, exit_params.stop_loss)
        self.position = Position(
            price, idx, time, direction, size, exit_params.stop_loss, exit_params.take_profit, exit_params.stop_loss
        )

        if self.callbacks and self.callbacks._on_signal:
            self.callbacks._on_signal(
                direction, self.symbol, price, exit_params.stop_loss, exit_params.take_profit, size
            )

    def _close(self, price: float, idx: int, time: datetime, reason: ExitReason) -> None:
        assert self.position is not None
        p: Position = self.position
        pnl: float = (price - p.entry_price) * p.size if p.direction == "LONG" else (p.entry_price - price) * p.size

        self.trades.append(
            Trade(
                self.symbol,
                p.entry_price,
                price,
                p.entry_time,
                time,
                p.entry_index,
                p.direction,
                p.size,
                pnl,
                pnl / self.pos_sizer.capital,
                reason,
                idx - p.entry_index,
            )
        )
        self.pos_sizer.capital += pnl

        if self.callbacks and self.callbacks._on_trade_closed:
            self.callbacks._on_trade_closed(p.direction, self.symbol, p.entry_price, price, pnl, reason)

        self.position = None

    def get_stats(self) -> Stats | dict[str, str]:
        if not self.trades:
            return {"error": "No trades"}

        pnls: list[float] = [t.pnl for t in self.trades]
        wins: list[float] = [p for p in pnls if p > 0]
        losses: list[float] = [p for p in pnls if p < 0]

        equity: pl.Series = pl.Series(self.equity, dtype=pl.Float64)
        peak: pl.Series = equity.cum_max()
        dd: pl.Series = (peak - equity) / peak
        max_dd = dd.max()
        max_dd_val: float = float(max_dd) if isinstance(max_dd, (int, float)) else 0.0

        return {
            "symbol": self.symbol,
            "total_trades": len(self.trades),
            "winners": len(wins),
            "losers": len(losses),
            "win_rate": f"{100 * len(wins) / len(self.trades):.1f}%",
            "total_pnl": f"${sum(pnls):,.2f}",
            "total_return": f"{100 * (self.pos_sizer.capital - self.pos_sizer.initial) / self.pos_sizer.initial:.2f}%",
            "profit_factor": f"{abs(sum(wins) / sum(losses)):.2f}" if losses else "inf",
            "avg_win": f"${mean(wins):,.2f}" if wins else "$0",
            "avg_loss": f"${mean(losses):,.2f}" if losses else "$0",
            "max_drawdown": f"{100 * max_dd_val:.2f}%",
            "final_capital": f"${self.pos_sizer.capital:,.2f}",
            "avg_holding_period": f"{mean([t.holding_period for t in self.trades]):.1f} bars",
        }

    def plot_results(self, df: pl.DataFrame, results: pl.DataFrame) -> None:
        prices: list[float] = df["close"].to_list()
        equity: list[float] = results["equity"].to_list()

        equity_series: pl.Series = pl.Series(equity, dtype=pl.Float64)
        peak_series: pl.Series = equity_series.cum_max()
        drawdown: list[float] = ((peak_series - equity_series) / peak_series * -100).to_list()

        swings: list[SwingPoint] = find_swing_points(df, self.swing_lb)
        swing_high_x: list[int] = [sp.index for sp in swings if sp.is_high]
        swing_high_y: list[float] = [sp.price for sp in swings if sp.is_high]
        swing_low_x: list[int] = [sp.index for sp in swings if not sp.is_high]
        swing_low_y: list[float] = [sp.price for sp in swings if not sp.is_high]

        plt.clf()
        plt.theme("clear")
        plt.subplots(3, 1)

        plt.subplot(1, 1)
        plt.title(f"{self.symbol} - Price & Swing Points")
        plt.plot(prices, color="cyan")
        if swing_high_x:
            plt.scatter(swing_high_x, swing_high_y, color="red", marker="v")
        if swing_low_x:
            plt.scatter(swing_low_x, swing_low_y, color="green", marker="^")
        for t in self.trades:
            plt.vline(t.entry_index, color="blue")
            color = "green+" if t.pnl > 0 else "red+"
            plt.vline(t.entry_index + t.holding_period, color=color)
        plt.ylabel("Price ($)")

        plt.subplot(2, 1)
        plt.title("Equity Curve")
        plt.plot(equity, color="cyan")
        plt.ylabel("Capital ($)")

        plt.subplot(3, 1)
        plt.title("Drawdown (%)")
        plt.plot(drawdown, color="red")
        plt.ylabel("Drawdown %")

        plt.show()

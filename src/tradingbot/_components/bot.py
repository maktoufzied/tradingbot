import asyncio
from collections.abc import Callable
from datetime import datetime
from statistics import mean
from typing import Any, TypedDict

import plotext as plt
import polars as pl

from tradingbot.types import Direction, ExitReason, PartialExit, PartialExitLevel, Position, Signal, SwingPoint, Trade

from .execution import ExecutionModel
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
    # Execution cost fields (optional for backward compat)
    gross_pnl: str
    gross_return: str
    total_costs: str


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
        stop_pct: float = 0.01,
        swing_lb: int = 5,
        trailing_stop: bool = False,
        atr_trail: bool = False,
        atr_trail_multiplier: float = 2.0,
        atr_trail_activation_r: float = 0.0,
        entry_strategy: str | None = None,
        exit_strategy: str | None = None,
        allow_short: bool = False,
        execution_model: ExecutionModel | None = None,
        use_atr_sizing: bool = False,
        budget: float | None = None,
        partial_exit_levels: tuple[PartialExitLevel, ...] = (),
        eod_exit: bool = False,
        eod_exit_minutes_before: int = 15,
        indicators: list[str] | None = None,
        filter_mode: str | None = None,
    ):
        self.sig_gen = SignalGenerator(
            swing_lb,
            entry_strategy=entry_strategy,
            exit_strategy=exit_strategy,
            indicators=indicators,
            filter_mode=filter_mode,
        )
        self.pos_sizer = PositionSizer(capital, risk_pct, use_atr_sizing=use_atr_sizing, budget=budget)
        self.rr_ratio = rr_ratio
        self.stop_pct = stop_pct
        self.swing_lb = swing_lb
        self.trailing_stop = trailing_stop
        self.atr_trail = atr_trail
        self.atr_trail_multiplier = atr_trail_multiplier
        self.atr_trail_activation_r = atr_trail_activation_r
        self.allow_short = allow_short
        self.execution_model = execution_model or ExecutionModel()
        self.partial_exit_levels = partial_exit_levels
        self.eod_exit = eod_exit
        self.eod_exit_minutes_before = eod_exit_minutes_before
        self.position: Position | None = None
        self.trades: list[Trade] = []
        self.equity: list[float] = []
        self.symbol = ""
        self.callbacks: BacktestCallbacks | None = None
        self.speed: float = 0  # bars per second, 0 = instant
        self._current_atr: float = 0.0  # Cached ATR at position entry

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
                if self.trailing_stop or self.atr_trail:
                    self._trail_stop(bar)
                # Check for partial exits first (if configured)
                self._process_partial_exits(bar, bar_time)
                # Then check for full exit
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

        # EOD exit: close positions before market close
        if self.eod_exit:
            bar_time: datetime = bar["datetime"]
            if self._is_near_market_close(bar_time):
                return "EOD_EXIT"

        return None

    def _is_near_market_close(self, bar_time: datetime) -> bool:
        """Check if bar time is within eod_exit_minutes_before of market close.

        Market close is 4:00 PM ET (16:00).
        Bars are in UTC, so we convert using zoneinfo for proper DST handling.
        """
        from zoneinfo import ZoneInfo

        # Treat bar_time as UTC and convert to US/Eastern
        utc_time = bar_time.replace(tzinfo=ZoneInfo("UTC"))
        et_time = utc_time.astimezone(ZoneInfo("America/New_York"))

        et_hour = et_time.hour
        et_minute = et_time.minute

        # Market close is at 16:00 ET (4:00 PM)
        market_close_hour = 16
        market_close_minute = 0

        # Calculate minutes until close
        current_minutes = et_hour * 60 + et_minute
        close_minutes = market_close_hour * 60 + market_close_minute
        minutes_to_close = close_minutes - current_minutes

        return 0 < minutes_to_close <= self.eod_exit_minutes_before

    def _process_partial_exits(self, bar: dict[str, Any], bar_time: datetime) -> None:
        """Check and execute any triggered partial exit levels."""
        if not self.partial_exit_levels or not self.position:
            return

        p = self.position
        if p.initial_stop_loss is None:
            return

        risk = abs(p.entry_price - p.initial_stop_loss)
        if risk == 0:
            return

        # Initialize tracking on first call
        if p.triggered_levels is None:
            p.triggered_levels = set()
        if p.partial_exits is None:
            p.partial_exits = []
        if p.remaining_size is None:
            p.remaining_size = p.size

        # Calculate current profit in R-multiples
        if p.direction == "LONG":
            current_price = bar["high"]  # Use high for profit check
            profit = current_price - p.entry_price
        else:
            current_price = bar["low"]  # Use low for short profit check
            profit = p.entry_price - current_price

        current_r = profit / risk

        # Check each level (sorted by r_multiple ascending)
        for level in sorted(self.partial_exit_levels, key=lambda x: x.r_multiple):
            if level.r_multiple in p.triggered_levels:
                continue  # Already triggered

            if current_r >= level.r_multiple:
                # Trigger this level
                p.triggered_levels.add(level.r_multiple)

                # Calculate exit size
                exit_size = p.remaining_size * level.exit_pct
                if exit_size <= 0:
                    continue

                # Calculate P&L for this partial exit
                exit_price = (
                    p.entry_price + (level.r_multiple * risk)
                    if p.direction == "LONG"
                    else p.entry_price - (level.r_multiple * risk)
                )
                gross_pnl, net_pnl = self.execution_model.calculate_net_pnl(
                    p.entry_price, exit_price, exit_size, p.direction
                )

                # Record partial exit
                partial_exit = PartialExit(
                    r_multiple=level.r_multiple,
                    exit_price=exit_price,
                    exit_size=exit_size,
                    pnl=net_pnl,
                    exit_time=bar_time,
                )
                p.partial_exits.append(partial_exit)

                # Update remaining size and capital
                p.remaining_size -= exit_size
                self.pos_sizer.capital += net_pnl

                # Move stop to breakeven after first partial exit
                if len(p.partial_exits) == 1:
                    p.stop_loss = p.entry_price

    def _calc_atr(self, df: pl.DataFrame, period: int = 14) -> float:
        """Calculate ATR for trailing stop distance."""
        if len(df) < period + 1:
            return 0.0

        high = df["high"].to_list()
        low = df["low"].to_list()
        close = df["close"].to_list()

        true_ranges: list[float] = []
        for i in range(1, len(df)):
            tr = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )
            true_ranges.append(tr)

        if len(true_ranges) < period:
            return mean(true_ranges) if true_ranges else 0.0

        return mean(true_ranges[-period:])

    def _trail_stop(self, bar: dict[str, Any]) -> None:
        """Trail stop loss based on configured method.

        - trailing_stop=True: Move to breakeven after 1R profit
        - atr_trail=True: Continuously trail at high_water - (N × ATR)
        - atr_trail_activation_r: Only start ATR trailing after reaching this R-multiple
        """
        assert self.position is not None
        p: Position = self.position
        if p.initial_stop_loss is None:
            return

        # Update high-water mark
        if p.direction == "LONG":
            current_high = bar["high"]
            if p.high_water_mark is None or current_high > p.high_water_mark:
                p.high_water_mark = current_high
        else:
            current_low = bar["low"]
            if p.high_water_mark is None or current_low < p.high_water_mark:
                p.high_water_mark = current_low

        # ATR-based trailing (continuous)
        if self.atr_trail and self._current_atr > 0 and p.high_water_mark is not None:
            # Check activation threshold before trailing
            if self.atr_trail_activation_r > 0:
                risk = abs(p.entry_price - p.initial_stop_loss)
                if risk > 0:
                    profit = bar["high"] - p.entry_price if p.direction == "LONG" else p.entry_price - bar["low"]
                    current_r = profit / risk
                    if current_r < self.atr_trail_activation_r:
                        return  # Not yet at activation threshold

            trail_distance = self.atr_trail_multiplier * self._current_atr
            if p.direction == "LONG":
                new_stop = p.high_water_mark - trail_distance
                # Only move stop up, never down
                if new_stop > p.stop_loss:
                    p.stop_loss = new_stop
            else:
                new_stop = p.high_water_mark + trail_distance
                # Only move stop down, never up (for shorts)
                if new_stop < p.stop_loss:
                    p.stop_loss = new_stop
            return

        # Breakeven trailing (move to entry after 1R)
        if self.trailing_stop:
            risk = abs(p.entry_price - p.initial_stop_loss)
            if p.direction == "LONG":
                if bar["high"] >= p.entry_price + risk and p.stop_loss < p.entry_price:
                    p.stop_loss = p.entry_price
            else:
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
        history = df.head(idx + 1)
        exit_params = self.sig_gen.calc_exit(direction, price, history, self.rr_ratio, self.stop_pct)
        size = self.pos_sizer.calc_size(price, exit_params.stop_loss, history)

        # Cache ATR at entry for trailing stop
        if self.atr_trail:
            self._current_atr = self._calc_atr(history)

        self.position = Position(
            price,
            idx,
            time,
            direction,
            size,
            exit_params.stop_loss,
            exit_params.take_profit,
            exit_params.stop_loss,
            high_water_mark=price,  # Initialize at entry price
        )

        if self.callbacks and self.callbacks._on_signal:
            self.callbacks._on_signal(
                direction, self.symbol, price, exit_params.stop_loss, exit_params.take_profit, size
            )

    def _close(self, price: float, idx: int, time: datetime, reason: ExitReason) -> None:
        assert self.position is not None
        p: Position = self.position

        # Use remaining size (accounts for partial exits)
        remaining_size = p.get_remaining_size()

        # Calculate gross and net P&L for remaining position
        gross_pnl, net_pnl = self.execution_model.calculate_net_pnl(p.entry_price, price, remaining_size, p.direction)
        costs = self.execution_model.calculate_costs(p.entry_price, price, remaining_size, p.direction)

        # Include P&L from partial exits in totals
        partial_exits_pnl = sum(pe.pnl for pe in (p.partial_exits or []))
        total_net_pnl = net_pnl + partial_exits_pnl
        total_gross_pnl = gross_pnl + sum(pe.pnl for pe in (p.partial_exits or []))  # Approximate

        self.trades.append(
            Trade(
                self.symbol,
                p.entry_price,
                price,
                p.entry_time,
                time,
                p.entry_index,
                p.direction,
                p.size,  # Original full size
                total_net_pnl,  # Total P&L including partial exits
                total_net_pnl / self.pos_sizer.capital,
                reason,
                idx - p.entry_index,
                gross_pnl=total_gross_pnl,
                execution_costs=costs.total,
                partial_exits=p.partial_exits,
                stop_loss=p.stop_loss,
                take_profit=p.take_profit,
            )
        )
        self.pos_sizer.capital += net_pnl  # Only add remaining position P&L (partial exits already added)

        if self.callbacks and self.callbacks._on_trade_closed:
            self.callbacks._on_trade_closed(p.direction, self.symbol, p.entry_price, price, total_net_pnl, reason)

        self.position = None

    def get_stats(self) -> Stats | dict[str, str]:
        if not self.trades:
            return {"error": "No trades"}

        # Net P&L (after costs)
        pnls: list[float] = [t.pnl for t in self.trades]
        wins: list[float] = [p for p in pnls if p > 0]
        losses: list[float] = [p for p in pnls if p < 0]

        # Gross P&L and costs
        gross_pnls: list[float] = [t.gross_pnl if t.gross_pnl is not None else t.pnl for t in self.trades]
        total_costs = sum(t.execution_costs or 0 for t in self.trades)

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
            # Execution cost breakdown
            "gross_pnl": f"${sum(gross_pnls):,.2f}",
            "gross_return": f"{100 * sum(gross_pnls) / self.pos_sizer.initial:.2f}%",
            "total_costs": f"${total_costs:,.2f}",
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

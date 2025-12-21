import polars as pl

from tradingbot.types import Position, Signal, SwingPoint, Trend

from .swing import analyze_structure, find_swing_points


class SignalGenerator:
    def __init__(self, swing_lookback: int = 5):
        self.swing_lookback: int = swing_lookback

    def generate(self, df: pl.DataFrame, idx: int, position: Position | None) -> tuple[Signal, dict[str, str | float]]:
        if idx < self.swing_lookback * 3:
            return Signal.HOLD, {"reason": "Insufficient data"}

        hist: pl.DataFrame = df.head(idx + 1)
        swings: list[SwingPoint] = find_swing_points(hist, self.swing_lookback)

        if len(swings) < 4:
            return Signal.HOLD, {"reason": "Not enough swings"}

        trend: Trend
        analysis: dict[str, float]
        trend, analysis = analyze_structure(swings)
        bar: dict[str, float] = df.row(idx, named=True)
        price: float = float(bar["close"])

        details: dict[str, str | float] = {"trend": trend.value, "price": price, **analysis}

        if position is not None:
            return Signal.HOLD, details

        highs: list[SwingPoint] = [s for s in swings if s.is_high]
        lows: list[SwingPoint] = [s for s in swings if not s.is_high]

        if trend == Trend.BEARISH and highs and price > highs[-1].price:
            return Signal.BUY, {**details, "reason": "Bullish structure break"}

        if trend == Trend.BULLISH and lows and price < lows[-1].price:
            return Signal.SELL, {**details, "reason": "Bearish structure break"}

        if trend == Trend.BULLISH and len(lows) >= 2:
            last_low: float = lows[-1].price
            if bar["low"] <= last_low * 1.01 and bar["close"] > bar["open"]:
                return Signal.BUY, {**details, "reason": "Pullback to HL"}

        if trend == Trend.BEARISH and len(highs) >= 2:
            last_high: float = highs[-1].price
            if bar["high"] >= last_high * 0.99 and bar["close"] < bar["open"]:
                return Signal.SELL, {**details, "reason": "Rally to LH"}

        return Signal.HOLD, details

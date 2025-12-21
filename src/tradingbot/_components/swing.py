from typing import Any

import polars as pl

from tradingbot.types import SwingPoint, Trend


def find_swing_points(df: pl.DataFrame, lookback: int = 5) -> list[SwingPoint]:
    swing_points: list[SwingPoint] = []
    highs: list[float] = df["high"].to_list()
    lows: list[float] = df["low"].to_list()
    timestamps = df["datetime"].to_list() if "datetime" in df.columns else [None] * len(df)
    n: int = len(df)

    for i in range(lookback, n - lookback):
        is_high: bool = all(highs[i] > highs[i - j] and highs[i] > highs[i + j] for j in range(1, lookback + 1))
        if is_high:
            swing_points.append(SwingPoint(i, float(highs[i]), True, timestamps[i]))

        is_low: bool = all(lows[i] < lows[i - j] and lows[i] < lows[i + j] for j in range(1, lookback + 1))
        if is_low:
            swing_points.append(SwingPoint(i, float(lows[i]), False, timestamps[i]))

    swing_points.sort(key=lambda x: x.index)
    return swing_points


def analyze_structure(swing_points: list[SwingPoint]) -> tuple[Trend, dict[str, Any]]:
    if len(swing_points) < 4:
        return Trend.NEUTRAL, {}

    highs: list[SwingPoint] = [sp for sp in swing_points if sp.is_high][-3:]
    lows: list[SwingPoint] = [sp for sp in swing_points if not sp.is_high][-3:]

    if len(highs) < 2 or len(lows) < 2:
        return Trend.NEUTRAL, {}

    hh: int = sum(1 for i in range(1, len(highs)) if highs[i].price > highs[i - 1].price)
    lh: int = sum(1 for i in range(1, len(highs)) if highs[i].price < highs[i - 1].price)
    hl: int = sum(1 for i in range(1, len(lows)) if lows[i].price > lows[i - 1].price)
    ll: int = sum(1 for i in range(1, len(lows)) if lows[i].price < lows[i - 1].price)

    analysis: dict[str, Any] = {
        "hh": hh,
        "lh": lh,
        "hl": hl,
        "ll": ll,
        "last_high": highs[-1],
        "last_low": lows[-1],
    }

    if hh + hl > lh + ll and hh + hl >= 2:
        return Trend.BULLISH, analysis
    elif lh + ll > hh + hl and lh + ll >= 2:
        return Trend.BEARISH, analysis
    return Trend.NEUTRAL, analysis

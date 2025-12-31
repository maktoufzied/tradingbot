"""Opening Range Breakout + Fair Value Gap (ORB+FVG) entry strategy.

1-minute scalping strategy combining:
1. Opening Range (9:30-9:35 AM ET): First 5 minutes high/low
2. FVG Confirmation: Breakout must create a Fair Value Gap
3. Retest Entry: Wait for price to retrace into FVG zone
4. Engulfing Trigger: Enter on engulfing candle within FVG

Win rate: 55-60% | Target RR: 3:1
Source: Adapted from ICT/SMC methodology
Best for: High volatility morning sessions, 1-minute charts
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Final

import numpy as np
import polars as pl
import talib

from tradingbot.types import Signal

from ..interfaces import Entry
from ..registry import register_entry

# Market open in US/Eastern timezone
# During EST (Nov-Mar): UTC-5, so 9:30 AM ET = 14:30 UTC
# During EDT (Mar-Nov): UTC-4, so 9:30 AM ET = 13:30 UTC
MARKET_OPEN_HOUR_ET: Final = 9
MARKET_OPEN_MINUTE: Final = 30
ORB_DURATION_MINUTES: Final = 5

# UTC offset for US/Eastern (simplified: use EST year-round for now)
# TODO: Use proper timezone library for DST handling
ET_UTC_OFFSET: Final = -5  # EST = UTC-5


class Phase(Enum):
    """State machine phases for ORB+FVG strategy."""

    BUILDING_RANGE = auto()
    WAITING_BREAKOUT = auto()
    WAITING_RETEST = auto()
    WAITING_ENGULFING = auto()
    COOLDOWN = auto()


@dataclass
class FVG:
    """Fair Value Gap zone."""

    type: str  # "bullish" or "bearish"
    top: float
    bottom: float
    idx: int


@dataclass
class SessionState:
    """Per-session state tracking."""

    date: str
    range_high: float | None = None
    range_low: float | None = None
    phase: Phase = Phase.BUILDING_RANGE
    breakout_direction: str | None = None
    active_fvg: FVG | None = None
    signal_generated: bool = False


class OrbFvgStrategy:
    """Entry strategy combining Opening Range Breakout with FVG confirmation."""

    @property
    def name(self) -> str:
        return "orb_fvg"

    def __init__(
        self,
        orb_minutes: int = ORB_DURATION_MINUTES,
        fvg_min_size_pct: float = 0.1,
        require_engulfing: bool = True,
    ) -> None:
        self._orb_minutes = orb_minutes
        self._fvg_min_size_pct = fvg_min_size_pct
        self._require_engulfing = require_engulfing
        self._session: SessionState | None = None

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute engulfing pattern using TA-Lib."""
        if "engulfing" in df.columns:
            return df

        opens = df["open"].to_numpy().astype(np.float64)
        highs = df["high"].to_numpy().astype(np.float64)
        lows = df["low"].to_numpy().astype(np.float64)
        closes = df["close"].to_numpy().astype(np.float64)

        engulfing = talib.CDLENGULFING(opens, highs, lows, closes)

        return df.with_columns([pl.Series("engulfing", engulfing)])

    def _get_session_date(self, dt: object) -> str:
        """Extract session date from datetime."""
        if hasattr(dt, "date"):
            return str(dt.date())
        return str(dt)[:10]

    def _to_et_time(self, dt: object) -> tuple[int, int]:
        """Convert datetime to Eastern Time (hour, minute).

        Assumes input is UTC (naive datetime from Alpaca).
        Uses simplified EST offset (-5h). For production, use pytz/zoneinfo.
        """
        if not hasattr(dt, "hour") or not hasattr(dt, "minute"):
            return (-1, -1)

        # Convert UTC to ET (simplified: assume EST year-round)
        utc_hour = dt.hour
        utc_minute = dt.minute

        et_hour = (utc_hour + ET_UTC_OFFSET) % 24
        return (et_hour, utc_minute)

    def _is_in_orb_period(self, dt: object) -> bool:
        """Check if datetime is within opening range period (9:30-9:35 AM ET)."""
        et_hour, et_minute = self._to_et_time(dt)
        if et_hour < 0:
            return False

        if et_hour != MARKET_OPEN_HOUR_ET:
            return False

        return MARKET_OPEN_MINUTE <= et_minute < MARKET_OPEN_MINUTE + self._orb_minutes

    def _is_after_orb(self, dt: object) -> bool:
        """Check if datetime is after opening range period."""
        et_hour, et_minute = self._to_et_time(dt)
        if et_hour < 0:
            return True

        if et_hour > MARKET_OPEN_HOUR_ET:
            return True
        if et_hour == MARKET_OPEN_HOUR_ET:
            return et_minute >= MARKET_OPEN_MINUTE + self._orb_minutes
        return False

    def _detect_fvg(
        self,
        highs: list[float],
        lows: list[float],
        idx: int,
    ) -> FVG | None:
        """Detect Fair Value Gap at index (3-candle pattern)."""
        if idx < 2:
            return None

        candle1_high = highs[idx - 2]
        candle1_low = lows[idx - 2]
        candle3_high = highs[idx]
        candle3_low = lows[idx]

        # Bullish FVG: gap between candle 1 high and candle 3 low
        if candle3_low > candle1_high:
            gap_size = candle3_low - candle1_high
            gap_pct = (gap_size / candle1_high) * 100
            if gap_pct >= self._fvg_min_size_pct:
                return FVG(
                    type="bullish",
                    top=candle3_low,
                    bottom=candle1_high,
                    idx=idx,
                )

        # Bearish FVG: gap between candle 1 low and candle 3 high
        if candle1_low > candle3_high:
            gap_size = candle1_low - candle3_high
            gap_pct = (gap_size / candle3_high) * 100
            if gap_pct >= self._fvg_min_size_pct:
                return FVG(
                    type="bearish",
                    top=candle1_low,
                    bottom=candle3_high,
                    idx=idx,
                )

        return None

    def _is_price_in_fvg(self, fvg: FVG, price: float) -> bool:
        """Check if price is within FVG zone."""
        return fvg.bottom <= price <= fvg.top

    def signal(self, df: pl.DataFrame, idx: int, has_position: bool) -> Entry:
        """Generate signal based on ORB+FVG state machine."""
        if idx < 5:
            return Entry(Signal.HOLD, "Insufficient data", {})

        hist = df.head(idx + 1)
        if "engulfing" not in hist.columns:
            hist = self.compute(hist)

        current_bar = hist.row(-1, named=True)
        current_dt = current_bar["datetime"]
        session_date = self._get_session_date(current_dt)

        close = float(current_bar["close"])
        high = float(current_bar["high"])
        low = float(current_bar["low"])
        engulfing = int(current_bar["engulfing"]) if "engulfing" in current_bar else 0

        # Initialize or reset session state
        if self._session is None or self._session.date != session_date:
            self._session = SessionState(date=session_date)

        session = self._session

        details: dict[str, str | float] = {
            "price": round(close, 2),
            "phase": session.phase.name,
        }

        if has_position:
            return Entry(Signal.HOLD, "Position open", details)

        if session.signal_generated:
            return Entry(Signal.HOLD, "Signal already generated today", details)

        highs = hist["high"].to_list()
        lows = hist["low"].to_list()

        # --- PHASE: BUILDING_RANGE ---
        if session.phase == Phase.BUILDING_RANGE:
            if self._is_in_orb_period(current_dt):
                # Update range high/low
                if session.range_high is None or high > session.range_high:
                    session.range_high = high
                if session.range_low is None or low < session.range_low:
                    session.range_low = low

                details["or_high"] = round(session.range_high, 2) if session.range_high else 0
                details["or_low"] = round(session.range_low, 2) if session.range_low else 0
                return Entry(Signal.HOLD, "Building opening range", details)

            elif self._is_after_orb(current_dt) and session.range_high and session.range_low:
                session.phase = Phase.WAITING_BREAKOUT
                details["or_high"] = round(session.range_high, 2)
                details["or_low"] = round(session.range_low, 2)

        # --- PHASE: WAITING_BREAKOUT ---
        if session.phase == Phase.WAITING_BREAKOUT:
            if session.range_high is None or session.range_low is None:
                return Entry(Signal.HOLD, "No opening range", details)

            details["or_high"] = round(session.range_high, 2)
            details["or_low"] = round(session.range_low, 2)

            # Breakout above range high
            if close > session.range_high:
                fvg = self._detect_fvg(highs, lows, idx)
                if fvg and fvg.type == "bullish":
                    session.phase = Phase.WAITING_RETEST
                    session.breakout_direction = "long"
                    session.active_fvg = fvg
                    details["fvg_top"] = round(fvg.top, 2)
                    details["fvg_bottom"] = round(fvg.bottom, 2)
                    return Entry(Signal.HOLD, "Bullish breakout with FVG - waiting retest", details)
                return Entry(Signal.HOLD, "Bullish breakout (no FVG)", details)

            # Breakout below range low
            if close < session.range_low:
                fvg = self._detect_fvg(highs, lows, idx)
                if fvg and fvg.type == "bearish":
                    session.phase = Phase.WAITING_RETEST
                    session.breakout_direction = "short"
                    session.active_fvg = fvg
                    details["fvg_top"] = round(fvg.top, 2)
                    details["fvg_bottom"] = round(fvg.bottom, 2)
                    return Entry(Signal.HOLD, "Bearish breakout with FVG - waiting retest", details)
                return Entry(Signal.HOLD, "Bearish breakout (no FVG)", details)

            return Entry(Signal.HOLD, "Waiting for breakout", details)

        # --- PHASE: WAITING_RETEST ---
        if session.phase == Phase.WAITING_RETEST:
            if session.active_fvg is None:
                session.phase = Phase.WAITING_BREAKOUT
                return Entry(Signal.HOLD, "Lost FVG reference", details)

            fvg = session.active_fvg
            details["fvg_top"] = round(fvg.top, 2)
            details["fvg_bottom"] = round(fvg.bottom, 2)

            if self._is_price_in_fvg(fvg, close):
                session.phase = Phase.WAITING_ENGULFING
                return Entry(Signal.HOLD, "Price in FVG zone - waiting engulfing", details)

            return Entry(Signal.HOLD, "Waiting for retest into FVG", details)

        # --- PHASE: WAITING_ENGULFING ---
        if session.phase == Phase.WAITING_ENGULFING:
            if session.active_fvg is None:
                session.phase = Phase.WAITING_BREAKOUT
                return Entry(Signal.HOLD, "Lost FVG reference", details)

            fvg = session.active_fvg
            details["fvg_top"] = round(fvg.top, 2)
            details["fvg_bottom"] = round(fvg.bottom, 2)
            details["engulfing"] = engulfing

            # Check if still in FVG zone
            if not self._is_price_in_fvg(fvg, close):
                # Price left FVG without engulfing - go back to waiting retest
                session.phase = Phase.WAITING_RETEST
                return Entry(Signal.HOLD, "Price left FVG without signal", details)

            # Check for engulfing pattern
            if self._require_engulfing:
                if session.breakout_direction == "long" and engulfing > 0:
                    session.signal_generated = True
                    session.phase = Phase.COOLDOWN
                    return Entry(
                        Signal.BUY,
                        f"ORB+FVG: Bullish engulfing in FVG zone ({fvg.bottom:.2f}-{fvg.top:.2f})",
                        details,
                    )
                if session.breakout_direction == "short" and engulfing < 0:
                    session.signal_generated = True
                    session.phase = Phase.COOLDOWN
                    return Entry(
                        Signal.SELL,
                        f"ORB+FVG: Bearish engulfing in FVG zone ({fvg.bottom:.2f}-{fvg.top:.2f})",
                        details,
                    )
                return Entry(Signal.HOLD, "Waiting for engulfing pattern", details)

            # No engulfing required - enter on FVG touch
            if session.breakout_direction == "long":
                session.signal_generated = True
                session.phase = Phase.COOLDOWN
                return Entry(
                    Signal.BUY,
                    f"ORB+FVG: Bullish retest of FVG ({fvg.bottom:.2f}-{fvg.top:.2f})",
                    details,
                )
            if session.breakout_direction == "short":
                session.signal_generated = True
                session.phase = Phase.COOLDOWN
                return Entry(
                    Signal.SELL,
                    f"ORB+FVG: Bearish retest of FVG ({fvg.bottom:.2f}-{fvg.top:.2f})",
                    details,
                )

        # --- PHASE: COOLDOWN ---
        if session.phase == Phase.COOLDOWN:
            return Entry(Signal.HOLD, "Signal generated - cooldown", details)

        return Entry(Signal.HOLD, "", details)


class OrbFvgSimpleStrategy(OrbFvgStrategy):
    """ORB+FVG without engulfing requirement - enters on FVG retest."""

    @property
    def name(self) -> str:
        return "orb_fvg_simple"

    def __init__(self) -> None:
        super().__init__(require_engulfing=False)


# Register on import
_strategy = OrbFvgStrategy()
_strategy_simple = OrbFvgSimpleStrategy()
register_entry(_strategy)
register_entry(_strategy_simple)

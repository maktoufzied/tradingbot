"""Clean interfaces for entry and exit strategies."""

from dataclasses import dataclass
from typing import Protocol

import polars as pl

from tradingbot.types import Direction, Signal, SwingPoint


@dataclass(frozen=True)
class Entry:
    """Entry signal with metadata."""

    signal: Signal
    reason: str
    details: dict[str, str | float]


@dataclass(frozen=True)
class Exit:
    """Exit parameters for a position."""

    stop_loss: float
    take_profit: float


class EntryStrategy(Protocol):
    """Protocol for entry strategies.

    Entry strategies are responsible for:
    - Computing any required indicators
    - Generating BUY/SELL/HOLD signals
    """

    @property
    def name(self) -> str:
        """Strategy identifier."""
        ...

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add any required indicators to the DataFrame."""
        ...

    def signal(self, df: pl.DataFrame, idx: int, has_position: bool) -> Entry:
        """Generate entry signal for the current bar.

        Args:
            df: OHLCV DataFrame with any computed indicators
            idx: Current bar index
            has_position: Whether a position is currently open

        Returns:
            Entry with signal (BUY/SELL/HOLD), reason, and details
        """
        ...


class ExitStrategy(Protocol):
    """Protocol for exit strategies.

    Exit strategies are responsible for:
    - Calculating stop-loss price
    - Calculating take-profit price
    """

    @property
    def name(self) -> str:
        """Strategy identifier."""
        ...

    def calc(
        self,
        direction: Direction,
        entry: float,
        df: pl.DataFrame,
        swings: list[SwingPoint],
        rr_ratio: float,
        stop_pct: float = 0.01,
    ) -> Exit:
        """Calculate exit parameters for a position.

        Args:
            direction: LONG or SHORT
            entry: Entry price
            df: OHLCV DataFrame
            swings: Recent swing points
            rr_ratio: Risk/reward ratio for RR-based TP
            stop_pct: Stop loss percentage (for fixed exit strategy)

        Returns:
            Exit with stop_loss and take_profit prices
        """
        ...

"""Signal generation using the new strategy architecture."""

import polars as pl

from tradingbot.config import get_indicator_config, get_strategy_config
from tradingbot.interfaces import IndicatorProtocol
from tradingbot.types import Signal, SwingPoint

from .indicators import get_registry as get_indicator_registry
from .strategies import Entry, Exit, get_entry_registry, get_exit_registry
from .strategies.interfaces import EntryStrategy, ExitStrategy
from .swing import find_swing_points


class SignalGenerator:
    """Signal generator with pluggable entry and exit strategies.

    Clean architecture:
    - Entry strategies only generate signals (BUY/SELL/HOLD)
    - Exit strategies only calculate SL/TP
    - Strategies are composable (any entry + any exit)
    - Indicators can filter signals (RSI, MACD, etc.)
    """

    def __init__(
        self,
        swing_lookback: int = 5,
        entry_strategy: str | None = None,
        exit_strategy: str | None = None,
    ) -> None:
        self.swing_lookback = swing_lookback
        self._entry: EntryStrategy = self._load_entry(entry_strategy)
        self._exit: ExitStrategy = self._load_exit(exit_strategy)
        self._indicator_config = get_indicator_config()
        self._indicator_registry = get_indicator_registry()

    def _load_entry(self, name: str | None) -> EntryStrategy:
        """Load entry strategy from registry."""
        cfg = get_strategy_config()
        strategy_name = name or cfg.entry
        return get_entry_registry().get(strategy_name)

    def _load_exit(self, name: str | None) -> ExitStrategy:
        """Load exit strategy from registry."""
        cfg = get_strategy_config()
        strategy_name = name or cfg.exit
        return get_exit_registry().get(strategy_name)

    def generate(
        self,
        df: pl.DataFrame,
        idx: int,
        has_position: bool,
    ) -> tuple[Signal, dict[str, str | float]]:
        """Generate entry signal for the current bar.

        Args:
            df: OHLCV DataFrame
            idx: Current bar index
            has_position: Whether a position is currently open

        Returns:
            Tuple of (Signal, details_dict)
        """
        # Minimum data check
        if idx < self.swing_lookback * 3:
            return Signal.HOLD, {"reason": "Insufficient data"}

        hist = df.head(idx + 1)

        # Compute indicators for filtering
        hist = self._compute_indicators(hist)

        # Let entry strategy compute its indicators
        hist = self._entry.compute(hist)

        # Generate signal
        entry: Entry = self._entry.signal(hist, len(hist) - 1, has_position)

        details: dict[str, str | float] = {
            "strategy": self._entry.name,
            "reason": entry.reason,
            **entry.details,
        }

        # Apply indicator filtering if signal is BUY/SELL
        if entry.signal in (Signal.BUY, Signal.SELL) and not self._filter_signal(entry.signal, hist, len(hist) - 1):
            details["filtered_by"] = "indicators"
            return Signal.HOLD, details

        return entry.signal, details

    def _get_enabled_indicators(self) -> list[IndicatorProtocol]:
        """Get list of enabled indicator instances."""
        return self._indicator_registry.get_enabled(self._indicator_config.enabled)

    def _compute_indicators(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute all enabled indicators."""
        for indicator in self._get_enabled_indicators():
            df = indicator.compute(df)
        return df

    def _filter_signal(self, signal: Signal, df: pl.DataFrame, idx: int) -> bool:
        """Filter signal through enabled indicators.

        Returns True if signal passes all filters, False if blocked.
        """
        if self._indicator_config.signal_mode == "none":
            return True

        indicators = self._get_enabled_indicators()
        if not indicators:
            return True

        filter_mode = self._indicator_config.filter_mode
        results = [ind.filter_signal(signal, df, idx) for ind in indicators]

        if filter_mode == "all":
            return all(results)
        if filter_mode == "any":
            return any(results)
        return True

    def calc_exit(
        self,
        direction: str,
        entry_price: float,
        df: pl.DataFrame,
        rr_ratio: float,
        stop_pct: float = 0.01,
    ) -> Exit:
        """Calculate exit parameters (SL/TP) for a position.

        Args:
            direction: LONG or SHORT
            entry_price: Entry price
            df: OHLCV DataFrame
            rr_ratio: Risk/reward ratio
            stop_pct: Stop loss percentage (for fixed exit strategy)

        Returns:
            Exit with stop_loss and take_profit prices
        """
        swings: list[SwingPoint] = find_swing_points(df, self.swing_lookback)
        return self._exit.calc(direction, entry_price, df, swings, rr_ratio, stop_pct)  # type: ignore[arg-type]

    @property
    def entry_name(self) -> str:
        """Get the current entry strategy name."""
        return self._entry.name

    @property
    def exit_name(self) -> str:
        """Get the current exit strategy name."""
        return self._exit.name

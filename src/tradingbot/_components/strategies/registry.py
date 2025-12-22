import polars as pl

from tradingbot.interfaces import ExitStrategyProtocol, Registry
from tradingbot.types import Direction, SwingPoint


class StrategyRegistry(Registry[ExitStrategyProtocol]):
    """Registry for exit strategy implementations."""


def get_registry() -> StrategyRegistry:
    return StrategyRegistry()


class ExitStrategy:
    """Facade for exit strategy access (stop-loss and take-profit).

    Available strategies: "swing", "atr", or "rr"
    """

    @staticmethod
    def calc(
        direction: Direction,
        entry: float,
        rr_ratio: float,
        bars: pl.DataFrame,
        swings: list[SwingPoint],
        strategy: str | None = None,
    ) -> tuple[float, float]:
        """Calculate stop-loss and take-profit prices.

        Returns:
            Tuple of (stop_loss, take_profit)
        """
        registry: StrategyRegistry = get_registry()
        impl: ExitStrategyProtocol = registry.get(strategy)
        return impl.calc(direction, entry, rr_ratio, bars, swings)

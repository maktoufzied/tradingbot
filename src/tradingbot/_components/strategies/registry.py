import polars as pl

from tradingbot.interfaces import Registry, StopStrategyProtocol
from tradingbot.types import Direction, SwingPoint


class StrategyRegistry(Registry[StopStrategyProtocol]):
    """Registry for stop strategy implementations."""


def get_registry() -> StrategyRegistry:
    return StrategyRegistry()


class StopStrategy:
    """Facade for stop strategy access."""

    @staticmethod
    def calc_stop(
        direction: Direction,
        entry: float,
        df: pl.DataFrame,
        idx: int,
        swings: list[SwingPoint],
        strategy: str | None = None,
    ) -> float:
        registry: StrategyRegistry = get_registry()
        impl: StopStrategyProtocol = registry.get(strategy)
        return impl.calc_stop(direction, entry, df, idx, swings)

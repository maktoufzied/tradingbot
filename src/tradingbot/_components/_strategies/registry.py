import polars as pl

from ..models import Direction, SwingPoint
from .protocol import StopStrategyProtocol


class StrategyRegistry:
    """Registry for stop loss strategies."""

    _instance: StrategyRegistry | None = None

    def __init__(self) -> None:
        self._strategies: dict[str, StopStrategyProtocol] = {}
        self._default: StopStrategyProtocol | None = None

    @classmethod
    def get_instance(cls) -> StrategyRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, strategy: StopStrategyProtocol, *, default: bool = False) -> None:
        self._strategies[strategy.name] = strategy
        if default or self._default is None:
            self._default = strategy

    def get(self, name: str) -> StopStrategyProtocol:
        if name not in self._strategies:
            raise KeyError(f"Strategy '{name}' not found. Available: {list(self._strategies.keys())}")
        return self._strategies[name]

    @property
    def default(self) -> StopStrategyProtocol:
        if self._default is None:
            raise RuntimeError("No strategies registered")
        return self._default

    def list_strategies(self) -> list[str]:
        return list(self._strategies.keys())


def get_registry() -> StrategyRegistry:
    return StrategyRegistry.get_instance()


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
        impl: StopStrategyProtocol = registry.get(strategy) if strategy else registry.default
        return impl.calc_stop(direction, entry, df, idx, swings)

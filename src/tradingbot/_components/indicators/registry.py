"""Indicator registry."""

from tradingbot.interfaces import IndicatorProtocol, Registry


class IndicatorRegistry(Registry[IndicatorProtocol]):
    """Registry for indicator implementations."""

    def get_enabled(self, names: list[str]) -> list[IndicatorProtocol]:
        """Get indicators by name list."""
        return [self._plugins[n] for n in names if n in self._plugins]


def get_registry() -> IndicatorRegistry:
    return IndicatorRegistry()

"""Indicator system with auto-discovery and registration."""

import importlib
import pkgutil
from pathlib import Path
from typing import cast

from tradingbot.config import get_indicator_config
from tradingbot.interfaces import IndicatorProtocol

from .registry import IndicatorRegistry, get_registry

__all__ = ["IndicatorRegistry", "get_registry"]


def _load_plugins(registry: IndicatorRegistry, enabled: list[str]) -> None:
    """Auto-discover and register all indicator plugins."""
    plugins_path = Path(__file__).parent / "plugins"
    config = get_indicator_config()

    for module_info in pkgutil.iter_modules([str(plugins_path)]):
        if module_info.name.startswith("_"):
            continue

        module = importlib.import_module(f".plugins.{module_info.name}", package=__name__)

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and hasattr(attr, "name")
                and hasattr(attr, "compute")
                and attr.__module__ == module.__name__
            ):
                instance = _create_instance(attr, config)
                is_default = instance.name in enabled
                registry.register(instance, default=is_default)


def _create_instance(cls: type, config: object) -> IndicatorProtocol:
    """Create indicator instance with config-based parameters."""
    indicator_config = getattr(config, cls.__name__.lower().replace("indicator", ""), None)
    if indicator_config:
        return cast(IndicatorProtocol, cls(**vars(indicator_config)))
    return cast(IndicatorProtocol, cls())


def _bootstrap() -> None:
    config = get_indicator_config()
    registry = get_registry()
    _load_plugins(registry, config.enabled)


_bootstrap()

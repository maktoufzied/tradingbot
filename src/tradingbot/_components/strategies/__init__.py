import importlib
import pkgutil
from pathlib import Path

from tradingbot.config import get_config_value
from tradingbot.interfaces import ExitStrategyProtocol

from .registry import ExitStrategy, StrategyRegistry, get_registry

__all__ = ["ExitStrategy", "get_registry"]


def _load_plugins(registry: StrategyRegistry, default_strategy: str) -> None:
    """Auto-discover and register all exit strategy plugins."""
    plugins_path = Path(__file__).parent / "plugins"

    for module_info in pkgutil.iter_modules([str(plugins_path)]):
        if module_info.name.startswith("_"):
            continue

        module = importlib.import_module(f".plugins.{module_info.name}", package=__name__)

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and hasattr(attr, "name")
                and hasattr(attr, "calc")
                and attr.__module__ == module.__name__
            ):
                instance: ExitStrategyProtocol = attr()
                is_default = instance.name == default_strategy
                registry.register(instance, default=is_default)


def _bootstrap() -> None:
    default_strategy = get_config_value("strategy", "stop", default="swing")
    registry = get_registry()
    _load_plugins(registry, default_strategy)


_bootstrap()

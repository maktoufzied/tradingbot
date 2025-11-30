import importlib
import pkgutil
import tomllib
from pathlib import Path
from typing import Any

from .protocol import StopStrategyProtocol
from .registry import StopStrategy, StrategyRegistry, get_registry

__all__ = ["StopStrategy", "get_registry"]


def _load_config() -> str:
    """Load default strategy from config file."""
    config_path: Path = Path.cwd() / "tradingbot.toml"
    if not config_path.exists():
        return "swing"

    with open(config_path, "rb") as f:
        data: dict[str, Any] = tomllib.load(f)

    result = data.get("tradingbot", {}).get("strategy", {}).get("stop", "swing")
    return str(result)


def _load_plugins(registry: StrategyRegistry, default_strategy: str) -> None:
    """Auto-discover and register all strategy plugins."""
    plugins_path: Path = Path(__file__).parent / "plugins"

    for module_info in pkgutil.iter_modules([str(plugins_path)]):
        if module_info.name.startswith("_"):
            continue

        module = importlib.import_module(f".plugins.{module_info.name}", package=__name__)

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and hasattr(attr, "name")
                and hasattr(attr, "calc_stop")
                and attr.__module__ == module.__name__
            ):
                instance: StopStrategyProtocol = attr()
                is_default: bool = instance.name == default_strategy
                registry.register(instance, default=is_default)


def _bootstrap() -> None:
    default_strategy: str = _load_config()
    registry: StrategyRegistry = get_registry()
    _load_plugins(registry, default_strategy)


_bootstrap()

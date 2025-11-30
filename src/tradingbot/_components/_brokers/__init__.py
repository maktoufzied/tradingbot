"""Broker abstraction layer for live trading."""

import importlib
import pkgutil
import tomllib
from pathlib import Path

from .protocol import BrokerProtocol
from .registry import Broker, BrokerRegistry, get_registry

__all__ = ["Broker", "BrokerProtocol", "get_registry"]


def _load_config() -> str:
    """Load default broker from config file."""
    config_path: Path = Path.cwd() / "tradingbot.toml"
    if not config_path.exists():
        return "paper"

    with open(config_path, "rb") as f:
        data: dict = tomllib.load(f)

    return data.get("tradingbot", {}).get("live", {}).get("broker", "paper")


def _load_plugins(registry: BrokerRegistry, default_broker: str) -> None:
    """Auto-discover and register all broker plugins."""
    plugins_path: Path = Path(__file__).parent / "plugins"

    for module_info in pkgutil.iter_modules([str(plugins_path)]):
        if module_info.name.startswith("_"):
            continue

        module = importlib.import_module(f".plugins.{module_info.name}", package=__name__)

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BrokerProtocol)
                and attr is not BrokerProtocol
                and hasattr(attr, "name")
            ):
                instance: BrokerProtocol = attr()
                is_default: bool = instance.name == default_broker
                registry.register(instance, default=is_default)


def _bootstrap() -> None:
    """Initialize the broker registry."""
    default_broker: str = _load_config()
    registry: BrokerRegistry = get_registry()
    _load_plugins(registry, default_broker)


_bootstrap()

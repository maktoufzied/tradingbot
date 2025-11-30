"""Real-time data feed abstraction layer."""

import importlib
import pkgutil
import tomllib
from pathlib import Path

from .protocol import DataFeedProtocol
from .registry import FeedRegistry, get_registry

__all__ = ["DataFeedProtocol", "get_registry"]


def _load_config() -> str:
    """Load default feed from config file."""
    config_path: Path = Path.cwd() / "tradingbot.toml"
    if not config_path.exists():
        return "polling"

    with open(config_path, "rb") as f:
        data: dict = tomllib.load(f)

    return data.get("tradingbot", {}).get("live", {}).get("feed", "polling")


def _load_plugins(registry: FeedRegistry, default_feed: str) -> None:
    """Auto-discover and register all feed plugins."""
    plugins_path: Path = Path(__file__).parent / "plugins"

    for module_info in pkgutil.iter_modules([str(plugins_path)]):
        if module_info.name.startswith("_"):
            continue

        module = importlib.import_module(f".plugins.{module_info.name}", package=__name__)

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, DataFeedProtocol)
                and attr is not DataFeedProtocol
                and hasattr(attr, "name")
            ):
                instance: DataFeedProtocol = attr()
                is_default: bool = instance.name == default_feed
                registry.register(instance, default=is_default)


def _bootstrap() -> None:
    """Initialize the feed registry."""
    default_feed: str = _load_config()
    registry: FeedRegistry = get_registry()
    _load_plugins(registry, default_feed)


_bootstrap()

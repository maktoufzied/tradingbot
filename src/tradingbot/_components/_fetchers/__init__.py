import importlib
import pkgutil
import tomllib
from pathlib import Path
from typing import Any

from .protocol import DataFetcherProtocol
from .registry import DataFetcher, FetcherRegistry, get_registry

__all__ = ["DataFetcher", "get_registry"]


def _load_config() -> str:
    """Load default fetcher from config file."""
    config_path: Path = Path.cwd() / "tradingbot.toml"
    if not config_path.exists():
        return "yahoo"

    with open(config_path, "rb") as f:
        data: dict[str, Any] = tomllib.load(f)

    result = data.get("tradingbot", {}).get("fetcher", "yahoo")
    return str(result)


def _load_plugins(registry: FetcherRegistry, default_fetcher: str) -> None:
    """Auto-discover and register all fetcher plugins."""
    plugins_path: Path = Path(__file__).parent / "plugins"

    for module_info in pkgutil.iter_modules([str(plugins_path)]):
        if module_info.name.startswith("_"):
            continue

        module = importlib.import_module(f".plugins.{module_info.name}", package=__name__)

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, DataFetcherProtocol) and attr is not DataFetcherProtocol:
                instance: DataFetcherProtocol = attr()
                is_default: bool = instance.name == default_fetcher
                registry.register(instance, default=is_default)


def _bootstrap() -> None:
    default_fetcher: str = _load_config()
    registry: FetcherRegistry = get_registry()
    _load_plugins(registry, default_fetcher)


_bootstrap()

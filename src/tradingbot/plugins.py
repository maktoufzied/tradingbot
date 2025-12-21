"""Generic plugin loader for registry-based systems."""

import importlib
import pkgutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tradingbot.config import get_config_value
from tradingbot.interfaces import NamedPlugin, PluginRegistry


def _load_plugins[P: NamedPlugin](
    registry: PluginRegistry[P],
    plugins_path: Path,
    protocol_type: type,
    package: str,
    default_name: str,
) -> None:
    """Auto-discover and register all plugins from a directory."""
    for module_info in pkgutil.iter_modules([str(plugins_path)]):
        if module_info.name.startswith("_"):
            continue

        module = importlib.import_module(f".plugins.{module_info.name}", package=package)

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, protocol_type)
                and attr is not protocol_type
                and hasattr(attr, "name")
            ):
                try:
                    instance: Any = attr()
                    is_default = instance.name == default_name
                    registry.register(instance, default=is_default)
                except (ValueError, OSError):
                    pass


def bootstrap[P: NamedPlugin](
    get_registry: Callable[[], PluginRegistry[P]],
    protocol_type: type,
    package: str,
    *config_keys: str,
    default: str,
) -> None:
    """Bootstrap a plugin registry.

    Args:
        get_registry: Function to get the registry singleton
        protocol_type: The protocol type that plugins must implement
        package: The package name for importing
        *config_keys: Config key path (e.g., "live", "broker" or "strategy", "stop")
        default: Default plugin name if not configured
    """
    default_name = get_config_value(*config_keys, default=default)
    registry = get_registry()
    module = importlib.import_module(package)
    module_file = module.__file__
    if module_file is None:
        msg = f"Cannot determine file path for module {package}"
        raise RuntimeError(msg)
    plugins_path = Path(module_file).parent / "plugins"
    _load_plugins(registry, plugins_path, protocol_type, package, default_name)

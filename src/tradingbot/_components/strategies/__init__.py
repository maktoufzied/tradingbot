"""Strategy system with clean separation of entry and exit logic."""

from .interfaces import Entry, EntryStrategy, Exit, ExitStrategy
from .registry import get_entry_registry, get_exit_registry

__all__ = [
    "Entry",
    "EntryStrategy",
    "Exit",
    "ExitStrategy",
    "get_entry_registry",
    "get_exit_registry",
]

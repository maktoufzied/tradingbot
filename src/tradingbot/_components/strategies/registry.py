"""Registry for entry and exit strategies."""

from typing import Final

from .interfaces import EntryStrategy, ExitStrategy

_entry_registry: dict[str, EntryStrategy] = {}
_exit_registry: dict[str, ExitStrategy] = {}
_initialized: bool = False


def _bootstrap() -> None:
    """Load all strategy plugins."""
    global _initialized
    if _initialized:
        return

    # Import entry strategies to trigger registration
    from .entry import (  # noqa: F401
        atr_breakout,
        fair_value_gaps,
        gap_and_go,
        liquidity_sweeps,
        orb,
        order_blocks,
        power_hour_reversal,
        rsi_divergence,
        swing_break,
        vwap_reversion,
    )

    # Import exit strategies to trigger registration
    from .exit import atr, fixed, swing  # noqa: F401

    _initialized = True


def register_entry(strategy: EntryStrategy) -> None:
    """Register an entry strategy."""
    _entry_registry[strategy.name] = strategy


def register_exit(strategy: ExitStrategy) -> None:
    """Register an exit strategy."""
    _exit_registry[strategy.name] = strategy


class EntryRegistry:
    """Registry for entry strategies."""

    def get(self, name: str) -> EntryStrategy:
        """Get entry strategy by name."""
        _bootstrap()
        if name not in _entry_registry:
            available = ", ".join(_entry_registry.keys())
            raise KeyError(f"Unknown entry strategy '{name}'. Available: {available}")
        return _entry_registry[name]

    def list(self) -> list[str]:
        """List all registered entry strategies."""
        _bootstrap()
        return list(_entry_registry.keys())


class ExitRegistry:
    """Registry for exit strategies."""

    def get(self, name: str) -> ExitStrategy:
        """Get exit strategy by name."""
        _bootstrap()
        if name not in _exit_registry:
            available = ", ".join(_exit_registry.keys())
            raise KeyError(f"Unknown exit strategy '{name}'. Available: {available}")
        return _exit_registry[name]

    def list(self) -> list[str]:
        """List all registered exit strategies."""
        _bootstrap()
        return list(_exit_registry.keys())


_entry_registry_instance: Final = EntryRegistry()
_exit_registry_instance: Final = ExitRegistry()


def get_entry_registry() -> EntryRegistry:
    """Get the entry strategy registry."""
    return _entry_registry_instance


def get_exit_registry() -> ExitRegistry:
    """Get the exit strategy registry."""
    return _exit_registry_instance

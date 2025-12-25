"""View mode configurations for the TUI.

Defines different information density levels that users can switch between.
"""

from dataclasses import dataclass
from enum import Enum, auto


class ViewMode(Enum):
    """Available view density modes."""

    ESSENTIAL = auto()  # Price + signal only
    DETAILED = auto()  # + sparkline + position
    MAXIMUM = auto()  # + all stats + risk meter


@dataclass(frozen=True, slots=True)
class ViewConfig:
    """Configuration for a view mode."""

    show_sparkline: bool
    show_position: bool
    show_stats_bar: bool
    show_risk_meter: bool
    show_swing_points: bool
    card_height: int
    stats_bar_height: int


VIEW_CONFIGS: dict[ViewMode, ViewConfig] = {
    ViewMode.ESSENTIAL: ViewConfig(
        show_sparkline=False,
        show_position=False,
        show_stats_bar=True,
        show_risk_meter=False,
        show_swing_points=False,
        card_height=4,
        stats_bar_height=3,
    ),
    ViewMode.DETAILED: ViewConfig(
        show_sparkline=True,
        show_position=True,
        show_stats_bar=True,
        show_risk_meter=True,
        show_swing_points=False,
        card_height=10,
        stats_bar_height=5,
    ),
    ViewMode.MAXIMUM: ViewConfig(
        show_sparkline=True,
        show_position=True,
        show_stats_bar=True,
        show_risk_meter=True,
        show_swing_points=True,
        card_height=14,
        stats_bar_height=6,
    ),
}


def get_config(mode: ViewMode) -> ViewConfig:
    """Get configuration for a view mode."""
    return VIEW_CONFIGS[mode]


def next_mode(current: ViewMode) -> ViewMode:
    """Get the next view mode in cycle."""
    modes = list(ViewMode)
    idx = modes.index(current)
    return modes[(idx + 1) % len(modes)]


def mode_name(mode: ViewMode) -> str:
    """Get human-readable name for a view mode."""
    names = {
        ViewMode.ESSENTIAL: "Essential",
        ViewMode.DETAILED: "Detailed",
        ViewMode.MAXIMUM: "Maximum",
    }
    return names[mode]

"""Color theme for the trading TUI.

Bloomberg amber + modern gradient styling.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Theme:
    """Trading terminal color scheme."""

    # Base colors
    background: str = "#0a0a0f"
    surface: str = "#12121a"
    surface_dark: str = "#0f0f18"
    surface_light: str = "#1a1a24"

    # Primary (Bloomberg amber)
    primary: str = "#ffaa00"
    primary_dim: str = "#cc8800"
    primary_bright: str = "#ffcc44"

    # Semantic colors
    positive: str = "#00ff88"
    positive_dim: str = "#00cc6a"
    negative: str = "#ff3366"
    negative_dim: str = "#cc2952"
    neutral: str = "#00d4ff"
    neutral_dim: str = "#00a8cc"
    warning: str = "#ffaa00"

    # Text colors
    text: str = "#ffffff"
    text_secondary: str = "#b0b0b8"
    text_dim: str = "#6a6a7a"
    text_muted: str = "#4a4a5a"

    # Border colors
    border: str = "#2a2a3a"
    border_focus: str = "#00ff88"
    border_dim: str = "#1a1a2a"

    # Status colors
    connected: str = "#00ff88"
    disconnected: str = "#ff3366"
    warning_status: str = "#ffaa00"


THEME = Theme()


# CSS color variables for use in TCSS
CSS_VARS = f"""
$bg: {THEME.background};
$surface: {THEME.surface};
$surface-dark: {THEME.surface_dark};
$surface-light: {THEME.surface_light};

$primary: {THEME.primary};
$primary-dim: {THEME.primary_dim};
$primary-bright: {THEME.primary_bright};

$positive: {THEME.positive};
$positive-dim: {THEME.positive_dim};
$negative: {THEME.negative};
$negative-dim: {THEME.negative_dim};
$neutral: {THEME.neutral};
$neutral-dim: {THEME.neutral_dim};
$warning: {THEME.warning};

$text: {THEME.text};
$text-secondary: {THEME.text_secondary};
$text-dim: {THEME.text_dim};
$text-muted: {THEME.text_muted};

$border: {THEME.border};
$border-focus: {THEME.border_focus};
$border-dim: {THEME.border_dim};

$connected: {THEME.connected};
$disconnected: {THEME.disconnected};
"""

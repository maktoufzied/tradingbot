"""Trading presets - predefined strategy configurations."""

from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True)
class Preset:
    """A complete trading configuration preset."""

    name: str
    description: str = ""
    # Strategy
    entry: str = "swing_break"
    exit: str = "swing"
    # Risk
    risk_pct: float = 0.01
    rr_ratio: float = 1.5
    # Indicators
    indicators: list[str] = field(default_factory=list)
    filter_mode: str = "all"  # "all", "any", "none"
    # Time exits
    eod_exit: bool = True
    time_exit_minutes: int = 0


# Predefined presets
PRESETS: Final[dict[str, Preset]] = {
    "conservative": Preset(
        name="conservative",
        description="Low risk, filtered signals, swing-based exits",
        entry="swing_break",
        exit="swing",
        risk_pct=0.005,  # 0.5%
        rr_ratio=1.5,
        indicators=["rsi", "macd"],
        filter_mode="all",
        eod_exit=True,
        time_exit_minutes=0,
    ),
    "balanced": Preset(
        name="balanced",
        description="Moderate risk, RSI filtering, good for most markets",
        entry="swing_break",
        exit="swing",
        risk_pct=0.01,  # 1%
        rr_ratio=1.5,
        indicators=["rsi"],
        filter_mode="all",
        eod_exit=True,
        time_exit_minutes=0,
    ),
    "aggressive": Preset(
        name="aggressive",
        description="Higher risk, no filtering, ATR-based exits",
        entry="swing_break",
        exit="atr",
        risk_pct=0.02,  # 2%
        rr_ratio=2.0,
        indicators=[],
        filter_mode="none",
        eod_exit=True,
        time_exit_minutes=0,
    ),
    "scalping": Preset(
        name="scalping",
        description="Quick trades, ORB strategy, fixed tight exits",
        entry="orb",
        exit="fixed",
        risk_pct=0.005,  # 0.5%
        rr_ratio=1.0,
        indicators=[],
        filter_mode="none",
        eod_exit=True,
        time_exit_minutes=30,  # Close after 30 min
    ),
    "mean_reversion": Preset(
        name="mean_reversion",
        description="VWAP reversion, best for ranging markets",
        entry="vwap_reversion",
        exit="fixed",
        risk_pct=0.01,
        rr_ratio=1.2,
        indicators=["rsi"],
        filter_mode="all",
        eod_exit=True,
        time_exit_minutes=60,
    ),
    "momentum": Preset(
        name="momentum",
        description="ATR breakouts, trend following",
        entry="atr_breakout",
        exit="atr",
        risk_pct=0.015,
        rr_ratio=1.5,
        indicators=["macd"],
        filter_mode="all",
        eod_exit=True,
        time_exit_minutes=0,
    ),
    "divergence": Preset(
        name="divergence",
        description="RSI divergence, counter-trend at exhaustion",
        entry="rsi_divergence",
        exit="swing",
        risk_pct=0.01,
        rr_ratio=1.5,
        indicators=[],
        filter_mode="none",
        eod_exit=True,
        time_exit_minutes=0,
    ),
}


def _load_custom_presets() -> dict[str, Preset]:
    """Load custom presets from config file."""
    import tomllib
    from pathlib import Path

    config_path = Path.cwd() / "tradingbot.toml"
    if not config_path.exists():
        return {}

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    custom_presets: dict[str, Preset] = {}
    presets_data = data.get("tradingbot", {}).get("presets", {})

    for name, preset_data in presets_data.items():
        custom_presets[name] = Preset(
            name=name,
            description=preset_data.get("description", f"Custom preset: {name}"),
            entry=preset_data.get("entry", "swing_break"),
            exit=preset_data.get("exit", "swing"),
            risk_pct=preset_data.get("risk_pct", 0.01),
            rr_ratio=preset_data.get("rr_ratio", 1.5),
            indicators=preset_data.get("indicators", []),
            filter_mode=preset_data.get("filter_mode", "all"),
            eod_exit=preset_data.get("eod_exit", True),
            time_exit_minutes=preset_data.get("time_exit_minutes", 0),
        )

    return custom_presets


def get_preset(name: str) -> Preset:
    """Get a preset by name (custom presets override built-in)."""
    custom = _load_custom_presets()
    all_presets = {**PRESETS, **custom}  # Custom overrides built-in

    if name not in all_presets:
        available = ", ".join(all_presets.keys())
        raise KeyError(f"Unknown preset '{name}'. Available: {available}")
    return all_presets[name]


def list_presets() -> list[str]:
    """List all available preset names."""
    custom = _load_custom_presets()
    all_presets = {**PRESETS, **custom}
    return list(all_presets.keys())

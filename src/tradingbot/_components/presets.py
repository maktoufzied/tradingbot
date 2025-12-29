"""Trading presets - predefined strategy configurations."""

from dataclasses import dataclass, field
from typing import Final

from tradingbot.types import PartialExitLevel


@dataclass(frozen=True)
class Preset:
    """A complete trading configuration preset."""

    name: str
    description: str = ""
    # Timeframe
    interval: str = "1h"
    period: str = "1y"
    # Strategy
    entry: str = "swing_break"
    exit: str = "swing"
    # Risk
    risk_pct: float = 0.01
    rr_ratio: float = 1.5
    atr_sizing: bool = False
    # Partial exits: list of {r_multiple, exit_pct} levels (empty = all-or-nothing)
    partial_exit_levels: tuple[PartialExitLevel, ...] = ()
    # Indicators
    indicators: list[str] = field(default_factory=list)
    filter_mode: str = "all"  # "all", "any", "none"
    # Time exits
    eod_exit: bool = True
    time_exit_minutes: int = 0


# Predefined presets
# Organized by trading style: day trading (intraday) vs swing trading (multi-day)
#
# Available indicators: rsi, macd, bollinger, ema_crossover, stochastic, adx, keltner
PRESETS: Final[dict[str, Preset]] = {
    # =========================================================================
    # DAY TRADING PRESETS (intraday, eod_exit=True)
    # =========================================================================
    "scalping": Preset(
        name="scalping",
        description="5m quick trades, ORB strategy, stochastic filter",
        interval="5m",
        period="2mo",
        entry="orb",
        exit="fixed",
        risk_pct=0.005,  # 0.5%
        rr_ratio=1.5,
        indicators=["stochastic"],  # Fast oscillator for quick trades
        filter_mode="all",
        eod_exit=True,
        time_exit_minutes=30,
    ),
    "day_momentum": Preset(
        name="day_momentum",
        description="15m intraday momentum, ADX trend filter",
        interval="15m",
        period="3mo",
        entry="atr_breakout",
        exit="atr",
        risk_pct=0.01,  # 1%
        rr_ratio=1.5,
        indicators=["adx"],  # Only trade when trending (ADX > 25)
        filter_mode="all",
        eod_exit=True,
        time_exit_minutes=0,
    ),
    "mean_reversion": Preset(
        name="mean_reversion",
        description="15m VWAP reversion, Bollinger band filter",
        interval="15m",
        period="2mo",
        entry="vwap_reversion",
        exit="fixed",
        risk_pct=0.01,
        rr_ratio=1.2,
        indicators=["bollinger"],  # Price at bands = reversal likely
        filter_mode="all",
        eod_exit=True,
        time_exit_minutes=60,
    ),
    "day_breakout": Preset(
        name="day_breakout",
        description="15m Keltner channel breakouts, trend confirmed",
        interval="15m",
        period="3mo",
        entry="atr_breakout",
        exit="atr",
        risk_pct=0.01,
        rr_ratio=1.5,
        indicators=["keltner", "ema_crossover"],  # Volatility + trend
        filter_mode="all",
        eod_exit=True,
        time_exit_minutes=0,
    ),
    # =========================================================================
    # SWING TRADING PRESETS (multi-day, eod_exit=False)
    # =========================================================================
    "swing_conservative": Preset(
        name="swing_conservative",
        description="1h swing, EMA trend filter, hold overnight",
        interval="1h",
        period="1y",
        entry="swing_break",
        exit="swing",
        risk_pct=0.005,  # 0.5%
        rr_ratio=2.0,
        indicators=["ema_crossover"],  # Trade with the trend
        filter_mode="all",
        eod_exit=False,
        time_exit_minutes=0,
    ),
    "swing_balanced": Preset(
        name="swing_balanced",
        description="1h swing, ADX trending filter, hold overnight",
        interval="1h",
        period="1y",
        entry="swing_break",
        exit="swing",
        risk_pct=0.01,  # 1%
        rr_ratio=2.0,
        indicators=["adx"],  # Only trade in trending markets
        filter_mode="all",
        eod_exit=False,
        time_exit_minutes=0,
    ),
    "swing_aggressive": Preset(
        name="swing_aggressive",
        description="1h swing, no filter, ATR exits, hold overnight",
        interval="1h",
        period="1y",
        entry="swing_break",
        exit="atr",
        risk_pct=0.02,  # 2%
        rr_ratio=2.5,
        indicators=[],  # No filter - take all signals
        filter_mode="none",
        eod_exit=False,
        time_exit_minutes=0,
    ),
    "divergence": Preset(
        name="divergence",
        description="1h RSI divergence, MACD confirmation",
        interval="1h",
        period="1y",
        entry="rsi_divergence",
        exit="swing",
        risk_pct=0.01,
        rr_ratio=2.0,
        indicators=["macd"],  # MACD confirms momentum shift
        filter_mode="all",
        eod_exit=False,
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
        # Parse partial exit levels (validation in PartialExitLevel.__post_init__)
        partial_levels_data = preset_data.get("partial_exit_levels", [])
        partial_exit_levels: list[PartialExitLevel] = []
        seen_r_multiples: set[float] = set()

        for level in partial_levels_data:
            r_mult = level["r_multiple"]
            if r_mult in seen_r_multiples:
                raise ValueError(f"preset '{name}': duplicate r_multiple {r_mult}")
            seen_r_multiples.add(r_mult)
            partial_exit_levels.append(PartialExitLevel(r_multiple=r_mult, exit_pct=level["exit_pct"]))

        custom_presets[name] = Preset(
            name=name,
            description=preset_data.get("description", f"Custom preset: {name}"),
            interval=preset_data.get("interval", "1h"),
            period=preset_data.get("period", "1y"),
            entry=preset_data.get("entry", "swing_break"),
            exit=preset_data.get("exit", "swing"),
            risk_pct=preset_data.get("risk_pct", 0.01),
            rr_ratio=preset_data.get("rr_ratio", 1.5),
            atr_sizing=preset_data.get("atr_sizing", False),
            partial_exit_levels=tuple(partial_exit_levels),
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


def get_strategy_defaults() -> dict[str, str]:
    """Load strategy defaults from config file."""
    import tomllib
    from pathlib import Path

    defaults: dict[str, str] = {
        "interval": "1h",
        "period": "1y",
        "entry_strategy": "swing_break",
        "exit_strategy": "swing",
    }

    config_path = Path.cwd() / "tradingbot.toml"
    if not config_path.exists():
        return defaults

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    strategy = data.get("tradingbot", {}).get("strategy", {})
    if "interval" in strategy:
        defaults["interval"] = strategy["interval"]
    if "period" in strategy:
        defaults["period"] = strategy["period"]
    if "entry" in strategy:
        defaults["entry_strategy"] = strategy["entry"]
    if "exit" in strategy:
        defaults["exit_strategy"] = strategy["exit"]

    return defaults


def save_preset(
    name: str,
    *,
    symbol: str,
    interval: str,
    period: str,
    swing_lb: int,
    risk_pct: float,
    rr_ratio: float,
    total_return: float | None = None,
    max_drawdown: float | None = None,
    entry_strategy: str | None = None,
    exit_strategy: str | None = None,
    atr_sizing: bool | None = None,
    partial_exit_levels: tuple[PartialExitLevel, ...] | None = None,
) -> None:
    """Save optimization results as a custom preset to tradingbot.toml.

    Args:
        name: Preset name
        symbol: Symbol that was optimized (for description)
        interval: Bar interval
        period: History period
        swing_lb: Swing lookback
        risk_pct: Risk percentage (0.01 = 1%)
        rr_ratio: Reward/risk ratio
        total_return: Optional backtest return for description
        max_drawdown: Optional max drawdown for description
        entry_strategy: Entry strategy used (optional)
        exit_strategy: Exit strategy used (optional)
        atr_sizing: ATR-based position sizing (optional)
        partial_exit_levels: Partial exit levels (optional)
    """
    from pathlib import Path

    import tomlkit

    config_path = Path.cwd() / "tradingbot.toml"

    if config_path.exists():
        content = config_path.read_text()
        doc = tomlkit.parse(content)
    else:
        doc = tomlkit.document()
        doc.add("tradingbot", tomlkit.table())

    # Ensure tradingbot.presets exists
    if "tradingbot" not in doc:
        doc.add("tradingbot", tomlkit.table())
    if "presets" not in doc["tradingbot"]:  # type: ignore[operator]
        doc["tradingbot"].add("presets", tomlkit.table())  # type: ignore[union-attr]

    # Build description
    desc_parts = [f"Optimized for {symbol}"]
    if total_return is not None:
        desc_parts.append(f"return={total_return:+.1f}%")
    if max_drawdown is not None:
        desc_parts.append(f"DD={max_drawdown:.1f}%")
    description = ", ".join(desc_parts)

    # Create preset table
    preset = tomlkit.table()
    preset.add("description", description)
    preset.add("interval", interval)
    preset.add("period", period)
    preset.add("swing_lb", swing_lb)
    preset.add("risk_pct", round(risk_pct, 4))  # Round for readability
    preset.add("rr_ratio", round(rr_ratio, 1))
    if entry_strategy:
        preset.add("entry", entry_strategy)
    if exit_strategy:
        preset.add("exit", exit_strategy)
    if atr_sizing is not None:
        preset.add("atr_sizing", atr_sizing)
    if partial_exit_levels:
        levels_array = tomlkit.array()
        for level in partial_exit_levels:
            level_table = tomlkit.inline_table()
            level_table.append("r_multiple", level.r_multiple)
            level_table.append("exit_pct", level.exit_pct)
            levels_array.append(level_table)
        preset.add("partial_exit_levels", levels_array)

    doc["tradingbot"]["presets"].add(name, preset)  # type: ignore[union-attr,index]

    config_path.write_text(tomlkit.dumps(doc))

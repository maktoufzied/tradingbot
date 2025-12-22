"""Configuration dataclasses and accessors."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

CONFIG_FILE: Final = "tradingbot.toml"

_config: Config | None = None


@dataclass(frozen=True)
class StrategyConfig:
    """Strategy configuration."""

    stop: str = "swing"


@dataclass(frozen=True)
class BotConfig:
    """Bot parameter configuration."""

    swing_lb: int = 5
    risk_pct: float = 0.01
    rr_ratio: float = 2.0
    capital: float = 100000


@dataclass(frozen=True)
class EngineRiskConfig:
    """Engine risk controls configuration."""

    max_daily_loss_pct: float = 0.05
    max_position_size_pct: float = 0.10
    max_open_positions: int = 5
    trading_hours_only: bool = True
    circuit_breaker_loss_pct: float = 0.03


@dataclass(frozen=True)
class AlpacaConfig:
    """Alpaca API configuration."""

    api_key: str | None = None
    secret_key: str | None = None
    paper: bool = True


@dataclass(frozen=True)
class EngineConfig:
    """Engine configuration."""

    broker: str = "paper"
    feed: str = "yahoo"
    symbols: list[str] = field(default_factory=list)
    risk: EngineRiskConfig = field(default_factory=EngineRiskConfig)
    alpaca: AlpacaConfig = field(default_factory=AlpacaConfig)


@dataclass(frozen=True)
class Config:
    """Root configuration."""

    fetcher: str = "yahoo"
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    bot: BotConfig = field(default_factory=BotConfig)
    engine: EngineConfig = field(default_factory=EngineConfig)


def _parse_config(data: dict[str, Any]) -> Config:
    """Parse raw TOML data into Config dataclass."""
    root = data.get("tradingbot", {})

    strategy_data = root.get("strategy", {})
    strategy = StrategyConfig(
        stop=strategy_data.get("stop", "swing"),
    )

    bot_data = root.get("bot", {})
    bot = BotConfig(
        swing_lb=bot_data.get("swing_lb", 5),
        risk_pct=bot_data.get("risk_pct", 0.01),
        rr_ratio=bot_data.get("rr_ratio", 2.0),
        capital=bot_data.get("capital", 100000),
    )

    engine_data = root.get("engine", {})
    risk_data = engine_data.get("risk", {})
    alpaca_data = engine_data.get("alpaca", {})

    engine_risk = EngineRiskConfig(
        max_daily_loss_pct=risk_data.get("max_daily_loss_pct", 0.05),
        max_position_size_pct=risk_data.get("max_position_size_pct", 0.10),
        max_open_positions=risk_data.get("max_open_positions", 5),
        trading_hours_only=risk_data.get("trading_hours_only", True),
        circuit_breaker_loss_pct=risk_data.get("circuit_breaker_loss_pct", 0.03),
    )

    alpaca = AlpacaConfig(
        api_key=alpaca_data.get("api_key"),
        secret_key=alpaca_data.get("secret_key"),
        paper=alpaca_data.get("paper", True),
    )

    engine = EngineConfig(
        broker=engine_data.get("broker", "paper"),
        feed=engine_data.get("feed", "yahoo"),
        symbols=engine_data.get("symbols", []),
        risk=engine_risk,
        alpaca=alpaca,
    )

    return Config(
        fetcher=root.get("fetcher", "yahoo"),
        strategy=strategy,
        bot=bot,
        engine=engine,
    )


def get_config() -> Config:
    """Get the parsed config, cached after first load."""
    global _config
    if _config is not None:
        return _config

    config_path = Path.cwd() / CONFIG_FILE
    if not config_path.exists():
        _config = Config()
        return _config

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    _config = _parse_config(data)
    return _config


def get_bot_config() -> BotConfig:
    """Get bot configuration."""
    return get_config().bot


def get_engine_config() -> EngineConfig:
    """Get engine configuration."""
    return get_config().engine


def get_config_value(*keys: str, default: str) -> str:
    """Get a config value by key path.

    Args:
        *keys: Path of keys to traverse (e.g., "live", "broker")
        default: Default value if not found
    """
    config = get_config()
    result: object = config

    for key in keys:
        if not hasattr(result, key):
            return default
        result = getattr(result, key)

    return str(result) if result else default

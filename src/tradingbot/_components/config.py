"""Centralized configuration loading from tradingbot.toml."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

CONFIG_FILE: Final[str] = "tradingbot.toml"


@dataclass(frozen=True)
class BotConfig:
    """Bot parameter configuration."""

    swing_lb: int = 5
    risk_pct: float = 0.01
    rr_ratio: float = 2.0
    capital: float = 100000


@dataclass(frozen=True)
class LiveRiskConfig:
    """Live trading risk controls configuration."""

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
class LiveConfig:
    """Live trading configuration."""

    broker: str = "paper"
    feed: str = "polling"
    symbols: list[str] | None = None
    risk: LiveRiskConfig = LiveRiskConfig()
    alpaca: AlpacaConfig = AlpacaConfig()


def _load_toml() -> dict[str, Any]:
    """Load and cache the toml config file."""
    config_path: Path = Path.cwd() / CONFIG_FILE
    if not config_path.exists():
        return {}

    with open(config_path, "rb") as f:
        return tomllib.load(f)


def get_fetcher() -> str:
    """Get configured fetcher name."""
    data = _load_toml()
    result = data.get("tradingbot", {}).get("fetcher", "yahoo")
    return str(result)


def get_stop_strategy() -> str:
    """Get configured stop strategy name."""
    data = _load_toml()
    result = data.get("tradingbot", {}).get("strategy", {}).get("stop", "swing")
    return str(result)


def get_bot_config() -> BotConfig:
    """Get bot parameter configuration."""
    data = _load_toml()
    bot_data = data.get("tradingbot", {}).get("bot", {})

    return BotConfig(
        swing_lb=bot_data.get("swing_lb", 5),
        risk_pct=bot_data.get("risk_pct", 0.01),
        rr_ratio=bot_data.get("rr_ratio", 2.0),
        capital=bot_data.get("capital", 100000),
    )


def get_live_config() -> LiveConfig:
    """Get live trading configuration."""
    data = _load_toml()
    live_data = data.get("tradingbot", {}).get("live", {})
    risk_data = live_data.get("risk", {})
    alpaca_data = live_data.get("alpaca", {})

    risk_config = LiveRiskConfig(
        max_daily_loss_pct=risk_data.get("max_daily_loss_pct", 0.05),
        max_position_size_pct=risk_data.get("max_position_size_pct", 0.10),
        max_open_positions=risk_data.get("max_open_positions", 5),
        trading_hours_only=risk_data.get("trading_hours_only", True),
        circuit_breaker_loss_pct=risk_data.get("circuit_breaker_loss_pct", 0.03),
    )

    alpaca_config = AlpacaConfig(
        api_key=alpaca_data.get("api_key"),
        secret_key=alpaca_data.get("secret_key"),
        paper=alpaca_data.get("paper", True),
    )

    return LiveConfig(
        broker=live_data.get("broker", "paper"),
        feed=live_data.get("feed", "polling"),
        symbols=live_data.get("symbols"),
        risk=risk_config,
        alpaca=alpaca_config,
    )

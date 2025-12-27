"""Configuration dataclasses and accessors."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

CONFIG_FILE: Final = "tradingbot.toml"

_config: Config | None = None


@dataclass(frozen=True)
class RSIConfig:
    """RSI indicator configuration."""

    period: int = 14
    overbought: float = 70.0
    oversold: float = 30.0


@dataclass(frozen=True)
class MACDConfig:
    """MACD indicator configuration."""

    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9


@dataclass(frozen=True)
class BollingerConfig:
    """Bollinger Bands indicator configuration."""

    period: int = 20
    std_dev: float = 2.0


@dataclass(frozen=True)
class EMACrossoverConfig:
    """EMA Crossover indicator configuration."""

    fast_period: int = 9
    slow_period: int = 21


@dataclass(frozen=True)
class StochasticConfig:
    """Stochastic Oscillator indicator configuration."""

    k_period: int = 14
    d_period: int = 3
    smooth_k: int = 3
    overbought: float = 80.0
    oversold: float = 20.0


@dataclass(frozen=True)
class ADXConfig:
    """ADX indicator configuration."""

    period: int = 14
    trend_threshold: float = 25.0


@dataclass(frozen=True)
class KeltnerConfig:
    """Keltner Channels indicator configuration."""

    ema_period: int = 20
    atr_period: int = 10
    multiplier: float = 2.0


@dataclass(frozen=True)
class IndicatorConfig:
    """Indicator system configuration."""

    enabled: list[str] = field(default_factory=lambda: ["rsi", "macd"])
    filter_mode: str = "all"  # all, any, none
    signal_mode: str = "filter"  # filter, none
    rsi: RSIConfig = field(default_factory=RSIConfig)
    macd: MACDConfig = field(default_factory=MACDConfig)
    bollinger: BollingerConfig = field(default_factory=BollingerConfig)
    ema_crossover: EMACrossoverConfig = field(default_factory=EMACrossoverConfig)
    stochastic: StochasticConfig = field(default_factory=StochasticConfig)
    adx: ADXConfig = field(default_factory=ADXConfig)
    keltner: KeltnerConfig = field(default_factory=KeltnerConfig)


@dataclass(frozen=True)
class StrategyConfig:
    """Strategy configuration - everything a preset can override."""

    preset: str | None = None  # Preset name (overrides all strategy settings)
    # Entry strategies: swing_break, vwap_reversion, orb, rsi_divergence, atr_breakout,
    #                   gap_and_go, order_blocks, fvg, liquidity_sweeps
    entry: str = "swing_break"
    exit: str = "swing"  # Exit: swing, atr, fixed
    # Risk parameters
    swing_lb: int = 5  # Swing lookback period (bars)
    risk_pct: float = 0.01  # Risk per trade (1% = 0.01)
    rr_ratio: float = 1.5  # Reward/risk ratio
    allow_short: bool = False  # Allow short selling
    # Time-based exits
    eod_exit: bool = True  # Close positions before market close
    time_exit_minutes: int = 0  # Close after N minutes (0 = disabled)
    eod_exit_minutes_before: int = 15  # Minutes before close to exit
    # Indicator filters
    indicators: IndicatorConfig = field(default_factory=IndicatorConfig)


@dataclass(frozen=True)
class BotConfig:
    """Bot configuration - account-level settings."""

    capital: float = 100000  # Starting capital ($)


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
class CacheRetentionConfig:
    """Cache retention policy (days per interval, -1 = forever)."""

    m1: int = 7
    m5: int = 30
    m15: int = 90
    h1: int = 365
    d1: int = -1

    def as_dict(self) -> dict[str, int]:
        """Return as interval -> days mapping."""
        return {
            "1m": self.m1,
            "5m": self.m5,
            "15m": self.m15,
            "1h": self.h1,
            "1d": self.d1,
        }


@dataclass(frozen=True)
class CacheConfig:
    """Cache configuration."""

    enabled: bool = True
    path: str = "~/.cache/tradingbot/tradingbot.duckdb"
    source: str = "yahoo"
    retention: CacheRetentionConfig = field(default_factory=CacheRetentionConfig)

    @property
    def db_path(self) -> Path:
        """Resolve path with ~ expansion."""
        return Path(self.path).expanduser()


@dataclass(frozen=True)
class EngineConfig:
    """Engine configuration."""

    broker: str = "paper"
    feed: str = "yahoo"
    bar_interval: str = "5m"  # 1m, 5m, or 15m - used for cache, bootstrap, and live feed
    risk: EngineRiskConfig = field(default_factory=EngineRiskConfig)
    alpaca: AlpacaConfig = field(default_factory=AlpacaConfig)


@dataclass(frozen=True)
class Config:
    """Root configuration."""

    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    bot: BotConfig = field(default_factory=BotConfig)
    engine: EngineConfig = field(default_factory=EngineConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)


def _parse_config(data: dict[str, Any]) -> Config:
    """Parse raw TOML data into Config dataclass."""
    root = data.get("tradingbot", {})

    strategy_data = root.get("strategy", {})

    # Parse indicators (nested under strategy)
    ind_data = strategy_data.get("indicators", {})
    rsi_data = ind_data.get("rsi", {})
    macd_data = ind_data.get("macd", {})

    rsi_config = RSIConfig(
        period=rsi_data.get("period", 14),
        overbought=rsi_data.get("overbought", 70.0),
        oversold=rsi_data.get("oversold", 30.0),
    )

    macd_config = MACDConfig(
        fast_period=macd_data.get("fast_period", 12),
        slow_period=macd_data.get("slow_period", 26),
        signal_period=macd_data.get("signal_period", 9),
    )

    indicators = IndicatorConfig(
        enabled=ind_data.get("enabled", ["rsi", "macd"]),
        filter_mode=ind_data.get("filter_mode", "all"),
        signal_mode=ind_data.get("signal_mode", "filter"),
        rsi=rsi_config,
        macd=macd_config,
    )

    strategy = StrategyConfig(
        preset=strategy_data.get("preset"),
        entry=strategy_data.get("entry", "swing_break"),
        exit=strategy_data.get("exit", "swing"),
        swing_lb=strategy_data.get("swing_lb", 5),
        risk_pct=strategy_data.get("risk_pct", 0.01),
        rr_ratio=strategy_data.get("rr_ratio", 1.5),
        allow_short=strategy_data.get("allow_short", False),
        eod_exit=strategy_data.get("eod_exit", True),
        time_exit_minutes=strategy_data.get("time_exit_minutes", 0),
        eod_exit_minutes_before=strategy_data.get("eod_exit_minutes_before", 15),
        indicators=indicators,
    )

    bot_data = root.get("bot", {})
    bot = BotConfig(
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
        bar_interval=engine_data.get("bar_interval", "5m"),
        risk=engine_risk,
        alpaca=alpaca,
    )

    # Parse cache config
    cache_data = root.get("cache", {})
    retention_data = cache_data.get("retention", {})

    cache_retention = CacheRetentionConfig(
        m1=retention_data.get("1m", 7),
        m5=retention_data.get("5m", 30),
        m15=retention_data.get("15m", 90),
        h1=retention_data.get("1h", 365),
        d1=retention_data.get("1d", -1),
    )

    cache = CacheConfig(
        enabled=cache_data.get("enabled", True),
        path=cache_data.get("path", "~/.cache/tradingbot/tradingbot.duckdb"),
        source=cache_data.get("source", "yahoo"),
        retention=cache_retention,
    )

    return Config(
        strategy=strategy,
        bot=bot,
        engine=engine,
        cache=cache,
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


def get_strategy_config() -> StrategyConfig:
    """Get strategy configuration."""
    return get_config().strategy


def get_engine_config() -> EngineConfig:
    """Get engine configuration."""
    return get_config().engine


def get_cache_config() -> CacheConfig:
    """Get cache configuration."""
    return get_config().cache


def get_indicator_config() -> IndicatorConfig:
    """Get indicator configuration."""
    return get_config().strategy.indicators


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

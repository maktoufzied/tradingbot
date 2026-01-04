"""Configuration dataclasses and accessors."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from tradingbot.types import PartialExitLevel

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
    atr_sizing: bool = False  # Volatility-adjusted position sizing
    # Trailing stops
    atr_trail: bool = False  # ATR-based trailing stop
    atr_trail_multiplier: float = 2.0  # Trail at high_water - (N × ATR)
    atr_trail_activation_r: float = 0.0  # Start trailing after this R-multiple (0 = immediate)
    # Partial exits: list of {r_multiple, exit_pct} levels (empty = all-or-nothing)
    partial_exit_levels: tuple[PartialExitLevel, ...] = ()
    # Time-based exits
    eod_exit: bool = True  # Close positions before market close
    time_exit_minutes: int = 0  # Close after N minutes (0 = disabled)
    eod_exit_minutes_before: int = 15  # Minutes before close to exit
    # Indicator filters
    indicators: IndicatorConfig = field(default_factory=IndicatorConfig)


@dataclass(frozen=True)
class SymbolAllocation:
    """Capital allocation for a single symbol."""

    symbol: str
    weight_pct: float  # 0.0-1.0 (50% = 0.5)

    def __post_init__(self) -> None:
        if not 0.0 < self.weight_pct <= 1.0:
            raise ValueError(f"weight_pct must be >0.0 and <=1.0, got {self.weight_pct}")


@dataclass(frozen=True)
class AllocationConfig:
    """Per-symbol capital allocation configuration."""

    enabled: bool = False
    allocations: tuple[SymbolAllocation, ...] = ()

    def __post_init__(self) -> None:
        if self.enabled:
            if not self.allocations:
                raise ValueError("allocations required when enabled=true")
            total = sum(a.weight_pct for a in self.allocations)
            if not 0.9999 <= total <= 1.0001:
                raise ValueError(f"allocations must sum to 100%, got {total * 100:.2f}%")

    def get_weight(self, symbol: str) -> float:
        """Get weight for a symbol (0.0 if not found)."""
        for alloc in self.allocations:
            if alloc.symbol == symbol:
                return alloc.weight_pct
        return 0.0

    def validate_symbols(self, symbols: list[str]) -> None:
        """Ensure all trading symbols have allocations."""
        allocated_symbols = {a.symbol for a in self.allocations}
        missing = set(symbols) - allocated_symbols
        extra = allocated_symbols - set(symbols)

        if missing:
            raise ValueError(f"Missing allocations for: {', '.join(sorted(missing))}")
        if extra:
            raise ValueError(f"Allocations for non-trading symbols: {', '.join(sorted(extra))}")


@dataclass(frozen=True)
class BotConfig:
    """Bot configuration - account-level settings."""

    capital: float = 100000  # Starting capital ($)
    allocation: AllocationConfig = field(default_factory=AllocationConfig)


@dataclass(frozen=True)
class EngineRiskConfig:
    """Engine risk controls configuration."""

    max_daily_loss_pct: float = 0.05
    max_position_size_pct: float = 0.10
    max_open_positions: int = 5
    trading_hours_only: bool = True
    circuit_breaker_loss_pct: float = 0.03


@dataclass(frozen=True)
class ProviderConfig:
    """Base provider configuration with execution costs."""

    spread_bps: float = 0.0  # Bid-ask spread in basis points
    slippage_bps: float = 0.0  # Slippage in basis points
    commission_per_share: float = 0.0  # Commission per share ($)

    @property
    def has_costs(self) -> bool:
        """Check if any costs are configured."""
        return self.spread_bps > 0 or self.slippage_bps > 0 or self.commission_per_share > 0


@dataclass(frozen=True)
class AlpacaConfig(ProviderConfig):
    """Alpaca provider configuration."""

    api_key: str | None = None
    secret_key: str | None = None
    paper: bool = True
    data_feed: str = "iex"  # "iex" (free, real-time websocket) or "sip" (paid, all exchanges)


@dataclass(frozen=True)
class PaperConfig(ProviderConfig):
    """Paper trading provider configuration."""

    pass


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
    retention: CacheRetentionConfig = field(default_factory=CacheRetentionConfig)

    @property
    def db_path(self) -> Path:
        """Resolve path with ~ expansion."""
        return Path(self.path).expanduser()


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR
    log_file: str | None = None  # Optional file path


@dataclass(frozen=True)
class HealthConfig:
    """Health check configuration."""

    enabled: bool = True  # Enable periodic health checks
    interval_minutes: int = 5  # Interval between health checks


@dataclass(frozen=True)
class EngineConfig:
    """Engine configuration."""

    provider: str = "paper"  # "alpaca" or "paper"
    bar_interval: str = "5m"  # 1m, 5m, or 15m - used for cache, bootstrap, and live feed
    risk: EngineRiskConfig = field(default_factory=EngineRiskConfig)
    alpaca: AlpacaConfig = field(default_factory=AlpacaConfig)
    paper: PaperConfig = field(default_factory=PaperConfig)

    def get_provider_config(self) -> ProviderConfig:
        """Get the configuration for the current provider."""
        if self.provider == "alpaca":
            return self.alpaca
        return self.paper


@dataclass(frozen=True)
class Config:
    """Root configuration."""

    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    bot: BotConfig = field(default_factory=BotConfig)
    engine: EngineConfig = field(default_factory=EngineConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    health: HealthConfig = field(default_factory=HealthConfig)


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

    # Parse partial exit levels (validation in PartialExitLevel.__post_init__)
    partial_levels_data = strategy_data.get("partial_exit_levels", [])
    partial_exit_levels: list[PartialExitLevel] = []
    seen_r_multiples: set[float] = set()

    for level in partial_levels_data:
        r_mult = level["r_multiple"]
        if r_mult in seen_r_multiples:
            raise ValueError(f"partial_exit_levels: duplicate r_multiple {r_mult}")
        seen_r_multiples.add(r_mult)
        partial_exit_levels.append(PartialExitLevel(r_multiple=r_mult, exit_pct=level["exit_pct"]))

    strategy = StrategyConfig(
        preset=strategy_data.get("preset"),
        entry=strategy_data.get("entry", "swing_break"),
        exit=strategy_data.get("exit", "swing"),
        swing_lb=strategy_data.get("swing_lb", 5),
        risk_pct=strategy_data.get("risk_pct", 0.01),
        rr_ratio=strategy_data.get("rr_ratio", 1.5),
        allow_short=strategy_data.get("allow_short", False),
        atr_sizing=strategy_data.get("atr_sizing", False),
        atr_trail=strategy_data.get("atr_trail", False),
        atr_trail_multiplier=strategy_data.get("atr_trail_multiplier", 2.0),
        atr_trail_activation_r=strategy_data.get("atr_trail_activation_r", 0.0),
        partial_exit_levels=tuple(partial_exit_levels),
        eod_exit=strategy_data.get("eod_exit", True),
        time_exit_minutes=strategy_data.get("time_exit_minutes", 0),
        eod_exit_minutes_before=strategy_data.get("eod_exit_minutes_before", 15),
        indicators=indicators,
    )

    bot_data = root.get("bot", {})

    # Parse allocation config
    alloc_data = bot_data.get("allocation", {})
    if alloc_data.get("enabled", False):
        allocations_list = alloc_data.get("allocations", [])
        parsed_allocations = tuple(
            SymbolAllocation(symbol=a["symbol"].upper(), weight_pct=a["weight_pct"]) for a in allocations_list
        )
        allocation = AllocationConfig(enabled=True, allocations=parsed_allocations)
    else:
        allocation = AllocationConfig()

    bot = BotConfig(
        capital=bot_data.get("capital", 100000),
        allocation=allocation,
    )

    engine_data = root.get("engine", {})
    risk_data = engine_data.get("risk", {})
    alpaca_data = engine_data.get("alpaca", {})
    paper_data = engine_data.get("paper", {})

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
        data_feed=alpaca_data.get("data_feed", "iex"),
        spread_bps=alpaca_data.get("spread_bps", 0.0),
        slippage_bps=alpaca_data.get("slippage_bps", 0.0),
        commission_per_share=alpaca_data.get("commission_per_share", 0.0),
    )

    paper = PaperConfig(
        spread_bps=paper_data.get("spread_bps", 0.0),
        slippage_bps=paper_data.get("slippage_bps", 0.0),
        commission_per_share=paper_data.get("commission_per_share", 0.0),
    )

    engine = EngineConfig(
        provider=engine_data.get("provider", "paper"),
        bar_interval=engine_data.get("bar_interval", "5m"),
        risk=engine_risk,
        alpaca=alpaca,
        paper=paper,
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
        retention=cache_retention,
    )

    # Parse logging config
    logging_data = root.get("logging", {})
    logging_config = LoggingConfig(
        level=logging_data.get("level", "INFO"),
        log_file=logging_data.get("log_file"),
    )

    # Parse health config
    health_data = root.get("health", {})
    health_config = HealthConfig(
        enabled=health_data.get("enabled", True),
        interval_minutes=health_data.get("interval_minutes", 5),
    )

    return Config(
        strategy=strategy,
        bot=bot,
        engine=engine,
        cache=cache,
        logging=logging_config,
        health=health_config,
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


def get_logging_config() -> LoggingConfig:
    """Get logging configuration."""
    return get_config().logging


def get_provider_config() -> ProviderConfig:
    """Get the current provider's configuration (includes costs)."""
    return get_config().engine.get_provider_config()


def get_indicator_config() -> IndicatorConfig:
    """Get indicator configuration."""
    return get_config().strategy.indicators


def get_health_config() -> HealthConfig:
    """Get health check configuration."""
    return get_config().health


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

# Roadmap: Version 1.0 Production Release

Production hardening plan to make the trading bot ready for real-money trading.

**Current State**: 70% production-ready (excellent foundations, needs hardening)
**Target**: Production-ready trading bot with resilience, observability, and recovery
**Timeline**: 7 weeks (6 weeks development + 1 week buffer)

---

## Timeline Overview

| Week | Phase | Key Deliverables |
|------|-------|------------------|
| 1 | Critical Infrastructure | Reconnection, exceptions, data validation |
| 2 | Critical Infrastructure (cont.) | Complete Phase 1 + buffer |
| 3 | Observability | Logging, alerts, health, monitoring |
| 4 | State Persistence | DuckDB state, reconciliation, recovery |
| 5 | Testing & Documentation | Integration tests, runbook, security, deployment |
| 6 | Beta Testing | 5+ trading days, failure simulation |
| 7 | Buffer | Final fixes, documentation polish, Go/No-Go |

---

## Phase 1: Critical Infrastructure (Weeks 1-2)

### 1.1 Automatic Reconnection

**Problem**: Feed/broker disconnections stop trading silently with no user visibility.

**Solution**: Implement exponential backoff reconnection with state preservation and real-time UI updates.

**Files to modify**:
- `src/tradingbot/_components/feeds/plugins/alpaca.py`
- `src/tradingbot/_components/brokers/plugins/alpaca.py`
- `src/tradingbot/_components/engine/engine.py`
- `src/tradingbot/_components/hub/hub.py` (connection status events)
- `src/tradingbot/_components/tui/widgets/status_bar.py` (visual indicator)
- `web/src/components/panels/StatusPanel.tsx` (visual indicator)

**Implementation**:
```python
from enum import Enum

class ConnectionState(Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"  # After max retries exhausted

@dataclass
class ConnectionStatus:
    feed: ConnectionState
    broker: ConnectionState
    last_change: datetime
    retry_count: int = 0
    next_retry_at: datetime | None = None

@dataclass
class ReconnectionConfig:
    max_retries: int = 5
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0

async def reconnect_with_backoff(
    connect_fn: Callable[[], Awaitable[None]],
    config: ReconnectionConfig,
    on_state_change: Callable[[ConnectionState, int], None] | None = None,
) -> None:
    """Reconnect with exponential backoff, broadcasting state changes."""
    delay = config.base_delay
    for attempt in range(config.max_retries):
        if on_state_change:
            on_state_change(ConnectionState.RECONNECTING, attempt + 1)
        try:
            await connect_fn()
            if on_state_change:
                on_state_change(ConnectionState.CONNECTED, 0)
            return
        except Exception as e:
            if attempt == config.max_retries - 1:
                if on_state_change:
                    on_state_change(ConnectionState.FAILED, attempt + 1)
                raise
            await asyncio.sleep(delay)
            delay = min(delay * config.backoff_factor, config.max_delay)
```

**Hub event broadcasting**:
```python
# New event type for connection status
@dataclass
class ConnectionStatusEvent:
    component: Literal["feed", "broker"]
    state: ConnectionState
    retry_count: int
    message: str

# Hub broadcasts to all subscribers (TUI, Web)
hub.broadcast("connection_status", ConnectionStatusEvent(...))
```

**TUI Status Bar** (`status_bar.py`):
```python
# Visual states:
# - Green dot: Connected
# - Yellow blinking dot: Reconnecting (with retry count)
# - Red dot: Disconnected/Failed

def get_connection_indicator(state: ConnectionState, retry: int) -> Text:
    match state:
        case ConnectionState.CONNECTED:
            return Text("●", style="green")
        case ConnectionState.RECONNECTING:
            # Blink effect via timer
            style = "yellow bold blink"
            return Text(f"● Retry {retry}", style=style)
        case ConnectionState.DISCONNECTED | ConnectionState.FAILED:
            return Text("●", style="red")
```

**Web UI Status Panel** (`StatusPanel.tsx`):
```tsx
// Visual states with CSS animations
const ConnectionIndicator = ({ state, retryCount }: Props) => {
  const getStatusClass = () => {
    switch (state) {
      case 'connected': return 'bg-green-500';
      case 'reconnecting': return 'bg-yellow-500 animate-pulse';
      case 'disconnected':
      case 'failed': return 'bg-red-500';
    }
  };

  return (
    <div className="flex items-center gap-2">
      <div className={`w-3 h-3 rounded-full ${getStatusClass()}`} />
      <span>
        {state === 'reconnecting'
          ? `Reconnecting (attempt ${retryCount})...`
          : state}
      </span>
    </div>
  );
};
```

**Acceptance criteria**:
- [ ] Feed reconnects automatically after network blip
- [ ] Broker reconnects and reconciles position state
- [ ] Engine continues processing after reconnection
- [ ] Alerts sent on repeated failures
- [ ] TUI status bar shows connection state with blinking indicator during reconnection
- [ ] Web UI shows connection state with animated indicator during reconnection
- [ ] Retry count visible to user during reconnection attempts
- [ ] Hub broadcasts connection status changes to all subscribers

---

### 1.2 Exception Hierarchy

**Problem**: Broad `except Exception` hides critical errors, making debugging hard.

**Solution**: Create typed exception hierarchy with retry decorators.

**New file**: `src/tradingbot/_components/exceptions.py`

**Implementation**:
```python
class TradingBotError(Exception):
    """Base exception for all trading bot errors."""

class ConfigurationError(TradingBotError):
    """Invalid configuration."""

class DataError(TradingBotError):
    """Data-related errors (feeds, cache)."""

class FeedError(DataError):
    """Feed connection/data errors."""

class BrokerError(TradingBotError):
    """Broker-related errors."""

class OrderError(BrokerError):
    """Order submission/execution errors."""

class InsufficientFundsError(OrderError):
    """Not enough buying power."""

class RiskLimitError(TradingBotError):
    """Risk limit exceeded."""

class RetryableError(TradingBotError):
    """Errors that can be retried."""

class FatalError(TradingBotError):
    """Errors requiring immediate shutdown."""
```

**Retry decorator**:
```python
def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    exceptions: tuple[type[Exception], ...] = (RetryableError,),
) -> Callable[[F], F]:
    """Retry decorator with exponential backoff."""
    ...
```

**Files to update**:
- Replace broad `except Exception` with specific exceptions
- Add retry decorator to network operations
- Log exceptions with full context

**Acceptance criteria**:
- [ ] All exceptions inherit from TradingBotError
- [ ] No bare `except Exception` in critical paths
- [ ] Retry decorator used for network operations
- [ ] Clear error messages with context

---

### 1.3 Data Validation Layer

**Problem**: Bad data from feeds (spikes, gaps, nulls) could trigger erroneous trades. This is safety-critical and must be implemented early.

**Solution**: Validate all incoming data before processing.

**New file**: `src/tradingbot/_components/validation.py`

**Implementation**:
```python
@dataclass
class ValidationConfig:
    max_price_change_pct: float = 10.0  # Max 10% change between bars
    max_spread_pct: float = 5.0  # Max 5% spread
    min_volume: int = 100  # Minimum volume
    reject_zero_prices: bool = True
    reject_future_timestamps: bool = True

class DataValidator:
    def __init__(self, config: ValidationConfig) -> None:
        self.config = config
        self.last_prices: dict[str, float] = {}

    def validate_bar(self, bar: Bar) -> ValidationResult:
        """Validate a price bar."""
        errors: list[str] = []

        # Check for zero/negative prices
        if self.config.reject_zero_prices:
            if bar.close <= 0 or bar.high <= 0 or bar.low <= 0:
                errors.append("Zero or negative price")

        # Check OHLC consistency
        if not (bar.low <= bar.open <= bar.high and bar.low <= bar.close <= bar.high):
            errors.append("Invalid OHLC relationship")

        # Check for price spikes
        if bar.symbol in self.last_prices:
            last = self.last_prices[bar.symbol]
            change_pct = abs(bar.close - last) / last * 100
            if change_pct > self.config.max_price_change_pct:
                errors.append(f"Price spike: {change_pct:.1f}%")

        # Check timestamp
        if self.config.reject_future_timestamps and bar.timestamp > datetime.now():
            errors.append("Future timestamp")

        self.last_prices[bar.symbol] = bar.close

        return ValidationResult(valid=len(errors) == 0, errors=errors)
```

**Integration points**:
- Validate bars before signal generation
- Log and alert on validation failures
- Option to reject or flag invalid data

**Acceptance criteria**:
- [ ] All incoming bars validated
- [ ] Price spikes detected and logged
- [ ] Invalid data does not trigger trades
- [ ] Alerts sent for repeated validation failures

---

## Phase 2: Observability (Week 3)

### 2.1 Structured Logging

**Problem**: Only 3 modules use logging, no structured format for analysis.

**Solution**: Implement structlog with JSON output and correlation IDs.

**New file**: `src/tradingbot/_components/logging.py`

**Dependencies**: Add `structlog` to pyproject.toml

**Implementation**:
```python
import structlog
from contextvars import ContextVar

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")

def configure_logging(
    level: str = "INFO",
    json_output: bool = True,
    log_file: str | None = None,
) -> None:
    """Configure structured logging."""
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

def get_logger(name: str) -> structlog.BoundLogger:
    """Get a logger with module context."""
    return structlog.get_logger(name)
```

**Usage pattern**:
```python
from tradingbot._components.logging import get_logger

logger = get_logger(__name__)

logger.info("order_submitted", symbol=symbol, side=side, qty=qty, order_id=order_id)
logger.error("order_failed", symbol=symbol, error=str(e), exc_info=True)
```

**Files to update**:
- Add logging to all modules in `_components/`
- Add correlation ID to request flows
- Configure log rotation

**Configuration** (tradingbot.toml):
```toml
[tradingbot.logging]
level = "INFO"
format = "console"  # "console" for development, "json" for production
log_file = "logs/tradingbot.log"
rotation_days = 7
```

**Environment-aware defaults**:
- Development: `format = "console"` (human-readable, colorized)
- Production: `format = "json"` (structured, machine-parseable)

**Acceptance criteria**:
- [ ] All modules use structured logging
- [ ] Console format for development (readable)
- [ ] JSON format for production (parseable)
- [ ] Correlation IDs track request flows
- [ ] Log rotation configured (7 days retention)

---

### 2.2 Alerting System

**Problem**: No notifications for critical events - failures go unnoticed.

**Solution**: Implement multi-channel alerting (email, webhook, optional SMS).

**New file**: `src/tradingbot/_components/alerts.py`

**Implementation**:
```python
from enum import Enum
from dataclasses import dataclass
from abc import ABC, abstractmethod

class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

@dataclass
class Alert:
    severity: AlertSeverity
    title: str
    message: str
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

class AlertChannel(ABC):
    @abstractmethod
    async def send(self, alert: Alert) -> None: ...

class EmailChannel(AlertChannel):
    """Send alerts via SMTP."""
    ...

class WebhookChannel(AlertChannel):
    """Send alerts to webhook (Slack, Discord, etc.)."""
    ...

class AlertManager:
    """Central alert dispatcher."""

    def __init__(self, channels: list[AlertChannel]) -> None:
        self.channels = channels

    async def send(self, alert: Alert) -> None:
        await asyncio.gather(*[ch.send(alert) for ch in self.channels])
```

**Alert triggers**:
| Event | Severity | Message |
|-------|----------|---------|
| Circuit breaker triggered | CRITICAL | Trading paused due to {loss}% daily loss |
| Max daily loss reached | CRITICAL | Daily loss limit reached, stopping trading |
| Feed disconnected | WARNING | {feed} disconnected, attempting reconnect |
| Feed reconnected | INFO | {feed} reconnected successfully |
| Order rejected | WARNING | Order rejected: {reason} |
| Position opened | INFO | Opened {side} {qty} {symbol} @ {price} |
| Position closed | INFO | Closed {symbol} for {pnl} ({pnl_pct}%) |

**Configuration** (tradingbot.toml):
```toml
[tradingbot.alerts]
enabled = true

[tradingbot.alerts.email]
enabled = true
smtp_host = "smtp.gmail.com"
smtp_port = 587
from_address = "bot@example.com"
to_addresses = ["trader@example.com"]

[tradingbot.alerts.webhook]
enabled = true
url = "https://hooks.slack.com/services/..."
```

**Acceptance criteria**:
- [ ] Email alerts working
- [ ] Webhook alerts working (Slack/Discord compatible)
- [ ] All critical events trigger alerts
- [ ] Rate limiting to prevent alert spam

---

### 2.3 Health Checks

**Problem**: No way to monitor if the bot is running correctly.

**Solution**: HTTP health endpoint and heartbeat system.

**New file**: `src/tradingbot/_components/health.py`

**Implementation**:
```python
from aiohttp import web

@dataclass
class HealthStatus:
    status: Literal["healthy", "degraded", "unhealthy"]
    feed_connected: bool
    broker_connected: bool
    last_bar_time: datetime | None
    last_heartbeat: datetime
    open_positions: int
    daily_pnl: float

async def health_handler(request: web.Request) -> web.Response:
    """Health check endpoint."""
    status = get_health_status()
    return web.json_response(asdict(status))

def start_health_server(port: int = 8080) -> None:
    """Start health check HTTP server."""
    ...
```

**Acceptance criteria**:
- [ ] `/health` endpoint returns JSON status
- [ ] Heartbeat logged every 60 seconds
- [ ] Status reflects actual component health

---

## Phase 3: State Persistence (Week 4)

### 3.1 State Persistence & Recovery

**Problem**: Position state is only in memory - crashes lose state.

**Solution**: Persist state to database with startup reconciliation.

**New file**: `src/tradingbot/_components/state.py`

**Implementation**:
```python
import duckdb
from pathlib import Path

class StateManager:
    """Persistent state management."""

    def __init__(self, db_path: Path) -> None:
        self.conn = duckdb.connect(str(db_path))
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                symbol VARCHAR PRIMARY KEY,
                side VARCHAR,
                qty DOUBLE,
                entry_price DOUBLE,
                entry_time TIMESTAMP,
                stop_loss DOUBLE,
                take_profit DOUBLE,
                high_water DOUBLE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS session_state (
                key VARCHAR PRIMARY KEY,
                value VARCHAR,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def save_position(self, position: Position) -> None:
        """Persist position to database."""
        ...

    def load_positions(self) -> list[Position]:
        """Load positions from database."""
        ...

    def reconcile_with_broker(self, broker_positions: list[Position]) -> ReconciliationResult:
        """Reconcile local state with broker state."""
        ...
```

**Startup reconciliation flow**:
1. Load local state from database
2. Fetch positions from broker
3. Compare and reconcile differences
4. Log any discrepancies
5. Alert if manual intervention needed

**Acceptance criteria**:
- [ ] Positions persisted to DuckDB
- [ ] State survives restarts
- [ ] Startup reconciliation with broker
- [ ] Alerts on state mismatches

---

## Phase 4: Testing & Documentation (Week 5)

### 4.1 Integration Tests

**New tests to add**:

```
tests/
├── integration/
│   ├── test_live_engine.py      # Full engine lifecycle
│   ├── test_reconnection.py     # Network failure recovery
│   ├── test_error_handling.py   # Exception scenarios
│   ├── test_state_recovery.py   # Crash recovery
│   └── test_alerting.py         # Alert delivery
```

**Critical path tests**:
1. Feed → Signal → Order → Execution (happy path)
2. Position entry → Partial exit → Full exit
3. Stop loss trigger → Order submission → Position close
4. Take profit trigger → Order submission → Position close
5. Circuit breaker activation → Trading pause → Alert
6. Daily loss limit → Trading stop → Alert
7. EOD exit → Close all positions → Verify empty state

**Failure scenario tests**:
1. Feed disconnection → Reconnection → Resume trading
2. Broker disconnection → Reconnection → Position reconciliation
3. Invalid bar data → Validation failure → Skip bar → Alert
4. Order rejection → Log error → Alert → Continue trading
5. State mismatch → Reconciliation → Alert if manual needed
6. Crash mid-trade → Restart → Load state → Reconcile

**Concurrent operation tests**:
1. Multiple symbols trading simultaneously
2. Position exits while entry signals arrive
3. Risk limits reached while signals pending

**Acceptance criteria**:
- [ ] Feed disconnection and reconnection
- [ ] Broker disconnection during open position
- [ ] Invalid data handling
- [ ] Circuit breaker activation
- [ ] State recovery after restart
- [ ] Alert delivery verification
- [ ] Test coverage >80% for core trading components

---

### 4.2 Production Runbook

**New file**: `docs/RUNBOOK.md`

**Contents**:
1. **Startup checklist** - Pre-flight checks before starting
2. **Monitoring** - What to watch, expected values
3. **Common issues** - Symptoms, causes, solutions
4. **Emergency procedures** - How to stop trading immediately
5. **Recovery procedures** - How to recover from crashes
6. **Escalation** - When to intervene manually

---

### 4.3 Security Hardening

**Tasks**:
- [ ] Audit credential handling (no hardcoded secrets)
- [ ] Verify .env files are gitignored
- [ ] Add credential validation on startup
- [ ] Document secure configuration practices

---

### 4.4 Deployment & Disaster Recovery

**Deployment procedures**:
- [ ] Docker containerization (optional but recommended)
- [ ] Environment configuration (dev/staging/prod)
- [ ] Deployment scripts or documentation
- [ ] Rollback procedures

**Disaster recovery**:
- [ ] Database backup procedures (DuckDB state + cache)
- [ ] Position reconciliation after outage
- [ ] Emergency shutdown procedures
- [ ] Recovery from corrupted state

**Documentation**:
- [ ] Deployment guide (`docs/DEPLOYMENT.md`)
- [ ] Backup/restore procedures
- [ ] Environment setup guide

---

### 4.5 Non-Functional Requirements

**Performance targets**:
- [ ] Order execution latency <100ms (p95)
- [ ] Feed processing latency <50ms (p95)
- [ ] Memory usage <500MB for 10 symbols
- [ ] CPU usage <25% average during active trading

**Reliability targets**:
- [ ] 99.9% uptime during trading hours
- [ ] MTTR (Mean Time to Recovery) <60 seconds
- [ ] Maximum reconnection time <5 minutes

**Security audit**:
- [ ] No hardcoded credentials
- [ ] .env files in .gitignore
- [ ] API keys stored securely
- [ ] Access logs for live trading actions

---

## Phase 5: Beta Testing (Weeks 6-7)

### 5.1 Extended Paper Trading

**Duration**: 5 full trading days minimum

**Test scenarios**:
1. Normal operation - Let it run unattended
2. Network interruption - Disconnect/reconnect WiFi
3. Process restart - Kill and restart mid-session
4. High volatility - Trade during market open/close
5. Weekend handling - Verify behavior over weekend

**Success metrics**:
- [ ] No unhandled exceptions
- [ ] All alerts delivered correctly
- [ ] State recovered after restart
- [ ] No missed trades due to reconnection issues

---

### 5.2 Failure Simulation

**Tests to run**:
- Kill feed connection mid-trade
- Simulate broker rejection
- Inject invalid price data
- Trigger circuit breaker
- Force state mismatch

---

### 5.3 Performance Testing

**Tests to run**:
- [ ] Benchmark order execution latency (<100ms target)
- [ ] Memory leak testing (24+ hour continuous runs)
- [ ] CPU usage profiling during active trading
- [ ] Data feed latency monitoring

**Long-running tests**:
- [ ] 8-hour continuous paper trading
- [ ] 24-hour memory usage monitoring
- [ ] Weekend startup/shutdown cycles

**Success criteria**:
- [ ] No memory leaks detected over 24 hours
- [ ] Order latency consistently <100ms
- [ ] CPU usage <25% average
- [ ] No degradation over time

---

### 5.4 Week 7: Buffer & Final Polish

**Activities**:
- Fix any issues discovered in beta testing
- Documentation polish and review
- Final Go/No-Go decision
- Tag v1.0 release

---

## Configuration Changes

### New tradingbot.toml sections

```toml
[tradingbot.resilience]
reconnect_max_retries = 5
reconnect_base_delay = 1.0
reconnect_max_delay = 60.0

[tradingbot.logging]
level = "INFO"
format = "console"  # "console" for dev, "json" for production
log_file = "logs/tradingbot.log"
rotation_days = 7

[tradingbot.alerts]
enabled = true

[tradingbot.alerts.email]
enabled = false
smtp_host = ""
smtp_port = 587
from_address = ""
to_addresses = []

[tradingbot.alerts.webhook]
enabled = false
url = ""

[tradingbot.health]
enabled = true
port = 8080

[tradingbot.state]
persist = true
db_path = "data/state.duckdb"
reconcile_on_startup = true
```

---

## New Dependencies

Add to `pyproject.toml`:

```toml
dependencies = [
    # ... existing ...
    "structlog>=24.1.0",
    "aiosmtplib>=3.0.0",  # For email alerts
]
```

---

## Summary

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| 1. Critical Infrastructure | Weeks 1-2 | Reconnection, exceptions, data validation |
| 2. Observability | Week 3 | Logging, alerts, health checks, monitoring |
| 3. State Persistence | Week 4 | DuckDB state, reconciliation, recovery |
| 4. Testing & Docs | Week 5 | Integration tests, runbook, deployment, security |
| 5. Beta Testing | Weeks 6-7 | Paper trading, failure simulation, performance |

**Total effort**: 7 weeks to production-ready v1.0 (6 weeks development + 1 week buffer)

---

## Go/No-Go Checklist

Before v1.0 release, verify all items in each category:

### Code Quality
- [ ] All P0 items implemented and tested
- [ ] No `except Exception` in critical paths
- [ ] All modules have structured logging
- [ ] No critical bugs in issue tracker
- [ ] Security audit passed
- [ ] Type checking passes with no errors
- [ ] Test coverage >80% for core trading components

### Reliability
- [ ] 5+ days of successful paper trading
- [ ] Zero unhandled exceptions in production mode
- [ ] State recovery tested with 3+ crash scenarios
- [ ] Reconnection tested with 5+ network interruption scenarios
- [ ] All alerts working (email + webhook)

### Observability
- [ ] Logs capture all critical events
- [ ] Alerts trigger correctly for all critical events
- [ ] Health endpoint returns accurate status
- [ ] Connection status visible in TUI/Web UI

### Documentation
- [ ] Production runbook documented
- [ ] All configuration options documented in README
- [ ] Integration test scenarios documented
- [ ] Deployment guide completed
- [ ] Known issues documented

### Performance
- [ ] Order execution latency <100ms (p95)
- [ ] Memory usage <500MB for 10 symbols after 8 hours
- [ ] No memory leaks detected in 24-hour test
- [ ] CPU usage <25% average during active trading

### Deployment
- [ ] Deployment procedure documented
- [ ] Rollback procedure documented
- [ ] Backup/restore procedures tested
- [ ] Environment configuration tested (dev/prod)

---

## Post-1.0 Roadmap

Features deferred to later versions:

**v1.1** (1-2 months after 1.0):
- ML signal filter
- Strategy parameter cleanup
- Enhanced TUI

**v1.2** (3-4 months after 1.0):
- TA-Lib dynamic indicators
- Candlestick patterns
- Volume confirmation

**v2.0** (6+ months after 1.0):
- Multi-broker support
- Options trading
- Portfolio-level risk

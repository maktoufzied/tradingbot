# Roadmap: Version 1.0 Production Release

Production hardening plan to make the trading bot ready for real-money trading.

**Current State**: ~85% production-ready
**Target**: Production-ready trading bot with state persistence and recovery
**Timeline**: 3 weeks

---

## What's Already Done

| Component | Status | Location |
|-----------|--------|----------|
| Reconnection with exponential backoff | ✅ Done | `resilience.py` |
| Connection status UI (TUI/Web) | ✅ Done | `status_bar.py`, `StatusPanel.tsx` |
| Exception hierarchy (24 types) | ✅ Done | `exceptions.py` |
| Retry decorators | ✅ Done | `resilience.py` |
| Health checks | ✅ Done | `health.py` |
| Centralized logging | ✅ Done | `logging.py` |
| Sound alerts (trade events) | ✅ Done | `sounds.py` |

---

## Timeline Overview

| Week | Phase | Key Deliverables |
|------|-------|------------------|
| 1 | State Persistence | DuckDB state, reconciliation, critical sound alerts |
| 2 | Testing | Integration tests, failure scenarios |
| 3 | Beta Testing | 5+ trading days, failure simulation, docs |

---

## Phase 1: State Persistence (Week 1)

### 1.1 State Persistence & Recovery

**Problem**: Position state is only in memory - crashes lose state.

**Solution**: Persist state to DuckDB with startup reconciliation.

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
5. Play alert sound if manual intervention needed

**Acceptance criteria**:
- [ ] Positions persisted to DuckDB
- [ ] State survives restarts
- [ ] Startup reconciliation with broker
- [ ] Sound alert on state mismatches

---

### 1.2 Critical Event Sound Alerts

**Problem**: Need audible notification for critical events beyond trade sounds.

**Solution**: Add sound alerts for critical events (circuit breaker, disconnection, etc.)

**File to modify**: `src/tradingbot/_components/sounds.py`

**New sound types**:
```python
# Add to existing sounds
ALERT: Final = "alert"      # Circuit breaker, daily loss limit
WARNING: Final = "warning"  # Feed disconnected
```

**Events to add sounds**:
| Event | Sound | Location to Add |
|-------|-------|-----------------|
| Circuit breaker triggered | `ALERT` | `risk_manager.py` |
| Daily loss limit reached | `ALERT` | `risk_manager.py` |
| Feed disconnected | `WARNING` | `alpaca.py` feed |
| State mismatch on startup | `ALERT` | `state.py` |

**Acceptance criteria**:
- [ ] Alert sound plays on circuit breaker
- [ ] Alert sound plays on daily loss limit
- [ ] Warning sound plays on feed disconnect
- [ ] Alert sound plays on state mismatch

---

## Phase 2: Testing (Week 2)

### 2.1 Integration Tests

**New tests to add**:

```
tests/
├── integration/
│   ├── test_live_engine.py      # Full engine lifecycle
│   ├── test_reconnection.py     # Network failure recovery
│   ├── test_state_recovery.py   # Crash recovery
```

**Critical path tests**:
1. Feed → Signal → Order → Execution (happy path)
2. Position entry → Partial exit → Full exit
3. Stop loss trigger → Order submission → Position close
4. Take profit trigger → Order submission → Position close
5. Circuit breaker activation → Trading pause → Sound alert
6. EOD exit → Close all positions → Verify empty state

**Failure scenario tests**:
1. Feed disconnection → Reconnection → Resume trading
2. Broker disconnection → Reconnection → Position reconciliation
3. Crash mid-trade → Restart → Load state → Reconcile

**Acceptance criteria**:
- [ ] Feed disconnection and reconnection tested
- [ ] Broker disconnection during open position tested
- [ ] Circuit breaker activation tested
- [ ] State recovery after restart tested
- [ ] Test coverage >80% for core trading components

---

### 2.2 Security Hardening

**Tasks**:
- [ ] Audit credential handling (no hardcoded secrets)
- [ ] Verify .env files are gitignored
- [ ] Add credential validation on startup

---

## Phase 3: Beta Testing & Documentation (Week 3)

### 3.1 Extended Paper Trading

**Duration**: 5 full trading days minimum

**Test scenarios**:
1. Normal operation - Let it run unattended
2. Network interruption - Disconnect/reconnect WiFi
3. Process restart - Kill and restart mid-session
4. High volatility - Trade during market open/close

**Success metrics**:
- [ ] No unhandled exceptions
- [ ] Sound alerts play correctly
- [ ] State recovered after restart
- [ ] No missed trades due to reconnection issues

---

### 3.2 Failure Simulation

**Tests to run**:
- Kill feed connection mid-trade
- Simulate broker rejection
- Trigger circuit breaker
- Force state mismatch (edit DuckDB manually)

---

### 3.3 Production Runbook

**New file**: `docs/RUNBOOK.md`

**Contents**:
1. **Startup checklist** - Pre-flight checks before starting
2. **Monitoring** - What to watch, expected values
3. **Common issues** - Symptoms, causes, solutions
4. **Emergency procedures** - How to stop trading immediately
5. **Recovery procedures** - How to recover from crashes

---

## Configuration Changes

### New tradingbot.toml section

```toml
[tradingbot.state]
persist = true
db_path = "data/state.duckdb"
reconcile_on_startup = true
```

---

## Go/No-Go Checklist

Before v1.0 release, verify all items:

### Core Functionality
- [ ] State persistence working (positions saved to DuckDB)
- [ ] State reconciliation on startup tested
- [ ] Sound alerts working for critical events
- [ ] Type checking passes with no errors
- [ ] All tests passing

### Reliability
- [ ] 5+ days of successful paper trading
- [ ] Zero unhandled exceptions
- [ ] State recovery tested with 3+ crash scenarios
- [ ] Reconnection tested with network interruptions

### Documentation
- [ ] Production runbook documented (`docs/RUNBOOK.md`)
- [ ] Configuration options documented in README

---

## Post-1.0 Roadmap

Features deferred to later versions:

**v1.1** (1-2 months after 1.0):
- Telegram alerts
- Email/webhook alerts
- Structured logging (structlog with JSON)
- ML signal filter

**v1.2** (3-4 months after 1.0):
- TA-Lib dynamic indicators
- Candlestick patterns
- Data validation layer (if needed based on real-world experience)

**v2.0** (6+ months after 1.0):
- Multi-broker support
- Options trading
- Portfolio-level risk

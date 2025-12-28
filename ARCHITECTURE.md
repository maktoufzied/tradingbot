# Architecture

Technical documentation of the trading bot's architecture, components, and design patterns.

## Directory Structure

```
src/tradingbot/
├── __init__.py              # Public API exports
├── config.py                # Configuration management (TOML)
├── types.py                 # Core data models
├── interfaces.py            # Protocol definitions
│
├── backtest_cli.py          # tradingbot-backtest CLI
├── optimize_cli.py          # tradingbot-optimize CLI
├── cli.py                   # tradingbot-live CLI
├── cache_cli.py             # tradingbot-cache CLI
│
└── _components/             # Internal modules
    ├── bot.py               # MarketStructureBot (backtesting)
    ├── runner.py            # Backtest orchestration
    ├── optimizer.py         # Parameter optimization
    ├── execution.py         # ExecutionModel (slippage, spread, commission)
    ├── signals.py           # SignalGenerator
    ├── swing.py             # Swing point detection
    ├── risk.py              # PositionSizer
    ├── live_risk.py         # LiveRiskManager
    ├── presets.py           # Strategy presets
    │
    ├── engine/              # Real-time trading engine
    ├── feeds/               # Data feed plugins
    ├── brokers/             # Broker plugins
    ├── strategies/          # Entry/exit strategies
    ├── indicators/          # Technical indicators
    ├── cache/               # DuckDB data cache
    ├── hub/                 # Event hub + WebSocket
    └── tui/                 # Terminal UI
```

## Core Types

Defined in `types.py`:

| Type | Description |
|------|-------------|
| `Bar` | OHLCV data point with datetime |
| `Position` | Active trade state (entry, size, SL/TP) |
| `Trade` | Closed trade record with P&L (gross, net, costs) |
| `Signal` | BUY / SELL / HOLD decision |
| `ExecutionModel` | Slippage, spread, commission modeling |
| `SwingPoint` | Local high/low for structure analysis |
| `Order` | Broker order request |
| `Trend` | BULLISH / BEARISH / NEUTRAL |

## Plugin Architecture

The system uses a **registry pattern** for extensibility:

```mermaid
flowchart LR
    subgraph Registration
        P[Protocol<br/>interfaces.py] --> R[Registry<br/>singleton]
        PL[Plugins<br/>plugins/*.py] --> R
    end

    subgraph Usage
        R --> |get| C[Component]
        C --> |uses| I[Instance]
    end
```

### Registries

| Registry | Plugins | Default |
|----------|---------|---------|
| **BrokerRegistry** | `paper`, `alpaca` | `paper` |
| **FeedRegistry** | `yahoo`, `alpaca`, `replay` | `yahoo` |
| **EntryRegistry** | 9 strategies | `swing_break` |
| **ExitRegistry** | `swing`, `atr`, `fixed` | `swing` |
| **IndicatorRegistry** | 11 indicators | `rsi`, `macd` |

### Adding a Plugin

```python
# src/tradingbot/_components/strategies/entry/my_strategy.py
from ..interfaces import Entry
from ..registry import register_entry

class MyStrategy:
    @property
    def name(self) -> str:
        return "my_strategy"

    def compute(self, df): ...
    def signal(self, df, idx, has_position): ...

register_entry(MyStrategy())
```

Then import in `registry.py` bootstrap function.

## Data Flow

### Backtesting Flow

```mermaid
flowchart TB
    CLI[backtest_cli.py] --> Runner[runner.py<br/>run_single_backtest]
    Runner --> Bot[MarketStructureBot]

    Bot --> Feed[DataFeed]
    Feed --> Cache[(DuckDB Cache)]
    Cache -.-> Yahoo[Yahoo Finance]

    Bot --> SG[SignalGenerator]
    Bot --> PS[PositionSizer]

    subgraph SignalGenerator
        SG --> Entry[Entry Strategy]
        SG --> Exit[Exit Strategy]
        SG --> Ind[Indicators]
    end

    Bot --> Trades[Trade Records]
    Trades --> Results[Performance Metrics]
```

### Live Trading Flow

```mermaid
flowchart TB
    CLI[cli.py] --> Engine[TradingEngine]

    subgraph Engine[TradingEngine]
        Feed[DataFeed<br/>real-time] --> |Bar| Process[Process Bar]
        Process --> SG[SignalGenerator]
        SG --> |Signal| Risk[LiveRiskManager]
        Risk --> |Validated| PS[PositionSizer]
        PS --> |Size| Broker[Broker]
        Broker --> |Order| Market((Market))
    end

    Engine --> |Events| CB[Callbacks]

    subgraph Callbacks
        CB --> Console[Console Output]
        CB --> TUI[Terminal UI]
        CB --> Hub[EventHub]
    end

    Hub --> |WebSocket| Web[Web Clients]
```

## Signal Generation

The `SignalGenerator` coordinates entry strategies, exit strategies, and indicator filters:

```mermaid
flowchart TB
    subgraph Input
        DF[DataFrame<br/>OHLCV + indicators]
        IDX[Current Index]
        POS[Has Position?]
    end

    DF --> SG[SignalGenerator]
    IDX --> SG
    POS --> SG

    subgraph SignalGenerator
        SG --> |1| Entry[EntryStrategy.signal]
        Entry --> |BUY/SELL/HOLD| Raw[Raw Signal]

        Raw --> |2| Filter{Indicator<br/>Filters}
        Filter --> |pass| Valid[Valid Signal]
        Filter --> |block| Hold[HOLD]

        Valid --> |3| Exit[ExitStrategy.calc]
        Exit --> SL[Stop Loss]
        Exit --> TP[Take Profit]
    end

    subgraph Output
        Valid --> Signal[Signal]
        SL --> Levels[Exit Levels]
        TP --> Levels
    end
```

### Indicator Filter Logic

```mermaid
flowchart LR
    Signal[Raw Signal] --> Mode{Filter Mode}

    Mode --> |all| All[All indicators<br/>must pass]
    Mode --> |any| Any[At least one<br/>must pass]
    Mode --> |none| None[No filtering]

    All --> Check{Check Each}
    Any --> Check

    Check --> |RSI| RSI[filter_signal]
    Check --> |MACD| MACD[filter_signal]
    Check --> |...| Other[filter_signal]

    RSI --> Result{Result}
    MACD --> Result
    Other --> Result

    Result --> |pass| Allow[Allow Signal]
    Result --> |block| Block[Block → HOLD]
```

## Callback System

### Engine Callbacks

The `TradingEngine` emits events through `EngineCallbacks`:

```mermaid
flowchart TB
    subgraph TradingEngine
        Bar[New Bar] --> |emit| E1[on_bar]
        Signal[Signal Generated] --> |emit| E2[on_signal]
        Trade[Trade Closed] --> |emit| E3[on_trade]
        Stats[Stats Updated] --> |emit| E4[on_stats]
        Msg[Message] --> |emit| E5[on_message]
    end

    subgraph EngineCallbacks
        E1 --> CB[Callback Handler]
        E2 --> CB
        E3 --> CB
        E4 --> CB
        E5 --> CB
    end

    CB --> |BarEvent| H1[Handle Bar]
    CB --> |SignalEvent| H2[Handle Signal]
    CB --> |TradeClosedEvent| H3[Handle Trade]
    CB --> |StatsUpdatedEvent| H4[Handle Stats]
    CB --> |MessageEvent| H5[Handle Message]
```

### Event Types

```mermaid
classDiagram
    class BarEvent {
        +str symbol
        +Bar bar
        +float equity
    }

    class SignalEvent {
        +str symbol
        +Signal signal
        +str reason
        +dict details
    }

    class TradeClosedEvent {
        +Trade trade
    }

    class StatsUpdatedEvent {
        +SessionStats stats
    }

    class MessageEvent {
        +str message
        +MessageLevel level
    }

    class AccountEvent {
        +float equity
        +float cash
        +float buying_power
    }

    class RiskEvent {
        +bool circuit_breaker
        +bool max_loss_hit
        +float daily_pnl
    }
```

### EventHub Architecture

The `EventHub` provides centralized state management and broadcasting:

```mermaid
flowchart TB
    subgraph Sources
        Engine[TradingEngine] --> Adapter[EngineAdapter]
    end

    Adapter --> Hub[EventHub]

    subgraph Hub[EventHub]
        direction TB
        State[(State Storage)]
        Dispatch[Dispatcher]

        State --> |tickers| T[Price Updates]
        State --> |positions| P[Open Trades]
        State --> |stats| S[Session Stats]
        State --> |account| A[Account Info]
        State --> |risk| R[Risk Status]
    end

    Hub --> |broadcast| Channels

    subgraph Channels
        CH1[TICKER]
        CH2[POSITION]
        CH3[TRADE]
        CH4[STATS]
        CH5[ACCOUNT]
        CH6[RISK]
    end

    Channels --> Subscribers

    subgraph Subscribers
        TUI[TUI Widgets]
        WS[WebSocket Clients]
        Log[Logger]
    end
```

### WebSocket Message Flow

```mermaid
sequenceDiagram
    participant E as TradingEngine
    participant A as EngineAdapter
    participant H as EventHub
    participant S as HubServer
    participant C as WebSocket Client

    E->>A: BarEvent
    A->>H: TickerUpdate
    H->>H: Update state
    H->>S: Broadcast
    S->>C: JSON message

    Note over C: Client connects
    C->>S: Connect
    S->>H: Get snapshot
    H->>S: Full state
    S->>C: Snapshot message
```

## Component Details

### TradingEngine

Event-driven engine for real-time trading:

```python
class TradingEngine:
    def __init__(
        symbols: list[str],
        broker: BrokerProtocol,
        feed: DataFeedProtocol,
        signal_generator: SignalGenerator,
        position_sizer: PositionSizer,
        live_risk_manager: LiveRiskManager,
        rr_ratio: float,
        allow_short: bool,
        dry_run: bool,
        callbacks: EngineCallbacks,
    )
```

### Engine Event Loop

```mermaid
stateDiagram-v2
    [*] --> Idle: start()

    Idle --> Processing: Bar received

    state Processing {
        [*] --> UpdateHistory
        UpdateHistory --> CheckPosition

        CheckPosition --> EvaluateExit: has position
        CheckPosition --> EvaluateEntry: no position

        EvaluateExit --> ClosePosition: SL/TP hit
        EvaluateExit --> HoldPosition: not hit

        EvaluateEntry --> GenerateSignal
        GenerateSignal --> ValidateRisk: BUY/SELL
        GenerateSignal --> Skip: HOLD

        ValidateRisk --> CalculateSize: approved
        ValidateRisk --> Skip: rejected

        CalculateSize --> SubmitOrder
        SubmitOrder --> [*]
        ClosePosition --> [*]
        HoldPosition --> [*]
        Skip --> [*]
    }

    Processing --> EmitCallbacks
    EmitCallbacks --> Idle

    Idle --> [*]: stop()
```

### Cache System

DuckDB-based historical data cache with aggregation and retention management:

```mermaid
flowchart TB
    Request[DataFeed.history<br/>symbol, interval, period] --> Cache[CachedFeed]

    Cache --> Check{Cache Hit?}

    Check --> |full hit| Return[Return DataFrame]
    Check --> |partial| Fetch[Fetch Missing]
    Check --> |miss| FetchAll[Fetch All]

    Fetch --> Yahoo[Yahoo Finance API]
    FetchAll --> Yahoo

    Yahoo --> Merge[Merge Data]
    Merge --> Store[(DuckDB)]
    Store --> Return
```

### Cache Maintenance

```mermaid
flowchart LR
    subgraph Maintenance[run_maintenance]
        Agg[Aggregate 1m bars] --> Purge[Purge old data]
    end

    subgraph Aggregation
        1m[1m bars] --> 5m[5m]
        1m --> 15m[15m]
        1m --> 1h[1h]
        1m --> 1d[1d]
    end

    subgraph Retention[Purge by Policy]
        P1[1m: 7 days]
        P2[5m: 30 days]
        P3[15m: 90 days]
        P4[1h: 365 days]
        P5[1d: forever]
    end
```

### Cache Functions

| Function | Description |
|----------|-------------|
| `insert_bars()` | Insert/upsert bars into DuckDB |
| `query_bars()` | Query bars by symbol, interval, date range |
| `aggregate_bars()` | Aggregate from source to target interval |
| `aggregate_all_intervals()` | Aggregate 1m → 5m/15m/1h/1d |
| `purge_old_bars()` | Delete bars older than retention policy |
| `run_maintenance()` | Full maintenance: aggregate + purge |

### Execution Cost Model

The `ExecutionModel` provides realistic trade execution cost simulation:

```mermaid
flowchart LR
    subgraph Entry
        SP[Signal Price] --> Spread[+ Spread/2]
        Spread --> Slip[+ Slippage]
        Slip --> EP[Entry Price]
    end

    subgraph Exit
        XP[Signal Price] --> XSpread[- Spread/2]
        XSpread --> XSlip[- Slippage]
        XSlip --> Exit[Exit Price]
    end

    subgraph Costs
        EP --> Comm[+ Commission]
        Exit --> Comm
        Comm --> Total[Total Costs]
    end
```

**Cost Components:**

| Component | Default | Description |
|-----------|---------|-------------|
| Slippage | 5 bps | Price movement between signal and fill |
| Spread | 2 bps | Bid-ask spread (pay ask, sell bid) |
| Commission | $0.005/share | Per-share brokerage fee |

**P&L Calculation:**

```python
# LONG trade example
entry_price = signal_price * (1 + spread_bps/20000 + slippage_bps/10000)
exit_price = signal_price * (1 - spread_bps/20000 - slippage_bps/10000)
gross_pnl = (exit_signal - entry_signal) * shares
commission = shares * commission_per_share * 2  # round-trip
net_pnl = (exit_price - entry_price) * shares - commission
```

**Factory Methods:**

| Method | Use Case |
|--------|----------|
| `ExecutionModel()` | Default costs (5bps slip, 2bps spread, $0.005 comm) |
| `ExecutionModel.zero()` | No costs (for comparison/benchmarking) |
| `ExecutionModel.conservative()` | Higher costs (10bps slip, 5bps spread) |

**CLI Flags:**

```bash
tradingbot-backtest AAPL --no-costs           # Disable all costs
tradingbot-backtest AAPL --slippage 10        # Custom slippage (bps)
tradingbot-backtest AAPL --spread 5           # Custom spread (bps)
tradingbot-backtest AAPL --commission 0.01    # Custom commission ($/share)
```

**Retention Policy:**
| Interval | Default Retention |
|----------|-------------------|
| 1m | 7 days |
| 5m | 30 days |
| 15m | 90 days |
| 1h | 365 days |
| 1d | Forever |

## Configuration

Hierarchy (later overrides earlier):

```mermaid
flowchart TB
    D[Defaults<br/>config.py] --> T[tradingbot.toml]
    T --> P[Presets<br/>--preset flag]
    P --> C[CLI Arguments]
    C --> Final[Final Config]
```

### Config Sections

```toml
[tradingbot.strategy]      # Entry/exit, risk params
[tradingbot.bot]           # Capital
[tradingbot.engine]        # Broker, feed, bar interval
[tradingbot.engine.risk]   # Live risk controls
[tradingbot.cache]         # Cache settings
```

## Protocols (Interfaces)

Defined in `interfaces.py`:

### BrokerProtocol

```python
class BrokerProtocol(Protocol):
    async def connect(self) -> None
    async def disconnect(self) -> None
    async def submit_order(self, order: Order) -> OrderResult
    async def cancel_order(self, order_id: str) -> bool
    async def get_position(self, symbol: str) -> Position | None
    async def get_account(self) -> AccountInfo
```

### DataFeedProtocol

```python
class DataFeedProtocol(Protocol):
    async def connect(self) -> None
    async def disconnect(self) -> None
    async def subscribe(self, symbols: list[str]) -> None
    def on_bar(self, callback: Callable[[Bar], None]) -> None
    def history(self, symbol, interval, period) -> pl.DataFrame
```

### EntryStrategy

```python
class EntryStrategy(Protocol):
    @property
    def name(self) -> str: ...
    def compute(self, df: pl.DataFrame) -> pl.DataFrame: ...
    def signal(self, df, idx, has_position) -> Entry: ...
```

### ExitStrategy

```python
class ExitStrategy(Protocol):
    @property
    def name(self) -> str: ...
    def calc(self, direction, entry, df, swings, rr_ratio) -> Exit: ...
```

### IndicatorProtocol

```python
class IndicatorProtocol(Protocol):
    @property
    def name(self) -> str: ...
    def compute(self, df: pl.DataFrame) -> pl.DataFrame: ...
    def get_signal(self, df, idx) -> Signal | None: ...
    def filter_signal(self, signal, df, idx) -> bool: ...
```

## Design Patterns

| Pattern | Usage |
|---------|-------|
| **Registry** | Plugin discovery and access |
| **Singleton** | Registry instances |
| **Strategy** | Entry/exit/indicator algorithms |
| **Adapter** | EngineAdapter (engine → hub) |
| **Observer** | Callbacks, hub subscriptions |
| **Protocol** | Interface definitions |
| **Dataclass** | Immutable config objects |

## Entry Points

| Command | Module | Description |
|---------|--------|-------------|
| `tradingbot-backtest` | `backtest_cli.py` | Run backtests |
| `tradingbot-optimize` | `optimize_cli.py` | Parameter optimization |
| `tradingbot-live` | `cli.py` | Live/paper trading |
| `tradingbot-cache` | `cache_cli.py` | Cache management |

## Testing

```bash
task test          # Run all tests
task check         # Lint + typecheck + test
```

Test organization:
```
tests/
├── test_bot.py           # Backtest logic
├── test_signals.py       # Signal generation
├── test_swing.py         # Swing detection
├── test_indicators.py    # Indicator calculations
├── test_risk.py          # Position sizing, risk
├── test_execution.py     # Execution cost modeling
├── test_alpaca_broker.py # Broker integration
├── test_alpaca_feed.py   # Feed integration
└── test_models.py        # Data models
```

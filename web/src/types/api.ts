// Types matching the Python hub/types.py definitions

export type Trend = 'BULLISH' | 'BEARISH' | 'NEUTRAL';
export type Signal = 'BUY' | 'SELL' | 'HOLD';
export type Direction = 'LONG' | 'SHORT';
export type TradeType = 'ENTRY' | 'EXIT' | 'BLOCKED';
export type UIChannel = 'ticker' | 'position' | 'trade' | 'stats' | 'account' | 'risk' | 'status' | 'chart';

// Connection state (mirrors Python resilience.ConnectionState)
export type ConnectionState = 'connected' | 'disconnected' | 'reconnecting' | 'failed';

export interface TickerUpdate {
  symbol: string;
  price: number;
  change: number;
  change_pct: number;
  high: number;
  low: number;
  volume: number;
  timestamp: string;
  trend: Trend;
  signal: Signal;
}

export interface PositionUpdate {
  symbol: string;
  direction: Direction | null;
  entry_price: number;
  current_price: number;
  size: number;
  stop_loss: number;
  take_profit: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  holding_minutes: number;
  risk_amount: number;
  is_open: boolean;
}

export interface TradeAlert {
  type: TradeType;
  symbol: string;
  direction: Direction;
  price: number;
  size: number;
  stop_loss: number | null;
  take_profit: number | null;
  pnl: number | null;
  pnl_pct: number | null;
  reason: string | null;
  strategy: string | null;
  timestamp: string;
  is_winner: boolean | null;
}

export interface SessionStats {
  total_pnl: number;
  total_pnl_pct: number;
  trade_count: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  profit_factor: number;
  largest_win: number;
  largest_loss: number;
  current_streak: number;
  equity_curve: number[];
}

export interface AccountSnapshot {
  equity: number;
  cash: number;
  buying_power: number;
  realized_pnl: number;
  unrealized_pnl: number;
  positions_value: number;
}

export interface RiskStatus {
  daily_loss_pct: number;
  max_daily_loss_pct: number;
  open_positions: number;
  max_positions: number;
  circuit_breaker_active: boolean;
  can_trade: boolean;
  blocked_reason: string | null;
}

export interface SystemStatus {
  feed_connected: boolean;
  broker_connected: boolean;
  market_open: boolean;
  market_next_change: string | null;
  uptime_seconds: number;
  bars_received: number;
  errors_count: number;
  is_replay: boolean;
  replay_time: string | null;
  // Provider name (e.g., "Alpaca", "Paper")
  provider: string;
  // Connection state details (feed only - broker uses REST)
  feed_state: ConnectionState;
  feed_retry_count: number;
  feed_last_error: string | null;
  // Legacy broker fields (kept for compatibility)
  broker_state: ConnectionState;
  broker_retry_count: number;
  broker_last_error: string | null;
}

export interface ChartUpdate {
  symbol: string;
  timestamps: string[];
  opens: number[];
  highs: number[];
  lows: number[];
  closes: number[];
  swing_highs: number[];
  swing_lows: number[];
}

export interface SymbolStrategyConfig {
  preset_name: string;
  entry_strategy: string;
  exit_strategy: string;
  risk_pct: number;
  rr_ratio: number;
  indicators: string[];
  filter_mode: string;
  eod_exit: boolean;
  partial_exits: string;
}

export interface StrategyInfo {
  preset_name: string;
  entry_strategy: string;
  exit_strategy: string;
  risk_pct: number;
  rr_ratio: number;
  indicators: string[];
  symbol_strategies: Record<string, string>;
  symbol_configs: Record<string, SymbolStrategyConfig>;
}

export interface GlobalState {
  tickers: Record<string, TickerUpdate>;
  positions: Record<string, PositionUpdate>;
  stats: SessionStats;
  account: AccountSnapshot;
  risk: RiskStatus;
  status: SystemStatus;
  charts: Record<string, ChartUpdate>;
  recent_trades: TradeAlert[];
  strategy: StrategyInfo;
}

// WebSocket message types
export interface SnapshotMessage {
  type: 'snapshot';
  data: GlobalState;
}

export interface ChannelMessage {
  channel: UIChannel;
  data: unknown;
}

export type WebSocketMessage = SnapshotMessage | ChannelMessage;

import { create } from 'zustand';
import { useShallow } from 'zustand/shallow';
import type {
  TickerUpdate,
  PositionUpdate,
  TradeAlert,
  SessionStats,
  AccountSnapshot,
  RiskStatus,
  SystemStatus,
  ChartUpdate,
  StrategyInfo,
  GlobalState,
  LogEntry,
} from '../types/api';

interface TradingState {
  // Connection state
  connected: boolean;
  reconnecting: boolean;
  reconnectAttempts: number;

  // Data state
  tickers: Record<string, TickerUpdate>;
  positions: Record<string, PositionUpdate>;
  stats: SessionStats;
  account: AccountSnapshot;
  risk: RiskStatus;
  status: SystemStatus;
  charts: Record<string, ChartUpdate>;
  recentTrades: TradeAlert[];
  strategy: StrategyInfo;
  logs: LogEntry[];

  // Actions
  setConnected: (connected: boolean) => void;
  setReconnecting: (reconnecting: boolean, attempts?: number) => void;
  setSnapshot: (data: GlobalState) => void;
  updateTicker: (data: TickerUpdate) => void;
  updatePosition: (data: PositionUpdate) => void;
  updateStats: (data: SessionStats) => void;
  updateAccount: (data: AccountSnapshot) => void;
  updateRisk: (data: RiskStatus) => void;
  updateStatus: (data: SystemStatus) => void;
  updateChart: (data: ChartUpdate) => void;
  addTrade: (data: TradeAlert) => void;
  addLog: (data: LogEntry) => void;
  clearState: () => void;
}

const emptyStats: SessionStats = {
  total_pnl: 0,
  total_pnl_pct: 0,
  trade_count: 0,
  win_count: 0,
  loss_count: 0,
  win_rate: 0,
  profit_factor: 0,
  largest_win: 0,
  largest_loss: 0,
  current_streak: 0,
  equity_curve: [],
};

const emptyAccount: AccountSnapshot = {
  equity: 0,
  cash: 0,
  buying_power: 0,
  realized_pnl: 0,
  unrealized_pnl: 0,
  positions_value: 0,
};

const defaultRisk: RiskStatus = {
  daily_loss_pct: 0,
  max_daily_loss_pct: 5,
  open_positions: 0,
  max_positions: 5,
  circuit_breaker_active: false,
  can_trade: true,
  blocked_reason: null,
};

const defaultStatus: SystemStatus = {
  feed_connected: false,
  broker_connected: false,
  market_open: false,
  market_next_change: null,
  uptime_seconds: 0,
  bars_received: 0,
  errors_count: 0,
  is_replay: false,
  replay_time: null,
};

const defaultStrategy: StrategyInfo = {
  preset_name: 'custom',
  entry_strategy: 'swing_break',
  exit_strategy: 'swing',
  risk_pct: 0.01,
  rr_ratio: 1.5,
  indicators: [],
};

export const useTradingStore = create<TradingState>((set) => ({
  // Initial state
  connected: false,
  reconnecting: false,
  reconnectAttempts: 0,
  tickers: {},
  positions: {},
  stats: emptyStats,
  account: emptyAccount,
  risk: defaultRisk,
  status: defaultStatus,
  charts: {},
  recentTrades: [],
  strategy: defaultStrategy,
  logs: [],

  // Actions
  setConnected: (connected) => set({ connected, reconnecting: false, reconnectAttempts: 0 }),

  setReconnecting: (reconnecting, attempts = 0) =>
    set({ reconnecting, reconnectAttempts: attempts }),

  setSnapshot: (data) =>
    set({
      tickers: data.tickers,
      positions: data.positions,
      stats: data.stats,
      account: data.account,
      risk: data.risk,
      status: data.status,
      charts: data.charts,
      recentTrades: data.recent_trades,
      strategy: data.strategy,
    }),

  updateTicker: (data) =>
    set((state) => ({
      tickers: { ...state.tickers, [data.symbol]: data },
    })),

  updatePosition: (data) =>
    set((state) => ({
      positions: { ...state.positions, [data.symbol]: data },
    })),

  updateStats: (data) => set({ stats: data }),

  updateAccount: (data) => set({ account: data }),

  updateRisk: (data) => set({ risk: data }),

  updateStatus: (data) => set({ status: data }),

  updateChart: (data) =>
    set((state) => ({
      charts: { ...state.charts, [data.symbol]: data },
    })),

  addTrade: (data) =>
    set((state) => ({
      recentTrades: [data, ...state.recentTrades].slice(0, 50),
    })),

  addLog: (data) =>
    set((state) => ({
      logs: [...state.logs, data].slice(-100),
    })),

  clearState: () =>
    set({
      tickers: {},
      positions: {},
      stats: emptyStats,
      account: emptyAccount,
      risk: defaultRisk,
      status: defaultStatus,
      charts: {},
      recentTrades: [],
      strategy: defaultStrategy,
      logs: [],
    }),
}));

// Selector hooks for optimized re-renders
export const useConnectionStatus = () => useTradingStore((s) => s.connected);
export const useReconnecting = () => useTradingStore(
  useShallow((s) => ({ reconnecting: s.reconnecting, attempts: s.reconnectAttempts }))
);
export const useTicker = (symbol: string) => useTradingStore((s) => s.tickers[symbol]);
export const usePosition = (symbol: string) => useTradingStore((s) => s.positions[symbol]);
export const useStats = () => useTradingStore((s) => s.stats);
export const useAccount = () => useTradingStore((s) => s.account);
export const useRisk = () => useTradingStore((s) => s.risk);
export const useStatus = () => useTradingStore((s) => s.status);
export const useChart = (symbol: string) => useTradingStore((s) => s.charts[symbol]);
export const useRecentTrades = () => useTradingStore((s) => s.recentTrades);
export const useStrategy = () => useTradingStore((s) => s.strategy);
export const useLogs = () => useTradingStore((s) => s.logs);
export const useSymbols = () => useTradingStore(useShallow((s) => Object.keys(s.tickers)));
export const useAllTickers = () => useTradingStore((s) => s.tickers);
export const useAllPositions = () => useTradingStore((s) => s.positions);

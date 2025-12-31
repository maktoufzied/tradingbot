import { useEffect, useRef, useCallback } from 'react';
import { useTradingStore } from '../store/tradingStore';
import type {
  WebSocketMessage,
  TickerUpdate,
  PositionUpdate,
  TradeAlert,
  SessionStats,
  AccountSnapshot,
  RiskStatus,
  SystemStatus,
  ChartUpdate,
} from '../types/api';

interface UseWebSocketOptions {
  url: string;
  autoConnect?: boolean;
}

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000, 30000];
const PING_INTERVAL = 30000;

// Helper to get store actions without subscribing
const getActions = () => useTradingStore.getState();

export function useWebSocket({ url, autoConnect = true }: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const pingIntervalRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef(0);

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const message: WebSocketMessage = JSON.parse(event.data);
      const actions = getActions();

      // Handle pong response
      if ('pong' in message) {
        return;
      }

      // Handle snapshot
      if ('type' in message && message.type === 'snapshot') {
        actions.setSnapshot(message.data);
        return;
      }

      // Handle channel updates
      if ('channel' in message) {
        switch (message.channel) {
          case 'ticker':
            actions.updateTicker(message.data as TickerUpdate);
            break;
          case 'position':
            actions.updatePosition(message.data as PositionUpdate);
            break;
          case 'trade':
            actions.addTrade(message.data as TradeAlert);
            break;
          case 'stats':
            actions.updateStats(message.data as SessionStats);
            break;
          case 'account':
            actions.updateAccount(message.data as AccountSnapshot);
            break;
          case 'risk':
            actions.updateRisk(message.data as RiskStatus);
            break;
          case 'status':
            actions.updateStatus(message.data as SystemStatus);
            break;
          case 'chart':
            actions.updateChart(message.data as ChartUpdate);
            break;
        }
      }
    } catch (error) {
      console.error('Failed to parse WebSocket message:', error);
    }
  }, []);

  const startPingInterval = useCallback(() => {
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
    }
    pingIntervalRef.current = window.setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ ping: true }));
      }
    }, PING_INTERVAL);
  }, []);

  const stopPingInterval = useCallback(() => {
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    // Clean up existing connection
    if (wsRef.current) {
      wsRef.current.close();
    }

    try {
      const ws = new WebSocket(url);

      ws.onopen = () => {
        console.log('WebSocket connected');
        getActions().setConnected(true);
        reconnectAttemptsRef.current = 0;
        startPingInterval();
      };

      ws.onmessage = handleMessage;

      ws.onclose = (event) => {
        console.log('WebSocket disconnected:', event.code, event.reason);
        getActions().setConnected(false);
        stopPingInterval();

        // Auto-reconnect
        if (!event.wasClean) {
          const delay = RECONNECT_DELAYS[Math.min(reconnectAttemptsRef.current, RECONNECT_DELAYS.length - 1)];
          reconnectAttemptsRef.current += 1;
          getActions().setReconnecting(true, reconnectAttemptsRef.current);

          console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current})`);
          reconnectTimeoutRef.current = window.setTimeout(() => {
            connect();
          }, delay);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      wsRef.current = ws;
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
    }
  }, [url, handleMessage, startPingInterval, stopPingInterval]);

  const disconnect = useCallback(() => {
    // Clear reconnect timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Stop ping interval
    stopPingInterval();

    // Close WebSocket
    if (wsRef.current) {
      wsRef.current.close(1000, 'Manual disconnect');
      wsRef.current = null;
    }

    const actions = getActions();
    actions.setConnected(false);
    actions.setReconnecting(false, 0);
    actions.clearState();
  }, [stopPingInterval]);

  const refresh = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ refresh: true }));
    }
  }, []);

  // Auto-connect on mount (intentionally omitting connect/disconnect from deps to avoid infinite loop)
  useEffect(() => {
    if (autoConnect) {
      connect();
    }

    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoConnect]);

  return {
    connect,
    disconnect,
    refresh,
    isConnected: wsRef.current?.readyState === WebSocket.OPEN,
  };
}

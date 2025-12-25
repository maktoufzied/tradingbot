import { useRecentTrades } from '../../store/tradingStore';
import { TradeLogEntry } from './TradeLogEntry';

export function TradeLog() {
  const trades = useRecentTrades();

  return (
    <div className="bg-surface border-t border-border">
      <div className="flex items-center justify-between px-4 py-2 border-b border-border">
        <h3 className="text-sm font-semibold text-primary">SIGNALS & TRADES</h3>
        <span className="text-xs text-text-dim">{trades.length} entries</span>
      </div>

      <div className="h-40 overflow-y-auto">
        {trades.length === 0 ? (
          <div className="flex items-center justify-center h-full text-text-dim text-sm">
            No trades yet
          </div>
        ) : (
          trades.map((trade, i) => <TradeLogEntry key={`${trade.timestamp}-${i}`} trade={trade} />)
        )}
      </div>
    </div>
  );
}

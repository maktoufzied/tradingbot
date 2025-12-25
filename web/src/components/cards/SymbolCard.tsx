import { useTicker, usePosition, useChart } from '../../store/tradingStore';
import { PriceDisplay } from '../widgets/PriceDisplay';
import { TrendBadge } from '../widgets/TrendBadge';
import { SignalBadge } from '../widgets/SignalBadge';
import { PriceChart } from '../charts/PriceChart';
import clsx from 'clsx';

interface SymbolCardProps {
  symbol: string;
}

export function SymbolCard({ symbol }: SymbolCardProps) {
  const ticker = useTicker(symbol);
  const position = usePosition(symbol);
  const chartData = useChart(symbol);

  if (!ticker) {
    return (
      <div className="bg-surface rounded-lg border border-border p-4 flex items-center justify-center">
        <span className="text-text-dim">Waiting for {symbol}...</span>
      </div>
    );
  }

  return (
    <div className="bg-surface rounded-lg border border-border overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border">
        <div className="flex items-center gap-3">
          <span className="text-lg font-bold text-primary">{symbol}</span>
          <TrendBadge trend={ticker.trend} />
          <SignalBadge signal={ticker.signal} />
        </div>
        {position?.is_open && (
          <span
            className={clsx(
              'px-2 py-0.5 text-xs font-bold rounded',
              position.direction === 'LONG' ? 'bg-positive/20 text-positive' : 'bg-negative/20 text-negative'
            )}
          >
            {position.direction === 'LONG' ? '▲' : '▼'} {position.direction}
          </span>
        )}
      </div>

      {/* Price */}
      <div className="px-4 py-2">
        <PriceDisplay
          price={ticker.price}
          change={ticker.change}
          changePct={ticker.change_pct}
          size="md"
        />
      </div>

      {/* Chart */}
      <div className="px-2">
        <PriceChart chartData={chartData} position={position} height={120} />
      </div>

      {/* Session Stats */}
      <div className="flex justify-between px-4 py-2 text-xs text-text-secondary border-t border-border">
        <span>H: ${ticker.high.toFixed(2)}</span>
        <span>L: ${ticker.low.toFixed(2)}</span>
        <span>Vol: {(ticker.volume / 1000000).toFixed(1)}M</span>
      </div>

      {/* Position Details */}
      {position?.is_open && (
        <div className="px-4 py-3 bg-surface-dark border-t border-border">
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div>
              <span className="text-text-dim block">Entry</span>
              <span className="mono">${position.entry_price.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-text-dim block">SL</span>
              <span className="mono text-negative">${position.stop_loss.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-text-dim block">TP</span>
              <span className="mono text-positive">${position.take_profit.toFixed(2)}</span>
            </div>
          </div>
          <div className="flex justify-between items-center mt-2 pt-2 border-t border-border">
            <div className="text-xs">
              <span className="text-text-dim">Size:</span>{' '}
              <span className="mono">{position.size.toFixed(2)} sh</span>
            </div>
            <div className="text-xs">
              <span className="text-text-dim">Time:</span>{' '}
              <span className="mono">{position.holding_minutes}m</span>
            </div>
            <div
              className={clsx(
                'mono font-semibold',
                position.unrealized_pnl >= 0 ? 'text-positive' : 'text-negative'
              )}
            >
              {position.unrealized_pnl >= 0 ? '+' : ''}${position.unrealized_pnl.toFixed(2)}
              <span className="text-xs ml-1">
                ({position.unrealized_pnl >= 0 ? '+' : ''}{position.unrealized_pnl_pct.toFixed(2)}%)
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

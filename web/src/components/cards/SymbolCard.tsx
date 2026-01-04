import { useState } from 'react';
import { useTicker, usePosition, useChart, useSymbolStrategy } from '../../store/tradingStore';
import { PriceDisplay } from '../widgets/PriceDisplay';
import { TrendBadge } from '../widgets/TrendBadge';
import { SignalBadge } from '../widgets/SignalBadge';
import { Sparkline } from '../charts/Sparkline';
import { SymbolDetailModal } from '../modals/SymbolDetailModal';
import clsx from 'clsx';

interface SymbolCardProps {
  symbol: string;
}

export function SymbolCard({ symbol }: SymbolCardProps) {
  const [showModal, setShowModal] = useState(false);
  const ticker = useTicker(symbol);
  const position = usePosition(symbol);
  const chartData = useChart(symbol);
  const strategyName = useSymbolStrategy(symbol);

  if (!ticker) {
    return (
      <div className="bg-surface rounded-lg border border-border p-4 flex items-center justify-center h-[240px]">
        <span className="text-text-dim">Waiting for {symbol}...</span>
      </div>
    );
  }

  const hasPosition = position?.is_open;

  // Get sparkline data from chart closes
  const sparklineData = chartData?.closes?.filter((c) => c != null) ?? [];
  const sparklineColor = ticker.change >= 0 ? '#00ff88' : '#ff3366';

  return (
    <>
      <div
        className="bg-surface rounded-lg border border-border overflow-hidden cursor-pointer hover:border-primary/50 transition-colors flex flex-col"
        onClick={() => setShowModal(true)}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-border shrink-0 gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-lg font-bold text-primary shrink-0">{symbol}</span>
            {strategyName && (
              <span className="text-xs text-text-dim px-1.5 py-0.5 bg-surface-dark rounded truncate max-w-[80px]">
                {strategyName}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <TrendBadge trend={ticker.trend} />
            <SignalBadge signal={ticker.signal} />
            {hasPosition && position && (
              <span
                className={clsx(
                  'px-2 py-0.5 text-xs font-bold rounded whitespace-nowrap',
                  position.direction === 'LONG' ? 'bg-positive/20 text-positive' : 'bg-negative/20 text-negative'
                )}
              >
                {position.direction === 'LONG' ? '▲' : '▼'} {position.direction}
              </span>
            )}
            <svg className="w-4 h-4 text-text-dim shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
            </svg>
          </div>
        </div>

        {/* Price + Entry */}
        <div className="px-4 py-3 shrink-0">
          <div className="flex items-baseline justify-between">
            <PriceDisplay
              price={ticker.price}
              change={ticker.change}
              changePct={ticker.change_pct}
              size="md"
            />
            {hasPosition && position && (
              <div className="text-right">
                <span className="text-xs text-text-dim">Entry</span>
                <span className="text-sm font-mono text-primary ml-1">${position.entry_price.toFixed(2)}</span>
              </div>
            )}
          </div>
        </div>

        {/* Sparkline (full width) */}
        <div className="relative flex-1 min-h-[70px]">
          <Sparkline
            data={sparklineData}
            height={70}
            color={sparklineColor}
            entryPrice={hasPosition && position ? position.entry_price : undefined}
          />
        </div>

        {/* Stats */}
        <div className="flex justify-between px-4 py-2 text-xs text-text-secondary border-t border-border shrink-0">
          <span>H: ${ticker.high.toFixed(2)}</span>
          <span>L: ${ticker.low.toFixed(2)}</span>
          <span>Vol: {(ticker.volume / 1000000).toFixed(1)}M</span>
        </div>

        {/* Position (if open) */}
        {hasPosition && position && (
          <div className="px-4 py-2 bg-surface-dark border-t border-border shrink-0">
            <div className="flex justify-between items-center text-xs">
              <div className="flex gap-4">
                <span>
                  <span className="text-text-secondary">SL</span>{' '}
                  <span className="font-mono text-negative">${position.stop_loss.toFixed(2)}</span>
                </span>
                <span>
                  <span className="text-text-secondary">TP</span>{' '}
                  <span className="font-mono text-positive">${position.take_profit.toFixed(2)}</span>
                </span>
                <span className="whitespace-nowrap">
                  <span className="text-text-secondary">Size</span>{' '}
                  <span className="font-mono text-text">
                    {position.size}×${(position.size * position.entry_price / 1000).toFixed(1)}K
                  </span>
                </span>
              </div>
              <span
                className={clsx(
                  'font-mono font-semibold',
                  position.unrealized_pnl >= 0 ? 'text-positive' : 'text-negative'
                )}
              >
                {position.unrealized_pnl >= 0 ? '+' : ''}${position.unrealized_pnl.toFixed(2)}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Modal */}
      {showModal && (
        <SymbolDetailModal symbol={symbol} onClose={() => setShowModal(false)} />
      )}
    </>
  );
}

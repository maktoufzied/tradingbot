import { useState, useEffect, useCallback } from 'react';
import { useTicker, usePosition, useChart, useSymbolStrategy, useSymbolConfig } from '../../store/tradingStore';
import { PriceChart } from '../charts/PriceChart';
import { SymbolHistory } from './SymbolHistory';
import { TrendBadge } from '../widgets/TrendBadge';
import { SignalBadge } from '../widgets/SignalBadge';
import { theme } from '../../styles/theme';
import clsx from 'clsx';

interface SymbolDetailModalProps {
  symbol: string;
  onClose: () => void;
}

type TabId = 'chart' | 'history';

export function SymbolDetailModal({ symbol, onClose }: SymbolDetailModalProps) {
  const [activeTab, setActiveTab] = useState<TabId>('chart');
  const ticker = useTicker(symbol);
  const position = usePosition(symbol);
  const chartData = useChart(symbol);
  const strategyName = useSymbolStrategy(symbol);
  const symbolConfig = useSymbolConfig(symbol);

  // Close on Escape key
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
  }, [onClose]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [handleKeyDown]);

  if (!ticker) return null;

  const hasPosition = position?.is_open;

  // Calculate Risk Ladder positions
  const getRiskLadderData = () => {
    if (!hasPosition || !position) return null;
    const range = position.take_profit - position.stop_loss;
    if (range <= 0) return null;

    const pricePosition = ((ticker.price - position.stop_loss) / range) * 100;
    const entryPosition = ((position.entry_price - position.stop_loss) / range) * 100;
    const rValue = Math.abs(position.entry_price - position.stop_loss);

    // Parse partial exits
    const partialExits: { percent: number; rMultiple: number; position: number }[] = [];
    if (symbolConfig.partial_exits) {
      const exits = symbolConfig.partial_exits.split(',');
      for (const exit of exits) {
        const match = exit.trim().match(/(\d+)%@(\d+)R/);
        if (match) {
          const percent = parseInt(match[1]);
          const rMultiple = parseInt(match[2]);
          const price = position.entry_price + rValue * rMultiple;
          const pos = ((price - position.stop_loss) / range) * 100;
          partialExits.push({ percent, rMultiple, position: pos });
        }
      }
    }

    return { pricePosition, entryPosition, partialExits };
  };

  const riskLadder = getRiskLadderData();

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(4px)' }}
      onClick={onClose}
    >
      <div
        className="bg-surface rounded-xl border border-border w-full max-w-5xl h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
          <div className="flex items-center gap-4">
            <h2 className="text-2xl font-bold text-primary">{symbol}</h2>
            <span className="px-2 py-1 text-xs rounded bg-neutral/20 text-neutral">
              {strategyName || symbolConfig.preset_name}
            </span>
            <TrendBadge trend={ticker.trend} />
            <SignalBadge signal={ticker.signal} />
            {hasPosition && position && (
              <span
                className={clsx(
                  'px-2 py-1 text-xs font-bold rounded',
                  position.direction === 'LONG' ? 'bg-positive/20 text-positive' : 'bg-negative/20 text-negative'
                )}
              >
                {position.direction === 'LONG' ? '▲' : '▼'} {position.direction}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-surface-light rounded-lg transition text-text-dim hover:text-text"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-6 border-b border-border shrink-0">
          <button
            className={clsx(
              'px-4 py-3 text-sm font-medium transition relative',
              activeTab === 'chart' ? 'text-primary' : 'text-text-dim hover:text-text'
            )}
            onClick={() => setActiveTab('chart')}
          >
            Chart
            {activeTab === 'chart' && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
            )}
          </button>
          <button
            className={clsx(
              'px-4 py-3 text-sm font-medium transition relative',
              activeTab === 'history' ? 'text-primary' : 'text-text-dim hover:text-text'
            )}
            onClick={() => setActiveTab('history')}
          >
            History
            {activeTab === 'history' && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
            )}
          </button>
        </div>

        {/* Tab Content */}
        <div className="flex-1 min-h-0 overflow-hidden p-6">
          {activeTab === 'chart' ? (
            <div className="h-full flex flex-col">
              {/* Price Header */}
              <div className="shrink-0 mb-4">
                <div className="flex justify-between items-start">
                  <div className="flex items-baseline gap-3">
                    <span className="text-4xl font-bold text-text font-mono">${ticker.price.toFixed(2)}</span>
                    <span className={clsx('text-lg', ticker.change >= 0 ? 'text-positive' : 'text-negative')}>
                      {ticker.change >= 0 ? '+' : ''}${ticker.change.toFixed(2)} ({ticker.change >= 0 ? '+' : ''}{ticker.change_pct.toFixed(2)}%)
                    </span>
                  </div>
                  <div className="flex items-start gap-4">
                    <div className="text-right text-sm text-text-secondary">
                      <div>H: <span className="font-mono">${ticker.high.toFixed(2)}</span></div>
                      <div>L: <span className="font-mono">${ticker.low.toFixed(2)}</span></div>
                      <div>Vol: <span className="font-mono">{(ticker.volume / 1000000).toFixed(1)}M</span></div>
                    </div>
                    {hasPosition && (
                      <button className="px-4 py-2 bg-negative/20 text-negative hover:bg-negative/30 rounded-lg transition font-medium text-sm">
                        Close Position
                      </button>
                    )}
                  </div>
                </div>

                {/* Risk Ladder */}
                {hasPosition && position && riskLadder && (
                  <div className="flex items-center gap-4 mt-4 pt-6 pb-3 px-3 bg-surface-dark rounded-lg border border-border">
                    <div className="flex items-center gap-3 flex-1">
                      <span className="text-xs font-mono text-negative font-medium whitespace-nowrap">
                        SL ${position.stop_loss.toFixed(2)}
                      </span>
                      <div className="flex-1 relative">
                        {/* Bar container */}
                        <div className="relative h-6 bg-surface rounded border-2 border-border overflow-hidden">
                          <div
                            className="absolute inset-0"
                            style={{
                              background: `linear-gradient(to right, ${theme.negative}4D, ${theme.neutral}33, ${theme.positive}4D)`,
                            }}
                          />
                          {/* Progress fill */}
                          <div
                            className="absolute inset-y-0 left-0"
                            style={{
                              width: `${Math.min(Math.max(riskLadder.pricePosition, 0), 100)}%`,
                              background: `linear-gradient(to right, ${theme.negative}80, ${theme.primary}4D, ${theme.positive}80)`,
                            }}
                          />
                          {/* Entry marker */}
                          <div
                            className="absolute top-0 bottom-0 w-0.5 z-10"
                            style={{ left: `${riskLadder.entryPosition}%`, backgroundColor: theme.primary }}
                          />
                          {/* Partial exit markers */}
                          {riskLadder.partialExits.map((exit, i) => (
                            <div
                              key={i}
                              className="absolute top-0 bottom-0 w-0.5 z-10"
                              style={{ left: `${Math.min(exit.position, 99)}%`, backgroundColor: theme.neutral }}
                            />
                          ))}
                          {/* Current price dot */}
                          <div
                            className="absolute top-1/2 -translate-y-1/2 w-4 h-4 bg-text rounded-full border-2 border-surface-dark shadow-lg z-20"
                            style={{ left: `calc(${Math.min(Math.max(riskLadder.pricePosition, 0), 100)}% - 8px)` }}
                          />
                        </div>
                        {/* Labels */}
                        <div className="absolute -top-5 left-0 right-0 text-[10px] font-mono">
                          <div
                            className="absolute text-primary font-medium"
                            style={{ left: `${riskLadder.entryPosition}%`, transform: 'translateX(-50%)' }}
                          >
                            Entry
                          </div>
                          {riskLadder.partialExits.map((exit, i) => (
                            <div
                              key={i}
                              className="absolute text-neutral font-medium"
                              style={{ left: `${Math.min(exit.position, 99)}%`, transform: 'translateX(-50%)' }}
                            >
                              {exit.rMultiple}R
                            </div>
                          ))}
                        </div>
                      </div>
                      <span className="text-xs font-mono text-positive font-medium whitespace-nowrap">
                        TP ${position.take_profit.toFixed(2)}
                      </span>
                    </div>

                    <div className="w-px h-8 bg-border" />

                    {/* Stats Pills */}
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="px-2.5 py-1 bg-primary/20 text-primary rounded text-xs font-mono font-medium">
                        @${position.entry_price.toFixed(2)}
                      </span>
                      <span className="px-2.5 py-1 bg-surface border border-border rounded text-xs font-mono text-text">
                        {position.size}sh · ${(position.size * position.entry_price / 1000).toFixed(1)}K
                      </span>
                      <span className="px-2.5 py-1 bg-surface border border-border rounded text-xs font-mono text-text-secondary">
                        {position.holding_minutes}m
                      </span>
                      {symbolConfig.partial_exits && (
                        <span className="px-2.5 py-1 bg-neutral/20 text-neutral rounded text-xs font-mono font-medium">
                          {symbolConfig.partial_exits}
                        </span>
                      )}
                      <span
                        className={clsx(
                          'px-3 py-1 rounded text-sm font-mono font-bold',
                          position.unrealized_pnl >= 0 ? 'bg-positive/20 text-positive' : 'bg-negative/20 text-negative'
                        )}
                      >
                        {position.unrealized_pnl >= 0 ? '+' : ''}${position.unrealized_pnl.toFixed(2)}
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {/* Chart */}
              <div className="bg-surface-dark rounded-lg border border-border overflow-hidden flex-1 min-h-0">
                <PriceChart chartData={chartData} position={position} height={undefined} />
              </div>
            </div>
          ) : (
            <SymbolHistory symbol={symbol} />
          )}
        </div>
      </div>
    </div>
  );
}

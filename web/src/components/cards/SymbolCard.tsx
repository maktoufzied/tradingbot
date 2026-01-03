import { useState } from 'react';
import { useTicker, usePosition, useChart, useSymbolStrategy, useSymbolConfig } from '../../store/tradingStore';
import { PriceDisplay } from '../widgets/PriceDisplay';
import { TrendBadge } from '../widgets/TrendBadge';
import { SignalBadge } from '../widgets/SignalBadge';
import { PriceChart } from '../charts/PriceChart';
import clsx from 'clsx';

interface SymbolCardProps {
  symbol: string;
}

export function SymbolCard({ symbol }: SymbolCardProps) {
  const [showStrategy, setShowStrategy] = useState(false);
  const ticker = useTicker(symbol);
  const position = usePosition(symbol);
  const chartData = useChart(symbol);
  const strategyName = useSymbolStrategy(symbol);
  const symbolConfig = useSymbolConfig(symbol);

  if (!ticker) {
    return (
      <div className="bg-surface rounded-lg border border-border p-4 flex items-center justify-center">
        <span className="text-text-dim">Waiting for {symbol}...</span>
      </div>
    );
  }

  return (
    <div
      className="bg-surface rounded-lg border border-border overflow-hidden cursor-pointer h-[300px] flex flex-col"
      onClick={() => setShowStrategy(!showStrategy)}
    >
      {showStrategy ? (
        // Back - Strategy Details
        <>
          <div className="flex items-center justify-between px-4 py-2 border-b border-border">
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold text-primary">{symbol}</span>
              <span className="text-xs px-2 py-0.5 bg-accent/20 text-accent rounded-full font-medium">
                {strategyName || symbolConfig.preset_name}
              </span>
            </div>
            <span className="text-xs text-text-dim">tap to flip</span>
          </div>

          <div className="p-4 flex-1 flex flex-col justify-center">
            <div className="grid grid-cols-2 gap-x-6 gap-y-3">
              <div className="text-center">
                <div className="text-lg font-bold text-text">{symbolConfig.entry_strategy}</div>
                <div className="text-xs text-text-dim uppercase tracking-wider mt-1">Entry</div>
              </div>
              <div className="text-center">
                <div className="text-lg font-bold text-text">{symbolConfig.exit_strategy}</div>
                <div className="text-xs text-text-dim uppercase tracking-wider mt-1">Exit</div>
              </div>
              <div className="text-center">
                <div className="text-lg font-bold text-accent">{(symbolConfig.risk_pct * 100).toFixed(1)}%</div>
                <div className="text-xs text-text-dim uppercase tracking-wider mt-1">Risk</div>
              </div>
              <div className="text-center">
                <div className="text-lg font-bold text-accent">1:{symbolConfig.rr_ratio.toFixed(1)}</div>
                <div className="text-xs text-text-dim uppercase tracking-wider mt-1">R:R</div>
              </div>
            </div>

            {/* Indicators with filter mode */}
            {symbolConfig.indicators.length > 0 && (
              <div className="mt-3 pt-3 border-t border-border/30 text-center">
                <div className="flex justify-center gap-2 flex-wrap">
                  {symbolConfig.indicators.map((ind) => (
                    <span
                      key={ind}
                      className="px-2 py-0.5 bg-surface-dark rounded-full text-xs font-medium text-text-secondary"
                    >
                      {ind.toUpperCase()}
                    </span>
                  ))}
                  <span className="px-2 py-0.5 text-xs text-text-dim">
                    ({symbolConfig.filter_mode})
                  </span>
                </div>
              </div>
            )}

            {/* Badges: EOD/Swing and Partial Exits */}
            <div className="mt-3 pt-3 border-t border-border/30 flex justify-center gap-2 flex-wrap">
              <span
                className={clsx(
                  'px-2 py-0.5 rounded text-xs font-medium',
                  symbolConfig.eod_exit
                    ? 'bg-warning/20 text-warning'
                    : 'bg-positive/20 text-positive'
                )}
              >
                {symbolConfig.eod_exit ? 'EOD Exit' : 'Swing'}
              </span>
              {symbolConfig.partial_exits && (
                <span className="px-2 py-0.5 bg-accent/20 text-accent rounded text-xs font-medium">
                  Partial: {symbolConfig.partial_exits}
                </span>
              )}
            </div>
          </div>
        </>
      ) : (
        // Front - Price & Chart
        <>
          <div className="flex items-center justify-between px-4 py-2 border-b border-border shrink-0">
            <div className="flex items-center gap-3">
              <span className="text-lg font-bold text-primary">{symbol}</span>
              {strategyName && (
                <span className="text-xs text-text-dim px-1.5 py-0.5 bg-surface-dark rounded">
                  {strategyName}
                </span>
              )}
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

          <div className="px-4 py-2 shrink-0">
            <PriceDisplay
              price={ticker.price}
              change={ticker.change}
              changePct={ticker.change_pct}
              size="md"
            />
          </div>

          <div className="px-2 flex-1 min-h-0">
            <PriceChart chartData={chartData} position={position} height={120} />
          </div>

          <div className="flex justify-between px-4 py-2 text-xs text-text-secondary border-t border-border shrink-0">
            <span>H: ${ticker.high.toFixed(2)}</span>
            <span>L: ${ticker.low.toFixed(2)}</span>
            <span>Vol: {(ticker.volume / 1000000).toFixed(1)}M</span>
          </div>

          {position?.is_open && (
            <div className="px-4 py-3 bg-surface-dark border-t border-border shrink-0">
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
        </>
      )}
    </div>
  );
}

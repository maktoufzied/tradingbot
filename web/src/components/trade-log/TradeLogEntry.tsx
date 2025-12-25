import { format } from 'date-fns';
import clsx from 'clsx';
import type { TradeAlert } from '../../types/api';

interface TradeLogEntryProps {
  trade: TradeAlert;
}

export function TradeLogEntry({ trade }: TradeLogEntryProps) {
  const isEntry = trade.type === 'ENTRY';
  const isExit = trade.type === 'EXIT';
  const isBlocked = trade.type === 'BLOCKED';
  const isWinner = trade.is_winner === true;

  return (
    <div
      className={clsx(
        'flex items-center gap-3 px-4 py-2 text-sm border-b border-border-dim',
        isBlocked && 'opacity-60'
      )}
    >
      {/* Time */}
      <span className="mono text-text-dim w-16 flex-shrink-0">
        {format(new Date(trade.timestamp), 'HH:mm')}
      </span>

      {/* Direction */}
      <span
        className={clsx(
          'w-4 flex-shrink-0',
          trade.direction === 'LONG' ? 'text-positive' : 'text-negative'
        )}
      >
        {trade.direction === 'LONG' ? '▲' : '▼'}
      </span>

      {/* Symbol */}
      <span className="font-semibold text-primary w-16 flex-shrink-0">{trade.symbol}</span>

      {/* Type */}
      <span
        className={clsx(
          'px-2 py-0.5 text-xs font-medium rounded w-16 text-center flex-shrink-0',
          isEntry && 'bg-neutral/20 text-neutral',
          isExit && 'bg-warning/20 text-warning',
          isBlocked && 'bg-negative/20 text-negative'
        )}
      >
        {trade.type}
      </span>

      {/* Price */}
      <span className="mono flex-shrink-0 w-20">${trade.price.toFixed(2)}</span>

      {/* Details */}
      <div className="flex-1 text-text-secondary">
        {isEntry && (
          <span className="text-xs">
            {trade.size.toFixed(0)}sh · SL ${trade.stop_loss?.toFixed(2)} · TP ${trade.take_profit?.toFixed(2)}
          </span>
        )}
        {isExit && (
          <span className={clsx('mono', isWinner ? 'text-positive' : 'text-negative')}>
            {trade.pnl !== null && (
              <>
                {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                {trade.pnl_pct !== null && ` (${trade.pnl_pct >= 0 ? '+' : ''}${trade.pnl_pct.toFixed(2)}%)`}
              </>
            )}
          </span>
        )}
        {isBlocked && <span className="text-xs text-negative">{trade.reason}</span>}
      </div>

      {/* Exit reason or winner badge */}
      {isExit && (
        <div className="flex items-center gap-2 flex-shrink-0">
          {trade.reason && <span className="text-xs text-text-dim">{trade.reason}</span>}
          <span
            className={clsx(
              'text-xs font-medium',
              isWinner ? 'text-positive' : 'text-negative'
            )}
          >
            {isWinner ? '✓ WIN' : '✗ LOSS'}
          </span>
        </div>
      )}
    </div>
  );
}

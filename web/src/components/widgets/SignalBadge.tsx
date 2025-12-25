import clsx from 'clsx';
import type { Signal } from '../../types/api';

interface SignalBadgeProps {
  signal: Signal;
}

export function SignalBadge({ signal }: SignalBadgeProps) {
  return (
    <span
      className={clsx(
        'px-2 py-0.5 text-xs font-medium rounded',
        signal === 'BUY' && 'bg-positive/30 text-positive border border-positive/50',
        signal === 'SELL' && 'bg-negative/30 text-negative border border-negative/50',
        signal === 'HOLD' && 'bg-text-muted/30 text-text-secondary border border-text-muted/50'
      )}
    >
      {signal === 'BUY' && '●'} {signal === 'SELL' && '○'} {signal}
    </span>
  );
}

import clsx from 'clsx';
import type { Trend } from '../../types/api';

interface TrendBadgeProps {
  trend: Trend;
}

export function TrendBadge({ trend }: TrendBadgeProps) {
  return (
    <span
      className={clsx(
        'px-2 py-0.5 text-xs font-medium rounded',
        trend === 'BULLISH' && 'bg-positive/20 text-positive',
        trend === 'BEARISH' && 'bg-negative/20 text-negative',
        trend === 'NEUTRAL' && 'bg-neutral/20 text-neutral'
      )}
    >
      {trend === 'BULLISH' && '↑'} {trend === 'BEARISH' && '↓'} {trend}
    </span>
  );
}

import { useStatus } from '../../store/tradingStore';
import clsx from 'clsx';
import type { ConnectionState } from '../../types/api';

interface ConnectionIndicatorProps {
  state: ConnectionState;
  retryCount: number;
  label: string;
}

function ConnectionIndicator({ state, retryCount, label }: ConnectionIndicatorProps) {
  const getIndicatorClass = () => {
    switch (state) {
      case 'connected':
        return 'bg-positive';
      case 'reconnecting':
        return 'bg-warning animate-pulse';
      case 'failed':
        return 'bg-negative';
      case 'disconnected':
      default:
        return 'bg-negative';
    }
  };

  const getStatusText = () => {
    switch (state) {
      case 'connected':
        return label;
      case 'reconnecting':
        return `${label} (retry ${retryCount})`;
      case 'failed':
        return `${label} FAILED`;
      case 'disconnected':
      default:
        return label;
    }
  };

  return (
    <div className="flex items-center gap-1.5">
      <span className={clsx('w-2 h-2 rounded-full', getIndicatorClass())} />
      <span className="text-sm text-text-secondary">{getStatusText()}</span>
    </div>
  );
}

export function ConnectionStatus() {
  const status = useStatus();

  return (
    <div className="flex items-center gap-4">
      <ConnectionIndicator
        state={status.feed_state}
        retryCount={status.feed_retry_count}
        label={status.provider || 'Alpaca'}
      />
    </div>
  );
}

import { useConnectionStatus, useReconnecting } from '../../store/tradingStore';
import clsx from 'clsx';

export function ConnectionStatus() {
  const connected = useConnectionStatus();
  const { reconnecting, attempts } = useReconnecting();

  return (
    <div className="flex items-center gap-2">
      <span
        className={clsx(
          'w-2 h-2 rounded-full',
          connected ? 'bg-positive' : reconnecting ? 'bg-warning animate-pulse' : 'bg-negative'
        )}
      />
      <span className="text-sm text-text-secondary">
        {connected ? 'Connected' : reconnecting ? `Reconnecting (${attempts})...` : 'Disconnected'}
      </span>
    </div>
  );
}

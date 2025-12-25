import { useStatus } from '../../store/tradingStore';
import { ConnectionStatus } from '../widgets/ConnectionStatus';
import { format } from 'date-fns';

export function Header() {
  const status = useStatus();

  const formatUptime = (seconds: number) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return `${h}h ${m}m ${s}s`;
  };

  const replayTime = status.replay_time ? new Date(status.replay_time) : null;

  return (
    <header className="flex items-center justify-between px-4 py-2 bg-surface border-b border-border">
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-bold text-primary">TRADINGBOT</h1>
        {status.is_replay && (
          <span className="px-2 py-0.5 text-xs font-medium bg-warning/20 text-warning rounded">
            REPLAY
          </span>
        )}
      </div>

      <div className="flex items-center gap-6">
        {/* Connection indicators */}
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${status.feed_connected ? 'bg-positive' : 'bg-negative'}`}
            />
            <span className="text-text-secondary">Feed</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${status.broker_connected ? 'bg-positive' : 'bg-negative'}`}
            />
            <span className="text-text-secondary">Broker</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${status.market_open ? 'bg-positive' : 'bg-warning'}`}
            />
            <span className="text-text-secondary">{status.market_open ? 'Market Open' : 'Market Closed'}</span>
          </div>
        </div>

        {/* Stats */}
        <div className="flex items-center gap-4 text-sm text-text-secondary">
          <span className="mono">{status.bars_received} bars</span>
          {status.errors_count > 0 && (
            <span className="text-negative">{status.errors_count} errors</span>
          )}
          <span className="mono">{formatUptime(status.uptime_seconds)}</span>
        </div>

        {/* Time */}
        <div className="text-lg font-medium mono text-primary">
          {replayTime ? format(replayTime, 'HH:mm:ss') : format(new Date(), 'HH:mm:ss')}
        </div>

        <ConnectionStatus />
      </div>
    </header>
  );
}

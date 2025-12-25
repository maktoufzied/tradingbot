import { useRisk } from '../../store/tradingStore';
import clsx from 'clsx';

export function RiskMeter() {
  const risk = useRisk();

  const lossRatio = Math.min(Math.abs(risk.daily_loss_pct) / risk.max_daily_loss_pct, 1);
  const progressWidth = `${lossRatio * 100}%`;

  const getProgressColor = () => {
    if (lossRatio < 0.3) return 'bg-positive';
    if (lossRatio < 0.6) return 'bg-warning';
    return 'bg-negative';
  };

  return (
    <div className="p-3 bg-surface rounded-lg border border-border">
      <h3 className="text-sm font-semibold text-primary mb-3">RISK</h3>

      <div className="space-y-3">
        {/* Daily Loss Progress Bar */}
        <div>
          <div className="flex justify-between text-xs mb-1">
            <span className="text-text-secondary">Daily Loss</span>
            <span className="mono text-text-secondary">
              {risk.daily_loss_pct.toFixed(2)}% / {risk.max_daily_loss_pct.toFixed(1)}%
            </span>
          </div>
          <div className="h-2 bg-surface-dark rounded-full overflow-hidden">
            <div
              className={clsx('h-full transition-all duration-300', getProgressColor())}
              style={{ width: progressWidth }}
            />
          </div>
        </div>

        {/* Position Count */}
        <div className="flex justify-between items-center">
          <span className="text-text-secondary text-sm">Positions</span>
          <span className="mono text-sm">
            {risk.open_positions} / {risk.max_positions}
          </span>
        </div>

        {/* Trading Status */}
        <div className="flex justify-between items-center">
          <span className="text-text-secondary text-sm">Status</span>
          <span
            className={clsx(
              'px-2 py-0.5 text-xs font-medium rounded',
              risk.can_trade
                ? 'bg-positive/20 text-positive'
                : 'bg-negative/20 text-negative'
            )}
          >
            {risk.can_trade ? '✓ Can Trade' : '✗ Blocked'}
          </span>
        </div>

        {/* Circuit Breaker */}
        {risk.circuit_breaker_active && (
          <div className="flex items-center gap-2 text-negative text-sm">
            <span className="animate-pulse">⚠</span>
            <span>Circuit Breaker Active</span>
          </div>
        )}

        {/* Blocked Reason */}
        {risk.blocked_reason && (
          <div className="text-xs text-negative bg-negative/10 p-2 rounded">
            {risk.blocked_reason}
          </div>
        )}
      </div>
    </div>
  );
}

import { useStats } from '../../store/tradingStore';
import clsx from 'clsx';

export function StatsPanel() {
  const stats = useStats();
  const isPositive = stats.total_pnl >= 0;

  return (
    <div className="p-3 bg-surface rounded-lg border border-border">
      <h3 className="text-sm font-semibold text-primary mb-3">SESSION</h3>

      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <span className="text-text-secondary text-sm">P&L</span>
          <span
            className={clsx(
              'mono font-semibold',
              isPositive ? 'text-positive' : 'text-negative'
            )}
          >
            {isPositive ? '+' : ''}${stats.total_pnl.toFixed(2)}
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-text-secondary text-sm">Return</span>
          <span
            className={clsx(
              'mono text-sm',
              isPositive ? 'text-positive' : 'text-negative'
            )}
          >
            {isPositive ? '+' : ''}
            {stats.total_pnl_pct.toFixed(2)}%
          </span>
        </div>

        <div className="h-px bg-border my-2" />

        <div className="flex justify-between items-center">
          <span className="text-text-secondary text-sm">Trades</span>
          <span className="mono text-sm">
            {stats.trade_count}{' '}
            <span className="text-text-dim">
              ({stats.win_count}W/{stats.loss_count}L)
            </span>
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-text-secondary text-sm">Win Rate</span>
          <span className="mono text-sm">{stats.win_rate.toFixed(1)}%</span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-text-secondary text-sm">Profit Factor</span>
          <span className="mono text-sm">{stats.profit_factor.toFixed(2)}</span>
        </div>

        <div className="h-px bg-border my-2" />

        <div className="flex justify-between items-center">
          <span className="text-text-secondary text-sm">Largest Win</span>
          <span className="mono text-sm text-positive">
            +${stats.largest_win.toFixed(2)}
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-text-secondary text-sm">Largest Loss</span>
          <span className="mono text-sm text-negative">
            ${stats.largest_loss.toFixed(2)}
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-text-secondary text-sm">Streak</span>
          <span
            className={clsx(
              'mono text-sm',
              stats.current_streak > 0 ? 'text-positive' : stats.current_streak < 0 ? 'text-negative' : 'text-text-secondary'
            )}
          >
            {stats.current_streak > 0 ? '+' : ''}
            {stats.current_streak}
          </span>
        </div>
      </div>
    </div>
  );
}

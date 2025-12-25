import { useAccount } from '../../store/tradingStore';
import clsx from 'clsx';

export function AccountPanel() {
  const account = useAccount();

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  return (
    <div className="p-3 bg-surface rounded-lg border border-border">
      <h3 className="text-sm font-semibold text-primary mb-3">ACCOUNT</h3>

      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <span className="text-text-secondary text-sm">Equity</span>
          <span className="mono font-semibold text-text">
            {formatCurrency(account.equity)}
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-text-secondary text-sm">Cash</span>
          <span className="mono text-sm text-text-secondary">
            {formatCurrency(account.cash)}
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-text-secondary text-sm">Buying Power</span>
          <span className="mono text-sm text-text-secondary">
            {formatCurrency(account.buying_power)}
          </span>
        </div>

        <div className="h-px bg-border my-2" />

        <div className="flex justify-between items-center">
          <span className="text-text-secondary text-sm">Realized</span>
          <span
            className={clsx(
              'mono text-sm',
              account.realized_pnl >= 0 ? 'text-positive' : 'text-negative'
            )}
          >
            {account.realized_pnl >= 0 ? '+' : ''}
            {formatCurrency(account.realized_pnl)}
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-text-secondary text-sm">Unrealized</span>
          <span
            className={clsx(
              'mono text-sm',
              account.unrealized_pnl >= 0 ? 'text-positive' : 'text-negative'
            )}
          >
            {account.unrealized_pnl >= 0 ? '+' : ''}
            {formatCurrency(account.unrealized_pnl)}
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-text-secondary text-sm">Positions</span>
          <span className="mono text-sm text-text-secondary">
            {formatCurrency(account.positions_value)}
          </span>
        </div>
      </div>
    </div>
  );
}

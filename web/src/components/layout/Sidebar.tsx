import { StatsPanel } from '../panels/StatsPanel';
import { AccountPanel } from '../panels/AccountPanel';
import { RiskMeter } from '../panels/RiskMeter';
import { useStrategy } from '../../store/tradingStore';

export function Sidebar() {
  const strategy = useStrategy();

  return (
    <aside className="w-72 bg-surface-dark border-l border-border p-3 flex flex-col gap-3 overflow-y-auto">
      <StatsPanel />
      <AccountPanel />
      <RiskMeter />

      {/* Strategy Info */}
      <div className="p-3 bg-surface rounded-lg border border-border">
        <h3 className="text-sm font-semibold text-primary mb-3">STRATEGY</h3>
        <div className="space-y-2 text-xs">
          <div className="flex justify-between">
            <span className="text-text-secondary">Preset</span>
            <span className="text-text font-medium">{strategy.preset_name}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">Entry</span>
            <span className="mono text-text-secondary">{strategy.entry_strategy}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">Exit</span>
            <span className="mono text-text-secondary">{strategy.exit_strategy}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">Risk</span>
            <span className="mono">{(strategy.risk_pct * 100).toFixed(1)}%</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">R:R</span>
            <span className="mono">{strategy.rr_ratio.toFixed(1)}:1</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

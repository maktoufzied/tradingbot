import { StatsPanel } from '../panels/StatsPanel';
import { AccountPanel } from '../panels/AccountPanel';
import { RiskMeter } from '../panels/RiskMeter';

export function Sidebar() {
  return (
    <aside className="w-72 bg-surface-dark border-l border-border p-3 flex flex-col gap-3 overflow-y-auto">
      <StatsPanel />
      <AccountPanel />
      <RiskMeter />
    </aside>
  );
}

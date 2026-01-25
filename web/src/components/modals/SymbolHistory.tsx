import { useMemo, useState } from 'react';
import { useSymbolTrades } from '../../store/tradingStore';
import type { TradeAlert } from '../../types/api';
import { theme } from '../../styles/theme';
import clsx from 'clsx';

interface SymbolHistoryProps {
  symbol: string;
}

type FilterType = 'all' | 'wins' | 'losses';

export function SymbolHistory({ symbol }: SymbolHistoryProps) {
  const trades = useSymbolTrades(symbol);
  const [filter, setFilter] = useState<FilterType>('all');

  // Calculate stats from trades
  const stats = useMemo(() => {
    const completed = trades.filter((t) => t.type === 'EXIT');
    const wins = completed.filter((t) => t.is_winner === true);
    const losses = completed.filter((t) => t.is_winner === false);

    const totalPnl = completed.reduce((sum, t) => sum + (t.pnl ?? 0), 0);
    const avgWin = wins.length > 0 ? wins.reduce((sum, t) => sum + (t.pnl ?? 0), 0) / wins.length : 0;
    const avgLoss = losses.length > 0 ? Math.abs(losses.reduce((sum, t) => sum + (t.pnl ?? 0), 0) / losses.length) : 0;
    const winRate = completed.length > 0 ? (wins.length / completed.length) * 100 : 0;

    // Build equity curve using reduce to avoid variable reassignment
    const equityCurve = completed
      .slice()
      .reverse()
      .reduce<number[]>((acc, t) => {
        const prev = acc.length > 0 ? acc[acc.length - 1] : 0;
        acc.push(prev + (t.pnl ?? 0));
        return acc;
      }, []);

    // Calculate time-based stats
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const weekStart = new Date(todayStart);
    weekStart.setDate(weekStart.getDate() - weekStart.getDay()); // Start of week (Sunday)
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);

    const filterByDate = (trades: typeof completed, since: Date) => {
      return trades.filter((t) => new Date(t.timestamp) >= since);
    };

    const dailyTrades = filterByDate(completed, todayStart);
    const weeklyTrades = filterByDate(completed, weekStart);
    const monthlyTrades = filterByDate(completed, monthStart);

    const calcPeriodStats = (periodTrades: typeof completed) => ({
      pnl: periodTrades.reduce((sum, t) => sum + (t.pnl ?? 0), 0),
      wins: periodTrades.filter((t) => t.is_winner === true).length,
      losses: periodTrades.filter((t) => t.is_winner === false).length,
    });

    return {
      totalPnl,
      totalTrades: completed.length,
      wins: wins.length,
      losses: losses.length,
      winRate,
      avgWin,
      avgLoss,
      avgR: avgLoss > 0 ? avgWin / avgLoss : 0,
      equityCurve,
      daily: calcPeriodStats(dailyTrades),
      weekly: calcPeriodStats(weeklyTrades),
      monthly: calcPeriodStats(monthlyTrades),
    };
  }, [trades]);

  // Filter trades for timeline
  const filteredTrades = useMemo(() => {
    const exitTrades = trades.filter((t) => t.type === 'EXIT');
    if (filter === 'wins') return exitTrades.filter((t) => t.is_winner === true);
    if (filter === 'losses') return exitTrades.filter((t) => t.is_winner === false);
    return exitTrades;
  }, [trades, filter]);

  // Generate equity curve SVG path
  const equityCurvePath = useMemo(() => {
    if (stats.equityCurve.length < 2) return { line: '', area: '' };

    const data = stats.equityCurve;
    const min = Math.min(0, ...data);
    const max = Math.max(...data, 0);
    const range = max - min || 1;
    const height = 120;
    const padding = 10;

    const points = data.map((val, i) => ({
      x: (i / (data.length - 1)) * 800,
      y: padding + (1 - (val - min) / range) * (height - padding * 2),
    }));

    let line = `M ${points[0].x},${points[0].y}`;
    for (let i = 1; i < points.length; i++) {
      line += ` L ${points[i].x},${points[i].y}`;
    }

    const area = line + ` L 800,${height} L 0,${height} Z`;

    // Calculate marker positions for wins/losses
    const markers = data.map((val, i) => {
      const trade = trades.filter((t) => t.type === 'EXIT').reverse()[i];
      return {
        x: (i / (data.length - 1)) * 800,
        y: padding + (1 - (val - min) / range) * (height - padding * 2),
        isWin: trade?.is_winner === true,
      };
    });

    return { line, area, markers };
  }, [stats.equityCurve, trades]);

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return {
      date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      time: date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }),
    };
  };

  return (
    <div className="h-full flex flex-col gap-4">
      {/* 1. Symbol P&L Curve */}
      <div className="relative h-48 bg-gradient-to-br from-bg via-surface to-bg rounded-lg border border-border p-4 overflow-hidden shrink-0">
        {/* Grid Pattern */}
        <div
          className="absolute inset-0 opacity-5"
          style={{
            backgroundImage: `linear-gradient(${theme.primary} 1px, transparent 1px), linear-gradient(90deg, ${theme.primary} 1px, transparent 1px)`,
            backgroundSize: '24px 24px',
          }}
        />

        {/* Header */}
        <div className="relative z-10 flex items-start justify-between mb-2">
          <div>
            <h3 className="text-xs uppercase tracking-wider text-text-dim font-mono">{symbol} Cumulative P&L</h3>
            <div className="flex items-baseline gap-2 mt-1">
              <span className={clsx('text-2xl font-mono font-bold', stats.totalPnl >= 0 ? 'text-positive' : 'text-negative')}>
                {stats.totalPnl >= 0 ? '+' : ''}${stats.totalPnl.toFixed(2)}
              </span>
              <span className="text-sm font-mono text-text-secondary">{stats.totalTrades} trades</span>
            </div>
          </div>
        </div>

        {/* SVG Equity Curve */}
        <div className="relative h-28">
          {stats.equityCurve.length >= 2 ? (
            <svg className="w-full h-full" viewBox="0 0 800 120" preserveAspectRatio="none">
              <line x1="0" y1="30" x2="800" y2="30" stroke={theme.border} strokeWidth="1" />
              <line x1="0" y1="60" x2="800" y2="60" stroke={theme.border} strokeWidth="1" />
              <line x1="0" y1="90" x2="800" y2="90" stroke={theme.border} strokeWidth="1" />

              <defs>
                <linearGradient id="equityGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor={theme.primary} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={theme.primary} stopOpacity={0} />
                </linearGradient>
              </defs>

              <path d={equityCurvePath.area} fill="url(#equityGradient)" />
              <path d={equityCurvePath.line} stroke={theme.primary} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />

              {equityCurvePath.markers?.map((m, i) => (
                <circle key={i} cx={m.x} cy={m.y} r="4" fill={m.isWin ? theme.positive : theme.negative} />
              ))}
            </svg>
          ) : (
            <div className="flex items-center justify-center h-full text-text-dim text-sm">
              No trade history yet
            </div>
          )}
        </div>

        {/* Floating Stats */}
        <div className="absolute bottom-4 right-4 flex gap-2">
          <div className="bg-positive/10 border border-positive/30 rounded px-2 py-1">
            <div className="text-[10px] text-text-dim uppercase">Avg Win</div>
            <div className="text-sm font-mono text-positive font-medium">+${stats.avgWin.toFixed(2)}</div>
          </div>
          <div className="bg-negative/10 border border-negative/30 rounded px-2 py-1">
            <div className="text-[10px] text-text-dim uppercase">Avg Loss</div>
            <div className="text-sm font-mono text-negative font-medium">-${stats.avgLoss.toFixed(2)}</div>
          </div>
          <div className="bg-neutral/10 border border-neutral/30 rounded px-2 py-1">
            <div className="text-[10px] text-text-dim uppercase">Avg R</div>
            <div className="text-sm font-mono text-neutral font-medium">{stats.avgR.toFixed(1)}R</div>
          </div>
        </div>
      </div>

      {/* 2. Performance Matrix */}
      <div className="grid grid-cols-4 gap-3 shrink-0">
        <PerformancePod label="Daily" pnl={stats.daily.pnl} wins={stats.daily.wins} losses={stats.daily.losses} />
        <PerformancePod label="Weekly" pnl={stats.weekly.pnl} wins={stats.weekly.wins} losses={stats.weekly.losses} />
        <PerformancePod label="Monthly" pnl={stats.monthly.pnl} wins={stats.monthly.wins} losses={stats.monthly.losses} />
        <PerformancePod label="All-Time" pnl={stats.totalPnl} wins={stats.wins} losses={stats.losses} featured />
      </div>

      {/* 3. Trade Timeline */}
      <div className="flex-1 min-h-0 flex flex-col">
        <div className="flex items-center justify-between mb-3 shrink-0">
          <h3 className="text-sm uppercase tracking-wider text-text-secondary font-mono">{symbol} Trades</h3>
          <div className="flex gap-2">
            {(['all', 'wins', 'losses'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={clsx(
                  'px-2 py-1 text-xs font-mono rounded transition',
                  filter === f
                    ? f === 'wins'
                      ? 'bg-positive/20 text-positive border border-positive/30'
                      : f === 'losses'
                        ? 'bg-negative/20 text-negative border border-negative/30'
                        : 'bg-primary/20 text-primary border border-primary/30'
                    : 'text-text-dim hover:text-text'
                )}
              >
                {f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto space-y-2 pr-1 custom-scrollbar">
          {filteredTrades.length === 0 ? (
            <div className="flex items-center justify-center h-32 text-text-dim text-sm">
              No trades to display
            </div>
          ) : (
            filteredTrades.map((trade, i) => (
              <TradeTimelineItem key={i} trade={trade} formatTime={formatTime} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

interface PerformancePodProps {
  label: string;
  pnl: number;
  wins: number;
  losses: number;
  featured?: boolean;
}

function PerformancePod({ label, pnl, wins, losses, featured }: PerformancePodProps) {
  const total = wins + losses;
  const winRate = total > 0 ? (wins / total) * 100 : 0;

  return (
    <div
      className={clsx(
        'rounded-lg p-3 relative overflow-hidden',
        featured
          ? 'bg-gradient-to-br from-primary/10 via-surface to-surface border border-primary/30'
          : 'bg-surface border border-border hover:border-primary/50 transition-all cursor-pointer group'
      )}
    >
      {featured && <div className="absolute top-0 right-0 w-12 h-12 bg-primary/20 blur-2xl" />}
      <div className="flex items-center justify-between mb-2 relative">
        <span className={clsx('text-xs uppercase tracking-wider font-mono', featured ? 'text-primary font-bold' : 'text-text-dim')}>
          {label}
        </span>
        {featured && (
          <div className="flex items-center gap-1 text-xs font-mono text-positive">
            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
            </svg>
            <span>{winRate >= 70 ? 'A+' : winRate >= 50 ? 'B' : 'C'}</span>
          </div>
        )}
        {!featured && (
          <svg className="w-3 h-3 text-positive opacity-0 group-hover:opacity-100 transition-opacity" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10.293 3.293a1 1 0 011.414 0l6 6a1 1 0 010 1.414l-6 6a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-4.293-4.293a1 1 0 010-1.414z" />
          </svg>
        )}
      </div>
      <div className={clsx('font-mono text-xl font-bold mb-1 relative', pnl >= 0 ? 'text-positive' : 'text-negative')}>
        {pnl >= 0 ? '+' : '-'}${Math.abs(pnl).toFixed(0)}
      </div>
      <div className="flex items-center justify-between text-xs relative">
        <div className="flex items-center gap-1">
          <div className="w-1.5 h-1.5 rounded-full bg-positive" />
          <span className="text-text-secondary">{wins}W</span>
          <span className="text-text-dim">·</span>
          <div className="w-1.5 h-1.5 rounded-full bg-negative" />
          <span className="text-text-secondary">{losses}L</span>
        </div>
        <span className={clsx('font-mono font-medium', winRate >= 50 ? 'text-positive' : 'text-negative')}>{winRate.toFixed(0)}%</span>
      </div>
      <div className="mt-2 h-1 bg-border rounded-full overflow-hidden relative">
        <div
          className={clsx('h-full rounded-full', featured ? 'bg-gradient-to-r from-positive via-primary to-neutral' : 'bg-gradient-to-r from-positive to-primary')}
          style={{ width: `${winRate}%` }}
        />
      </div>
    </div>
  );
}

interface TradeTimelineItemProps {
  trade: TradeAlert;
  formatTime: (ts: string) => { date: string; time: string };
}

function TradeTimelineItem({ trade, formatTime }: TradeTimelineItemProps) {
  const time = formatTime(trade.timestamp);
  const isWin = trade.is_winner === true;
  const isLong = trade.direction === 'LONG';

  return (
    <div
      className={clsx(
        'group bg-surface border border-border rounded-lg transition-all',
        isWin ? 'hover:border-positive/50' : 'hover:border-negative/50'
      )}
    >
      <div className="flex items-center gap-3 p-3">
        {/* Time Badge */}
        <div className="flex flex-col items-center justify-center bg-surface-dark rounded px-2 py-1 min-w-[56px]">
          <span className="text-[10px] text-text-dim font-mono">{time.date}</span>
          <span className="text-xs text-text font-mono font-bold">{time.time}</span>
        </div>

        {/* Trade Details */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className={clsx('text-xs font-medium', isLong ? 'text-positive' : 'text-negative')}>
              {isLong ? '▲ LONG' : '▼ SHORT'}
            </span>
            <span className="text-text-dim">·</span>
            <span className="text-xs text-text-secondary">{trade.size} sh</span>
          </div>
          <div className="flex items-center gap-2 text-xs font-mono">
            <span className="text-text-secondary">${trade.price.toFixed(2)}</span>
            {trade.reason && (
              <>
                <span className="text-text-dim">·</span>
                <span className="text-text-dim">{trade.reason}</span>
              </>
            )}
          </div>
        </div>

        {/* P&L */}
        <div className="flex flex-col items-end">
          <span className={clsx('text-base font-mono font-bold', isWin ? 'text-positive' : 'text-negative')}>
            {(trade.pnl ?? 0) >= 0 ? '+' : ''}${(trade.pnl ?? 0).toFixed(2)}
          </span>
          {trade.pnl_pct !== null && (
            <span className={clsx('text-xs font-mono', isWin ? 'text-positive' : 'text-negative')}>
              {trade.pnl_pct >= 0 ? '+' : ''}{trade.pnl_pct.toFixed(2)}%
            </span>
          )}
        </div>

        {/* Result Badge */}
        <span
          className={clsx(
            'px-2 py-1 rounded text-xs font-medium',
            isWin ? 'bg-positive/20 text-positive' : 'bg-negative/20 text-negative'
          )}
        >
          {trade.reason === 'EOD' ? 'EOD' : isWin ? 'TP' : 'SL'}
        </span>
      </div>
    </div>
  );
}

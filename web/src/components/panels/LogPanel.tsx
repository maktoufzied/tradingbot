import { useEffect, useRef, useState } from 'react';
import { useLogs } from '../../store/tradingStore';

const levelColors: Record<string, string> = {
  DEBUG: 'text-text-dim',
  INFO: 'text-primary',
  WARNING: 'text-warning',
  ERROR: 'text-negative',
};

export function LogPanel() {
  const logs = useLogs();
  const containerRef = useRef<HTMLDivElement>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  // Detect manual scroll to disable auto-scroll
  const handleScroll = () => {
    if (containerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 10;
      setAutoScroll(isAtBottom);
    }
  };

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  };

  return (
    <div className={`border-t border-border bg-surface-dark transition-all ${isExpanded ? 'h-64' : 'h-10'}`}>
      {/* Header */}
      <div
        className="h-10 px-4 flex items-center justify-between cursor-pointer hover:bg-surface"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-text-secondary">FEED LOG</span>
          <span className="text-xs text-text-dim">({logs.length})</span>
          {logs.length > 0 && (
            <span className={`text-xs ${levelColors[logs[logs.length - 1]?.level] || 'text-text-dim'}`}>
              {logs[logs.length - 1]?.message.slice(0, 50)}
              {(logs[logs.length - 1]?.message.length || 0) > 50 ? '...' : ''}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {!autoScroll && isExpanded && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setAutoScroll(true);
              }}
              className="text-xs text-primary hover:underline"
            >
              Resume auto-scroll
            </button>
          )}
          <span className="text-text-dim text-xs">{isExpanded ? '▼' : '▲'}</span>
        </div>
      </div>

      {/* Log content */}
      {isExpanded && (
        <div
          ref={containerRef}
          onScroll={handleScroll}
          className="h-[calc(100%-2.5rem)] overflow-y-auto px-4 py-2 font-mono text-xs"
        >
          {logs.length === 0 ? (
            <div className="text-text-dim text-center py-4">No logs yet</div>
          ) : (
            logs.map((log, i) => (
              <div key={i} className="flex gap-2 py-0.5 hover:bg-surface">
                <span className="text-text-dim shrink-0">{formatTime(log.timestamp)}</span>
                <span className={`shrink-0 w-14 ${levelColors[log.level] || 'text-text-dim'}`}>
                  [{log.level}]
                </span>
                <span className="text-text">{log.message}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

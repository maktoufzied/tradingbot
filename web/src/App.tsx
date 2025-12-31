import { useWebSocket } from './hooks/useWebSocket';
import { Header } from './components/layout/Header';
import { Sidebar } from './components/layout/Sidebar';
import { SymbolGrid } from './components/cards/SymbolGrid';
import { TradeLog } from './components/trade-log/TradeLog';
import { LogPanel } from './components/panels/LogPanel';
import { useConnectionStatus } from './store/tradingStore';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8765';

function App() {
  useWebSocket({ url: WS_URL });
  const connected = useConnectionStatus();

  return (
    <div className="h-screen flex flex-col bg-bg">
      <Header />

      <div className="flex-1 flex overflow-hidden">
        {/* Main content */}
        <main className="flex-1 flex flex-col overflow-hidden min-h-0">
          {/* Symbol grid - scrollable */}
          <div className="flex-1 overflow-y-auto min-h-0">
            <SymbolGrid />
          </div>
          {/* Trade log - fixed at bottom */}
          <TradeLog />
          {/* Feed log - collapsible at very bottom */}
          <LogPanel />
        </main>

        {/* Sidebar */}
        <Sidebar />
      </div>

      {/* Connection overlay */}
      {!connected && (
        <div className="fixed inset-0 bg-bg/80 flex items-center justify-center z-50">
          <div className="bg-surface p-8 rounded-lg border border-border text-center">
            <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-text-secondary">Connecting to trading server...</p>
            <p className="text-xs text-text-dim mt-2">{WS_URL}</p>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;

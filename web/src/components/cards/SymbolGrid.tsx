import { useSymbols } from '../../store/tradingStore';
import { SymbolCard } from './SymbolCard';

export function SymbolGrid() {
  const symbols = useSymbols();

  if (symbols.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-text-dim">
        <div className="text-center">
          <p className="text-lg mb-2">No symbols connected</p>
          <p className="text-sm">Waiting for WebSocket data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 grid gap-4 auto-rows-min grid-cols-1 lg:grid-cols-2 xl:grid-cols-3">
      {symbols.map((symbol) => (
        <SymbolCard key={symbol} symbol={symbol} />
      ))}
    </div>
  );
}

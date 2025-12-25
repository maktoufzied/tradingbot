import { useEffect, useRef, useState } from 'react';
import clsx from 'clsx';

interface PriceDisplayProps {
  price: number;
  change: number;
  changePct: number;
  size?: 'sm' | 'md' | 'lg';
}

export function PriceDisplay({ price, change, changePct, size = 'md' }: PriceDisplayProps) {
  const prevPriceRef = useRef(price);
  const [flashClass, setFlashClass] = useState<string | null>(null);

  useEffect(() => {
    if (price !== prevPriceRef.current) {
      const direction = price > prevPriceRef.current ? 'flash-up' : 'flash-down';
      setFlashClass(direction);
      prevPriceRef.current = price;

      const timeout = setTimeout(() => setFlashClass(null), 500);
      return () => clearTimeout(timeout);
    }
  }, [price]);

  const isPositive = change >= 0;

  return (
    <div className={clsx('rounded px-1', flashClass)}>
      <div
        className={clsx(
          'mono font-semibold',
          size === 'sm' && 'text-lg',
          size === 'md' && 'text-2xl',
          size === 'lg' && 'text-3xl'
        )}
      >
        ${price.toFixed(2)}
      </div>
      <div
        className={clsx(
          'mono flex items-center gap-1',
          size === 'sm' && 'text-xs',
          size === 'md' && 'text-sm',
          size === 'lg' && 'text-base',
          isPositive ? 'text-positive' : 'text-negative'
        )}
      >
        <span>{isPositive ? '▲' : '▼'}</span>
        <span>
          {isPositive ? '+' : ''}
          {change.toFixed(2)}
        </span>
        <span>
          ({isPositive ? '+' : ''}
          {changePct.toFixed(2)}%)
        </span>
      </div>
    </div>
  );
}

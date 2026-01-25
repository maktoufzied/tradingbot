import { useEffect, useRef } from 'react';
import clsx from 'clsx';

interface PriceDisplayProps {
  price: number;
  change: number;
  changePct: number;
  size?: 'sm' | 'md' | 'lg';
}

export function PriceDisplay({ price, change, changePct, size = 'md' }: PriceDisplayProps) {
  const prevPriceRef = useRef(price);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (price !== prevPriceRef.current && el) {
      const direction = price > prevPriceRef.current ? 'flash-up' : 'flash-down';
      el.classList.add(direction);
      prevPriceRef.current = price;

      const timeout = setTimeout(() => {
        el.classList.remove('flash-up', 'flash-down');
      }, 500);
      return () => clearTimeout(timeout);
    }
  }, [price]);

  const isPositive = change >= 0;

  return (
    <div ref={containerRef} className="rounded px-1">
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

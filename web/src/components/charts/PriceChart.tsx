import { useEffect, useRef } from 'react';
import { createChart, LineSeries, LineStyle } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, IPriceLine } from 'lightweight-charts';
import type { PositionUpdate, ChartUpdate } from '../../types/api';
import { theme } from '../../styles/theme';

interface PriceChartProps {
  chartData: ChartUpdate | undefined;
  position?: PositionUpdate;
  height?: number;
}

export function PriceChart({ chartData, position, height = 150 }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);

  // Create chart on mount
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: theme.surfaceDark },
        textColor: theme.textSecondary,
      },
      grid: {
        vertLines: { color: theme.borderDim },
        horzLines: { color: theme.borderDim },
      },
      crosshair: {
        horzLine: {
          color: theme.textDim,
          labelBackgroundColor: theme.surface,
        },
        vertLine: {
          color: theme.textDim,
          labelBackgroundColor: theme.surface,
        },
      },
      rightPriceScale: {
        borderColor: theme.border,
      },
      timeScale: {
        borderColor: theme.border,
        timeVisible: true,
        secondsVisible: false,
      },
      height,
    });

    const series = chart.addSeries(LineSeries, {
      color: theme.primary,
      lineWidth: 2,
      priceLineVisible: true,
      lastValueVisible: true,
    });

    chartRef.current = chart;
    seriesRef.current = series;

    // Handle resize
    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);
    handleResize();

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [height]);

  // Update data
  useEffect(() => {
    if (!seriesRef.current || !chartData) return;

    const data = chartData.prices.map((price, i) => ({
      time: Math.floor(new Date(chartData.timestamps[i]).getTime() / 1000) as any,
      value: price,
    }));

    seriesRef.current.setData(data);
  }, [chartData]);

  // Update position lines
  useEffect(() => {
    if (!seriesRef.current) return;

    // Remove existing price lines
    for (const line of priceLinesRef.current) {
      seriesRef.current.removePriceLine(line);
    }
    priceLinesRef.current = [];

    if (position?.is_open) {
      // Entry price line
      const entryLine = seriesRef.current.createPriceLine({
        price: position.entry_price,
        color: theme.neutral,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: 'Entry',
      });
      priceLinesRef.current.push(entryLine);

      // Stop loss line
      if (position.stop_loss > 0) {
        const slLine = seriesRef.current.createPriceLine({
          price: position.stop_loss,
          color: theme.negative,
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: 'SL',
        });
        priceLinesRef.current.push(slLine);
      }

      // Take profit line
      if (position.take_profit > 0) {
        const tpLine = seriesRef.current.createPriceLine({
          price: position.take_profit,
          color: theme.positive,
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: 'TP',
        });
        priceLinesRef.current.push(tpLine);
      }
    }
  }, [position?.is_open, position?.entry_price, position?.stop_loss, position?.take_profit]);

  return <div ref={containerRef} className="w-full" />;
}

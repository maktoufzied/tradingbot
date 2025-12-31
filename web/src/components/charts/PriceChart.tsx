import { useEffect, useRef } from 'react';
import { createChart, CandlestickSeries, LineStyle, createSeriesMarkers } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, IPriceLine, SeriesMarker, Time, ISeriesMarkersPluginApi } from 'lightweight-charts';
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
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

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

    const series = chart.addSeries(CandlestickSeries, {
      upColor: theme.positive,
      downColor: theme.negative,
      borderUpColor: theme.positive,
      borderDownColor: theme.negative,
      wickUpColor: theme.positive,
      wickDownColor: theme.negative,
      priceLineVisible: true,
      lastValueVisible: true,
    });

    chartRef.current = chart;
    seriesRef.current = series;

    // Create markers plugin for 5m boundary indicators
    markersRef.current = createSeriesMarkers(series, []);

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
    if (!seriesRef.current || !chartData?.closes?.length) return;

    try {
      const now = new Date();

      // Get timezone offset in seconds (negative for west of UTC)
      const tzOffsetSeconds = now.getTimezoneOffset() * 60;

      // Filter to today's data only, excluding invalid points
      const rawData = chartData.timestamps
        .map((timestamp, i) => {
          const open = chartData.opens[i];
          const high = chartData.highs[i];
          const low = chartData.lows[i];
          const close = chartData.closes[i];
          if (open == null || high == null || low == null || close == null || timestamp == null) return null;
          // Parse timestamp - backend sends naive UTC, treat as UTC
          const isoStr = timestamp.endsWith('Z') ? timestamp : timestamp + 'Z';
          const date = new Date(isoStr);
          const utcTime = Math.floor(date.getTime() / 1000);
          if (isNaN(utcTime) || utcTime <= 0) return null;
          // Only include today's data (compare in local time)
          const localDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
          const todayDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
          if (localDate.getTime() !== todayDate.getTime()) return null;
          // Shift UTC to local time for display (lightweight-charts shows UTC)
          const localTime = utcTime - tzOffsetSeconds;
          return { time: localTime, open, high, low, close, utcDate: date };
        })
        .filter((d): d is { time: number; open: number; high: number; low: number; close: number; utcDate: Date } => d !== null);

      // Sort by time and deduplicate (keep last value for each timestamp)
      const timeMap = new Map<number, { open: number; high: number; low: number; close: number; utcDate: Date }>();
      for (const point of rawData) {
        timeMap.set(point.time, { open: point.open, high: point.high, low: point.low, close: point.close, utcDate: point.utcDate });
      }

      const data = Array.from(timeMap.entries())
        .sort((a, b) => a[0] - b[0])
        .map(([time, { open, high, low, close }]) => ({ time: time as Time, open, high, low, close }));

      if (data.length > 0) {
        seriesRef.current.setData(data);

        // Add markers at 5m boundaries (strategy evaluation points)
        if (markersRef.current) {
          const markers: SeriesMarker<Time>[] = [];
          for (const [time, { utcDate }] of timeMap.entries()) {
            const minute = utcDate.getMinutes();
            // Mark every 5m boundary (0, 5, 10, 15, etc.)
            if (minute % 5 === 4) {  // End of 5m period (e.g., :04, :09, :14...)
              markers.push({
                time: time as Time,
                position: 'belowBar',
                color: theme.textDim,
                shape: 'square',
                size: 0.5,
              });
            }
          }
          markersRef.current.setMarkers(markers.sort((a, b) => (a.time as number) - (b.time as number)));
        }
      }
    } catch (err) {
      console.warn('Chart update error:', err);
    }
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

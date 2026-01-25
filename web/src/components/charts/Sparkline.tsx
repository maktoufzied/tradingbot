import { useId, useMemo } from 'react';
import { theme } from '../../styles/theme';

interface SparklineProps {
  data: number[];
  height?: number;
  color?: string;
  entryPrice?: number;
}

export function Sparkline({ data, height = 70, color, entryPrice }: SparklineProps) {
  const sparklineColor = color ?? (data.length > 1 && data[data.length - 1] >= data[0] ? theme.positive : theme.negative);

  const { linePath, areaPath, entryY } = useMemo(() => {
    if (data.length < 2) {
      return { linePath: '', areaPath: '', entryY: null };
    }

    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const padding = 2;
    const viewHeight = height - padding * 2;

    const points = data.map((val, i) => ({
      x: (i / (data.length - 1)) * 100,
      y: padding + (1 - (val - min) / range) * viewHeight,
    }));

    // Create smooth curve using quadratic bezier
    let path = `M ${points[0].x},${points[0].y}`;
    for (let i = 1; i < points.length; i++) {
      const prev = points[i - 1];
      const curr = points[i];
      const cpx = (prev.x + curr.x) / 2;
      path += ` Q ${cpx},${prev.y} ${curr.x},${curr.y}`;
    }

    // Area path (for gradient fill)
    const area = path + ` L 100,${height} L 0,${height} Z`;

    // Calculate entry price Y position
    let entryLineY: number | null = null;
    if (entryPrice !== undefined && entryPrice >= min && entryPrice <= max) {
      entryLineY = padding + (1 - (entryPrice - min) / range) * viewHeight;
    }

    return { linePath: path, areaPath: area, entryY: entryLineY };
  }, [data, height, entryPrice]);

  const id = useId();
  const gradientId = `sparkline-gradient-${id}`;

  if (data.length < 2) {
    return <div className="w-full" style={{ height }} />;
  }

  return (
    <div className="relative w-full" style={{ height }}>
      <svg
        viewBox={`0 0 100 ${height}`}
        preserveAspectRatio="none"
        className="w-full h-full"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={sparklineColor} stopOpacity={0.4} />
            <stop offset="100%" stopColor={sparklineColor} stopOpacity={0.05} />
          </linearGradient>
        </defs>
        <path d={areaPath} fill={`url(#${gradientId})`} />
        <path
          d={linePath}
          fill="none"
          stroke={sparklineColor}
          strokeWidth="0.8"
          strokeLinecap="round"
        />
      </svg>
      {entryY !== null && (
        <div
          className="absolute left-0 right-0 border-t border-dashed"
          style={{
            top: `${(entryY / height) * 100}%`,
            borderColor: `${theme.primary}99`,
          }}
        />
      )}
    </div>
  );
}

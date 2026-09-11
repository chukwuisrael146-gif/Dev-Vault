import { useId } from 'react';
export function TrafficChart({ series }: { series: { hour: string; requests: number }[] }) {
  const id = useId();
  const maximum = Math.max(1, ...series.map((point) => point.requests));
  const first = Date.parse(series[0].hour);
  const last = Date.parse(series[series.length - 1].hour);
  const points = series
    .map(
      (point) =>
        `${last === first ? 440 : ((Date.parse(point.hour) - first) / (last - first)) * 880},${180 - (point.requests / maximum) * 155}`,
    )
    .join(' ');
  return (
    <figure className="traffic-chart">
      <div className="plot">
        <div className="y-axis">
          <span>{maximum.toLocaleString()}</span>
          <span>{Math.round(maximum / 2).toLocaleString()}</span>
          <span>0</span>
        </div>
        <svg
          viewBox="0 0 880 190"
          preserveAspectRatio="none"
          role="img"
          aria-label={`Recorded request counts in ${series.length} UTC buckets`}
        >
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#c8e598" stopOpacity=".15" />
              <stop offset="100%" stopColor="#c8e598" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[25, 100, 180].map((y) => (
            <line key={y} x1="0" y1={y} x2="880" y2={y} stroke="#ffffff15" strokeDasharray="3 6" />
          ))}
          <polyline
            points={points}
            fill="none"
            stroke="#cee89e"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
          {series.length === 1 && (
            <circle cx="440" cy={180 - (series[0].requests / maximum) * 155} r="4" fill="#cee89e" />
          )}
        </svg>
      </div>
      <div className="x-axis">
        <span>{series[0].hour.replace('T', ' ').slice(0, 16)}</span>
        <span>{series[series.length - 1].hour.replace('T', ' ').slice(0, 16)}</span>
      </div>
      <figcaption>
        <span className="legend-line" />
        Requests · UTC
        <details>
          <summary>View values</summary>
          <p>{series.map((point) => `${point.hour}: ${point.requests}`).join(' · ')}</p>
        </details>
      </figcaption>
    </figure>
  );
}

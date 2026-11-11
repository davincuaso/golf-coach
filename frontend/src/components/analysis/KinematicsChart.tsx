"use client";
import { useId } from "react";
import { linePath, type ChartPoint } from "@/lib/visualization";
import type { SwingEvents } from "@/lib/api-types";

interface Props {
  title: string;
  description: string;
  unit: string;
  points: ChartPoint[];
  playhead: number;
  events: SwingEvents | null;
  baseline?: number | null;
}
export function KinematicsChart({
  title,
  description,
  unit,
  points,
  playhead,
  events,
  baseline,
}: Props) {
  const id = useId();
  const values = points.flatMap((point) =>
    point.value === null ? [] : [point.value],
  );
  const width = 600,
    height = 192,
    left = 46,
    right = 18,
    top = 22,
    bottom = 30;
  const maxTime = Math.max(points.at(-1)?.time ?? 0, 0.01);
  const observed = baseline == null ? values : [...values, baseline];
  const low = Math.min(...observed),
    high = Math.max(...observed);
  const padding = Math.max((high - low) * 0.18, 1);
  const min = low - padding,
    max = high + padding;
  const x = (time: number) => left + (time / maxTime) * (width - left - right);
  const y = (value: number) =>
    top + ((max - value) / (max - min)) * (height - top - bottom);
  const path = values.length ? linePath(points, x, y) : "";
  const markers = events
    ? ([
        ["S", events.start_seconds],
        ["T", events.top_seconds],
        ["I", events.impact_seconds],
      ] as const)
    : [];
  return (
    <div className="chart-block">
      <div className="chart-heading">
        <h3>{title}</h3>
        <span>{unit}</span>
      </div>
      <p className="help-text">{description}</p>
      {!values.length ? (
        <div className="chart-empty">
          No reliable measurements for this metric.
        </div>
      ) : (
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="kinematics-chart"
          role="img"
          aria-labelledby={`${id}-title ${id}-description`}
        >
          <title id={`${id}-title`}>{title} over time</title>
          <desc id={`${id}-description`}>
            {values.length} measurements from {low.toFixed(1)} to{" "}
            {high.toFixed(1)} {unit}. Gaps indicate missing tracking. S is swing
            start, T is top, and I is impact.
          </desc>
          {[0, 0.5, 1].map((fraction) => {
            const value = min + (max - min) * fraction;
            return (
              <g key={fraction}>
                <line
                  x1={left}
                  x2={width - right}
                  y1={y(value)}
                  y2={y(value)}
                  className="chart-grid-line"
                />
                <text
                  x={left - 10}
                  y={y(value) + 4}
                  textAnchor="end"
                  className="chart-label"
                >
                  {value.toFixed(0)}
                </text>
              </g>
            );
          })}
          {[0, 0.5, 1].map((fraction) => (
            <text
              key={fraction}
              x={x(maxTime * fraction)}
              y={height - 7}
              textAnchor="middle"
              className="chart-label"
            >
              {(maxTime * fraction).toFixed(1)}s
            </text>
          ))}
          {baseline != null && (
            <line
              x1={left}
              x2={width - right}
              y1={y(baseline)}
              y2={y(baseline)}
              className="chart-baseline"
            />
          )}
          {markers
            .filter(([, time]) => time <= maxTime)
            .map(([label, time]) => (
              <g key={label}>
                <line
                  x1={x(time)}
                  x2={x(time)}
                  y1={top}
                  y2={height - bottom}
                  className="chart-event"
                />
                <text
                  x={x(time)}
                  y={12}
                  textAnchor="middle"
                  className="chart-label"
                >
                  {label}
                </text>
              </g>
            ))}
          <path d={path} className="chart-data-line" />
          {points.length === 1 && points[0].value !== null && (
            <circle
              cx={x(points[0].time)}
              cy={y(points[0].value)}
              r="3"
              fill="var(--green)"
            />
          )}
          {playhead >= 0 && playhead <= maxTime && (
            <line
              x1={x(playhead)}
              x2={x(playhead)}
              y1={top}
              y2={height - bottom}
              className="chart-playhead"
            />
          )}
        </svg>
      )}
    </div>
  );
}

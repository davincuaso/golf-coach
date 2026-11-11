import type { PoseFrame } from "./api-types.ts";

/** Timestamps, rather than frame-index/fps arithmetic, preserve variable-rate alignment. */
export function nearestPoseFrame(
  frames: PoseFrame[],
  time: number,
  tolerance = 0.15,
): number {
  if (!frames.length || !Number.isFinite(time)) return -1;
  let low = 0,
    high = frames.length;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (frames[middle].timestamp_seconds < time) low = middle + 1;
    else high = middle;
  }
  const after = Math.min(low, frames.length - 1),
    before = Math.max(0, low - 1);
  const index =
    Math.abs(frames[before].timestamp_seconds - time) <=
    Math.abs(frames[after].timestamp_seconds - time)
      ? before
      : after;
  return Math.abs(frames[index].timestamp_seconds - time) <= tolerance
    ? index
    : -1;
}
export interface ChartPoint {
  time: number;
  value: number | null;
}
/** Start a new segment after every missing value. Never fabricate a line through tracking gaps. */
export function linePath(
  points: ChartPoint[],
  x: (value: number) => number,
  y: (value: number) => number,
): string {
  let open = false;
  return points
    .map((point) => {
      if (
        point.value === null ||
        !Number.isFinite(point.value) ||
        !Number.isFinite(point.time)
      ) {
        open = false;
        return "";
      }
      const command = open ? "L" : "M";
      open = true;
      return `${command}${x(point.time).toFixed(2)},${y(point.value).toFixed(2)}`;
    })
    .join(" ")
    .trim();
}
export function formatMetric(
  value: number | null,
  suffix = "",
  decimals = 1,
): string {
  return value === null || !Number.isFinite(value)
    ? "—"
    : `${value.toFixed(decimals)}${suffix}`;
}

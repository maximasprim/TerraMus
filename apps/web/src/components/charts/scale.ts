export interface NiceScale {
  min: number;
  max: number;
  ticks: number[];
}

/**
 * A "nice" axis for [minV, maxV] that always includes zero, with round steps
 * (1, 2, 2.5, 5 x 10^n) and roughly `tickCount` intervals.
 */
export function niceScale(minV: number, maxV: number, tickCount = 4): NiceScale {
  let lo = Math.min(0, minV);
  let hi = Math.max(0, maxV);
  if (hi === lo) hi = lo + 1;
  const rawStep = (hi - lo) / Math.max(1, tickCount);
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const norm = rawStep / magnitude;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * magnitude;
  const min = Math.floor(lo / step) * step;
  const max = Math.ceil(hi / step) * step;
  const ticks: number[] = [];
  const steps = Math.round((max - min) / step);
  for (let i = 0; i <= steps; i++) ticks.push(Number((min + i * step).toFixed(10)));
  return { min, max, ticks };
}

export interface Slice {
  label: string;
  value: number;
  color?: string;
}

/**
 * Largest `maxSlices - 1` slices stay as they are; the rest are folded into one
 * "Other" slice, so a donut with 20 categories stays legible. Zero/negative
 * values are dropped (they have no area to draw).
 */
export function groupSmallSlices(data: Slice[], maxSlices = 7): Slice[] {
  const positive = data.filter((d) => d.value > 0).sort((a, b) => b.value - a.value);
  if (positive.length <= maxSlices) return positive;
  const head = positive.slice(0, maxSlices - 1);
  const rest = positive.slice(maxSlices - 1);
  return [...head, { label: "Other", value: rest.reduce((sum, d) => sum + d.value, 0) }];
}

/** How many x labels fit: show every k-th so labels never collide. */
export function labelStride(count: number, band: number, longestLabelChars: number): number {
  const needed = longestLabelChars * 6.2 + 10;
  if (band <= 0) return 1;
  return Math.max(1, Math.ceil(needed / band));
}

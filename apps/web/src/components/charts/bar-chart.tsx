"use client";

import { useState, type KeyboardEvent } from "react";
import { ChartLegend, ChartTooltip, DataTable } from "./chart-parts";
import { compactNumber, count } from "./format";
import { labelStride, niceScale } from "./scale";
import { useElementWidth } from "./use-element-width";

export interface BarSeries {
  name: string;
  color: string;
  values: number[];
}

const TOP = 12;
const RIGHT = 10;
const BOTTOM_VERTICAL = 28;
const BOTTOM_HORIZONTAL = 24;
const ROW_HEIGHT = 30;
const CHAR_PX = 6.3;

/**
 * Grouped, stacked or horizontal bar chart. Draws at the container's real width.
 * Values may be negative (bars grow from the zero line). Hover, touch or use the
 * arrow keys to read a category; a hidden table mirrors the data for screen readers.
 */
export function BarChart({
  categories, series, stacked = false, horizontal = false, format = count, axisFormat = compactNumber,
  height = 260, ariaLabel, tooltipTitles, showLegend,
}: {
  categories: string[];
  series: BarSeries[];
  stacked?: boolean;
  horizontal?: boolean;
  format?: (n: number) => string;
  axisFormat?: (n: number) => string;
  height?: number;
  ariaLabel: string;
  tooltipTitles?: string[];
  showLegend?: boolean;
}) {
  const [ref, width] = useElementWidth();
  const [active, setActive] = useState<number | null>(null);
  const n = categories.length;
  const k = series.length;
  if (n === 0 || k === 0) return <p className="py-8 text-center text-sm text-muted">No data yet.</p>;

  // --- domain ---
  let lo = 0;
  let hi = 0;
  for (let i = 0; i < n; i++) {
    if (stacked) {
      let pos = 0;
      let neg = 0;
      for (const s of series) (s.values[i] ?? 0) >= 0 ? (pos += s.values[i] ?? 0) : (neg += s.values[i] ?? 0);
      hi = Math.max(hi, pos);
      lo = Math.min(lo, neg);
    } else {
      for (const s of series) {
        hi = Math.max(hi, s.values[i] ?? 0);
        lo = Math.min(lo, s.values[i] ?? 0);
      }
    }
  }
  const scale = niceScale(lo, hi, horizontal ? 4 : 4);
  const span = scale.max - scale.min || 1;

  // --- geometry ---
  const longestCategory = Math.max(...categories.map((c) => c.length));
  const longestTick = Math.max(...scale.ticks.map((t) => axisFormat(t).length));
  const left = horizontal ? Math.min(150, Math.max(48, longestCategory * CHAR_PX + 14)) : Math.max(36, longestTick * CHAR_PX + 12);
  const chartHeight = horizontal ? TOP + n * ROW_HEIGHT + BOTTOM_HORIZONTAL : height;
  const plotW = Math.max(40, width - left - RIGHT);
  const plotH = chartHeight - TOP - (horizontal ? BOTTOM_HORIZONTAL : BOTTOM_VERTICAL);
  const band = horizontal ? ROW_HEIGHT : plotW / n;

  const vy = (v: number) => TOP + plotH * (1 - (v - scale.min) / span); // vertical value -> y
  const hx = (v: number) => left + plotW * ((v - scale.min) / span); // horizontal value -> x
  const zero = horizontal ? hx(0) : vy(0);
  const stride = horizontal ? 1 : labelStride(n, band, Math.max(...categories.map((c) => c.length)));

  const thickness = stacked
    ? Math.min(horizontal ? 18 : 48, (horizontal ? ROW_HEIGHT : band) * 0.62)
    : Math.min(horizontal ? 16 : 36, ((horizontal ? ROW_HEIGHT : band) * 0.72 - (k - 1) * 3) / k);
  const groupSize = stacked ? thickness : k * thickness + (k - 1) * 3;

  // --- bars ---
  const bars: { key: string; x: number; y: number; w: number; h: number; color: string }[] = [];
  for (let i = 0; i < n; i++) {
    let posAcc = 0;
    let negAcc = 0;
    const slot = (horizontal ? TOP : left) + i * band + (band - groupSize) / 2;
    series.forEach((s, j) => {
      const v = s.values[i] ?? 0;
      if (v === 0) return;
      const offset = stacked ? 0 : j * (thickness + 3);
      let from = 0;
      let to = v;
      if (stacked) {
        if (v >= 0) { from = posAcc; posAcc += v; to = posAcc; } else { from = negAcc; negAcc += v; to = negAcc; }
      }
      if (horizontal) {
        const x1 = hx(from), x2 = hx(to);
        bars.push({ key: `${i}-${j}`, x: Math.min(x1, x2), y: slot + offset, w: Math.max(1, Math.abs(x2 - x1)), h: thickness, color: s.color });
      } else {
        const y1 = vy(from), y2 = vy(to);
        bars.push({ key: `${i}-${j}`, x: slot + offset, y: Math.min(y1, y2), w: thickness, h: Math.max(1, Math.abs(y2 - y1)), color: s.color });
      }
    });
  }

  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); setActive((a) => (a === null ? 0 : Math.min(n - 1, a + 1))); }
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); setActive((a) => (a === null ? n - 1 : Math.max(0, a - 1))); }
    else if (e.key === "Home") { e.preventDefault(); setActive(0); }
    else if (e.key === "End") { e.preventDefault(); setActive(n - 1); }
    else if (e.key === "Escape") setActive(null);
  };

  const tipX = active === null ? 0 : horizontal ? left + plotW / 2 : left + active * band + band / 2;
  const tipY = active === null ? 0 : horizontal ? TOP + active * band - 8 : 0;

  return (
    <div ref={ref} className="relative w-full">
      {(showLegend ?? k > 1) && <ChartLegend items={series.map((s) => ({ name: s.name, color: s.color }))} />}
      <div className="relative">
        <svg
          width={width} height={chartHeight} role="img" aria-label={ariaLabel} tabIndex={0}
          onKeyDown={onKey} onBlur={() => setActive(null)} onMouseLeave={() => setActive(null)}
          className="block overflow-visible rounded outline-none focus-visible:ring-2 focus-visible:ring-brass"
        >
          {/* grid + tick labels */}
          {scale.ticks.map((t) =>
            horizontal ? (
              <g key={t}>
                <line x1={hx(t)} x2={hx(t)} y1={TOP} y2={TOP + plotH} stroke="#E4DCC8" strokeWidth={t === 0 ? 1.5 : 1} />
                <text x={hx(t)} y={TOP + plotH + 16} textAnchor="middle" fontSize={11} className="fill-muted">{axisFormat(t)}</text>
              </g>
            ) : (
              <g key={t}>
                <line x1={left} x2={left + plotW} y1={vy(t)} y2={vy(t)} stroke="#E4DCC8" strokeWidth={t === 0 ? 1.5 : 1} strokeDasharray={t === 0 ? undefined : "3 3"} />
                <text x={left - 8} y={vy(t)} dy="0.32em" textAnchor="end" fontSize={11} className="fill-muted">{axisFormat(t)}</text>
              </g>
            ),
          )}

          {/* active band highlight */}
          {active !== null && (horizontal
            ? <rect x={left} y={TOP + active * band} width={plotW} height={band} fill="#E4DCC8" opacity={0.35} />
            : <rect x={left + active * band} y={TOP} width={band} height={plotH} fill="#E4DCC8" opacity={0.35} />)}

          {/* bars */}
          {bars.map((b) => <rect key={b.key} x={b.x} y={b.y} width={b.w} height={b.h} rx={2} fill={b.color} />)}

          {/* category labels */}
          {categories.map((c, i) => {
            if (!horizontal && i % stride !== 0) return null;
            const maxChars = Math.floor((left - 12) / CHAR_PX);
            const text = horizontal && c.length > maxChars ? `${c.slice(0, Math.max(1, maxChars - 1))}…` : c;
            return horizontal ? (
              <text key={i} x={left - 8} y={TOP + i * band + band / 2} dy="0.32em" textAnchor="end" fontSize={11.5} className="fill-ink">
                <title>{c}</title>{text}
              </text>
            ) : (
              <text key={i} x={left + i * band + band / 2} y={TOP + plotH + 18} textAnchor="middle" fontSize={11.5} className="fill-muted">{text}</text>
            );
          })}

          {/* hover/touch targets */}
          {categories.map((_, i) => (
            <rect
              key={i} fill="transparent"
              x={horizontal ? left : left + i * band} y={horizontal ? TOP + i * band : TOP}
              width={horizontal ? plotW : band} height={horizontal ? band : plotH}
              onMouseEnter={() => setActive(i)} onMouseMove={() => setActive(i)} onTouchStart={() => setActive(i)}
            />
          ))}
          <line x1={horizontal ? zero : left} x2={horizontal ? zero : left + plotW} y1={horizontal ? TOP : zero} y2={horizontal ? TOP + plotH : zero} stroke="#8A8578" strokeWidth={0.5} />
        </svg>

        {active !== null && (
          <ChartTooltip
            x={tipX} y={tipY} containerWidth={width}
            title={tooltipTitles?.[active] ?? categories[active]}
            rows={series.map((s) => ({ name: s.name, color: s.color, value: format(s.values[active] ?? 0) }))}
          />
        )}
      </div>

      <DataTable
        caption={ariaLabel}
        headers={["Category", ...series.map((s) => s.name)]}
        rows={categories.map((c, i) => [tooltipTitles?.[i] ?? c, ...series.map((s) => format(s.values[i] ?? 0))])}
      />
    </div>
  );
}

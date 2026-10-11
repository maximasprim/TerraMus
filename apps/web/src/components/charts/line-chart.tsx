"use client";

import { useState, type KeyboardEvent, type MouseEvent } from "react";
import { ChartLegend, ChartTooltip, DataTable } from "./chart-parts";
import { compactNumber, count } from "./format";
import { labelStride, niceScale } from "./scale";
import { useElementWidth } from "./use-element-width";

export interface LineSeries {
  name: string;
  color: string;
  values: number[];
  /** Soft fill down to the zero line. */
  area?: boolean;
  dashed?: boolean;
}

const TOP = 12;
const RIGHT = 14;
const BOTTOM = 28;
const CHAR_PX = 6.3;
/** Points are inset from the plot edges so the first/last dot and their x labels are never clipped. */
const INSET = 16;

/** Line / area chart over an ordered category axis (months, days). Negative values supported. */
export function LineChart({
  categories, series, format = count, axisFormat = compactNumber, height = 240, ariaLabel, tooltipTitles, showLegend,
}: {
  categories: string[];
  series: LineSeries[];
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
  if (n === 0 || series.length === 0) return <p className="py-8 text-center text-sm text-muted">No data yet.</p>;

  const all = series.flatMap((s) => s.values);
  const scale = niceScale(Math.min(0, ...all), Math.max(0, ...all), 4);
  const span = scale.max - scale.min || 1;

  const longestTick = Math.max(...scale.ticks.map((t) => axisFormat(t).length));
  const left = Math.max(36, longestTick * CHAR_PX + 12);
  const plotW = Math.max(40, width - left - RIGHT);
  const plotH = height - TOP - BOTTOM;
  const step = n > 1 ? (plotW - 2 * INSET) / (n - 1) : 0;
  const px = (i: number) => (n === 1 ? left + plotW / 2 : left + INSET + i * step);
  const py = (v: number) => TOP + plotH * (1 - (v - scale.min) / span);
  const stride = labelStride(n, n > 1 ? step : plotW, Math.max(...categories.map((c) => c.length)));

  const indexAt = (e: MouseEvent<SVGRectElement>) => {
    if (n === 1) return 0;
    const rect = e.currentTarget.getBoundingClientRect();
    const usable = (rect.width || 1) - 2 * INSET;
    const rel = (e.clientX - rect.left - INSET) / (usable > 0 ? usable : 1);
    return Math.max(0, Math.min(n - 1, Math.round(rel * (n - 1))));
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowRight") { e.preventDefault(); setActive((a) => (a === null ? 0 : Math.min(n - 1, a + 1))); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); setActive((a) => (a === null ? n - 1 : Math.max(0, a - 1))); }
    else if (e.key === "Home") { e.preventDefault(); setActive(0); }
    else if (e.key === "End") { e.preventDefault(); setActive(n - 1); }
    else if (e.key === "Escape") setActive(null);
  };

  const pathFor = (values: number[]) => values.map((v, i) => `${i === 0 ? "M" : "L"}${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(" ");
  const areaFor = (values: number[]) =>
    `${pathFor(values)} L${px(n - 1).toFixed(1)},${py(0).toFixed(1)} L${px(0).toFixed(1)},${py(0).toFixed(1)} Z`;
  const dots = n <= 14;

  return (
    <div ref={ref} className="relative w-full">
      {(showLegend ?? series.length > 1) && <ChartLegend items={series.map((s) => ({ name: s.name, color: s.color }))} />}
      <div className="relative">
        <svg
          width={width} height={height} role="img" aria-label={ariaLabel} tabIndex={0}
          onKeyDown={onKey} onBlur={() => setActive(null)} onMouseLeave={() => setActive(null)}
          className="block overflow-visible rounded outline-none focus-visible:ring-2 focus-visible:ring-brass"
        >
          {scale.ticks.map((t) => (
            <g key={t}>
              <line x1={left} x2={left + plotW} y1={py(t)} y2={py(t)} stroke="#E4DCC8" strokeWidth={t === 0 ? 1.5 : 1} strokeDasharray={t === 0 ? undefined : "3 3"} />
              <text x={left - 8} y={py(t)} dy="0.32em" textAnchor="end" fontSize={11} className="fill-muted">{axisFormat(t)}</text>
            </g>
          ))}

          {categories.map((c, i) => i % stride === 0 && (
            <text key={i} x={px(i)} y={TOP + plotH + 18} textAnchor="middle" fontSize={11.5} className="fill-muted">{c}</text>
          ))}

          {series.map((s) => s.area && <path key={`${s.name}-area`} d={areaFor(s.values)} fill={s.color} opacity={0.12} />)}
          {series.map((s) => (
            <path key={s.name} d={pathFor(s.values)} fill="none" stroke={s.color} strokeWidth={2.25} strokeLinejoin="round" strokeLinecap="round" strokeDasharray={s.dashed ? "5 4" : undefined} />
          ))}
          {dots && series.map((s) => s.values.map((v, i) => <circle key={`${s.name}-${i}`} cx={px(i)} cy={py(v)} r={3} fill={s.color} />))}

          {active !== null && (
            <g>
              <line x1={px(active)} x2={px(active)} y1={TOP} y2={TOP + plotH} stroke="#8A8578" strokeWidth={1} strokeDasharray="3 3" />
              {series.map((s) => <circle key={s.name} cx={px(active)} cy={py(s.values[active] ?? 0)} r={5} fill="#F7F3EA" stroke={s.color} strokeWidth={2.5} />)}
            </g>
          )}

          <rect
            x={left} y={TOP} width={plotW} height={plotH} fill="transparent"
            onMouseMove={(e) => setActive(indexAt(e))} onMouseEnter={(e) => setActive(indexAt(e))} onTouchStart={() => setActive(Math.floor(n / 2))}
          />
        </svg>

        {active !== null && (
          <ChartTooltip
            x={px(active)} containerWidth={width} title={tooltipTitles?.[active] ?? categories[active]}
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

"use client";

import { useMemo, useState } from "react";
import { clsx } from "clsx";
import { DataTable } from "./chart-parts";
import { colorAt, OTHER_COLOR } from "./palette";
import { count, percent } from "./format";
import { groupSmallSlices, type Slice } from "./scale";

const SIZE = 168;
const RADIUS = 62;
const STROKE = 22;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/**
 * Donut (pie) chart with a legend. Each slice is a stroked circle arc, which
 * stays correct for one slice, tiny slices and a full ring - the cases that
 * break hand-rolled arc paths. Hover/focus a slice or a legend row to read it.
 */
export function DonutChart({
  data, format = count, centerLabel = "Total", centerValue, ariaLabel, maxSlices = 7, colors,
}: {
  data: Slice[];
  format?: (n: number) => string;
  centerLabel?: string;
  centerValue?: string;
  ariaLabel: string;
  maxSlices?: number;
  /** Fixed colour per label (e.g. status names), so a status keeps its colour across charts. */
  colors?: Record<string, string>;
}) {
  const [active, setActive] = useState<number | null>(null);

  const slices = useMemo(
    () => groupSmallSlices(data, maxSlices).map((d, i) => ({
      ...d,
      color: d.label === "Other" ? OTHER_COLOR : d.color ?? colors?.[d.label] ?? colorAt(i),
    })),
    [data, maxSlices, colors],
  );
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  if (total <= 0) return <p className="py-8 text-center text-sm text-muted">No data yet.</p>;

  const gap = slices.length > 1 ? 1.5 : 0;
  let consumed = 0;
  const arcs = slices.map((slice) => {
    const length = (slice.value / total) * CIRCUMFERENCE;
    const arc = { dash: Math.max(0.5, length - gap), offset: -consumed };
    consumed += length;
    return arc;
  });
  const focused = active !== null ? slices[active] : null;

  return (
    <div className="flex flex-col items-center gap-5 sm:flex-row">
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} role="group" aria-label={ariaLabel} className="shrink-0 overflow-visible">
        <g transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}>
          {slices.map((slice, i) => (
            <circle
              key={slice.label}
              cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} fill="none"
              stroke={slice.color}
              strokeWidth={active === i ? STROKE + 5 : STROKE}
              strokeDasharray={`${arcs[i].dash} ${CIRCUMFERENCE}`}
              strokeDashoffset={arcs[i].offset}
              opacity={active === null || active === i ? 1 : 0.35}
              tabIndex={0}
              role="img"
              aria-label={`${slice.label}: ${format(slice.value)} (${percent(slice.value, total)})`}
              onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(i)} onBlur={() => setActive(null)}
              style={{ transition: "stroke-width 120ms, opacity 120ms", outline: "none", cursor: "default" }}
            />
          ))}
        </g>
        <text x="50%" y="46%" textAnchor="middle" className="fill-forest font-display" fontSize={focused ? 17 : 20}>
          {focused ? format(focused.value) : centerValue ?? format(total)}
        </text>
        <text x="50%" y="46%" dy="1.45em" textAnchor="middle" className="fill-muted" fontSize={10.5}>
          {focused ? `${focused.label} · ${percent(focused.value, total)}` : centerLabel}
        </text>
      </svg>

      <ul className="w-full min-w-0 flex-1 space-y-1">
        {slices.map((slice, i) => (
          <li
            key={slice.label}
            tabIndex={-1}
            onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)}
            className={clsx("flex items-center justify-between gap-3 rounded px-2 py-1 text-sm", active === i && "bg-hairline/50")}
          >
            <span className="flex min-w-0 items-center gap-2">
              <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: slice.color }} />
              <span className="truncate text-ink" title={slice.label}>{slice.label}</span>
            </span>
            <span className="shrink-0 tabular-nums text-muted">
              <span className="text-ink">{format(slice.value)}</span> · {percent(slice.value, total)}
            </span>
          </li>
        ))}
      </ul>

      <DataTable
        caption={ariaLabel}
        headers={["Category", "Value", "Share"]}
        rows={slices.map((s) => [s.label, format(s.value), percent(s.value, total)])}
      />
    </div>
  );
}

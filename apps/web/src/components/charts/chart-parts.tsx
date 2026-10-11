import type { ReactNode } from "react";
import { clsx } from "clsx";
import { Card } from "@/components/ui";

export interface TooltipRow {
  name: string;
  color: string;
  value: string;
}

/** Floating readout. Positioned in the chart container's pixel space; never intercepts the pointer. */
export function ChartTooltip({
  x, y = 0, containerWidth, title, rows,
}: { x: number; y?: number; containerWidth: number; title: string; rows: TooltipRow[] }) {
  const half = 84; // keeps the box inside the container at either edge
  const left = Math.min(Math.max(x, half), Math.max(half, containerWidth - half));
  return (
    <div
      role="status"
      className="pointer-events-none absolute z-10 min-w-[8rem] -translate-x-1/2 rounded-md bg-ink px-3 py-2 text-xs text-paper shadow-lg"
      style={{ left, top: y }}
    >
      <p className="mb-1 font-medium">{title}</p>
      {rows.map((row) => (
        <p key={row.name} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-sm" style={{ background: row.color }} />
            {row.name}
          </span>
          <span className="font-medium tabular-nums">{row.value}</span>
        </p>
      ))}
    </div>
  );
}

export function ChartLegend({ items }: { items: { name: string; color: string }[] }) {
  return (
    <ul className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
      {items.map((item) => (
        <li key={item.name} className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: item.color }} />
          {item.name}
        </li>
      ))}
    </ul>
  );
}

/** Card chrome shared by every chart: title, optional subtitle/actions, and an honest empty state. */
export function ChartCard({
  title, subtitle, actions, empty, emptyText = "Nothing to show for this period yet.", children, className,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  empty?: boolean;
  emptyText?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={clsx("flex flex-col", className)}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-lg text-forest">{title}</h3>
          {subtitle && <p className="text-xs text-muted">{subtitle}</p>}
        </div>
        {actions}
      </div>
      {empty ? (
        <div className="flex flex-1 items-center justify-center rounded-md border border-dashed border-hairline py-10 text-center text-sm text-muted">
          {emptyText}
        </div>
      ) : (
        children
      )}
    </Card>
  );
}

/** Screen-reader equivalent of a chart: the same numbers as a table. */
export function DataTable({
  caption, headers, rows,
}: { caption: string; headers: string[]; rows: (string | number)[][] }) {
  return (
    <table className="sr-only">
      <caption>{caption}</caption>
      <thead>
        <tr>{headers.map((h) => <th key={h} scope="col">{h}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i}>{row.map((cell, j) => (j === 0 ? <th key={j} scope="row">{cell}</th> : <td key={j}>{cell}</td>))}</tr>
        ))}
      </tbody>
    </table>
  );
}

/** Number, money, date and label helpers shared by every chart and report. */

export function toNumber(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === "") return 0;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

/** 1234 -> "1.2K", 2_500_000 -> "2.5M". For axis ticks and tight spaces. */
export function compactNumber(n: number): string {
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  const trim = (v: number) => String(Number(v.toFixed(1)));
  if (abs >= 1_000_000_000) return `${sign}${trim(abs / 1_000_000_000)}B`;
  if (abs >= 1_000_000) return `${sign}${trim(abs / 1_000_000)}M`;
  if (abs >= 1_000) return `${sign}${trim(abs / 1_000)}K`;
  return `${sign}${trim(abs)}`;
}

export const kes = (n: number): string =>
  `KES ${Math.round(n).toLocaleString("en-US")}`;

export const count = (n: number): string => n.toLocaleString("en-US");

export const liters = (n: number): string =>
  `${n.toLocaleString("en-US", { maximumFractionDigits: 1 })} L`;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-05" -> "May" (or "May 26" with the year). Pure string maths - no Date, so no timezone drift. */
export function monthLabel(key: string, withYear = false): string {
  const [y, m] = key.split("-");
  const name = MONTHS[Number(m) - 1] ?? key;
  return withYear ? `${name} ${y.slice(2)}` : name;
}

/** Month labels that add the year only where it changes (first label and each January). */
export function monthLabels(keys: string[]): string[] {
  return keys.map((k, i) => {
    const showYear = i === 0 || k.endsWith("-01");
    return monthLabel(k, showYear);
  });
}

/** "2026-10-09" -> "9 Oct". */
export function dayLabel(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${Number(d)} ${MONTHS[Number(m) - 1] ?? ""}`.trim();
}

/** "milk_sale" -> "Milk sale"; "ready_for_harvest" -> "Ready for harvest". */
export function humanize(code: string): string {
  const spaced = code.replace(/_/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function percent(part: number, total: number): string {
  if (total <= 0) return "0%";
  const p = (part / total) * 100;
  return `${p >= 10 || p === 0 ? Math.round(p) : p.toFixed(1)}%`;
}

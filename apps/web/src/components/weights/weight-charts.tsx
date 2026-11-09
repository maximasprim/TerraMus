"use client";

import { useElementWidth } from "@/components/charts/use-element-width";
import { BAND_COLOR, BAND_LABEL, shortDate, type AnimalWeights, type Band } from "@/lib/weights-types";

const DAY = 86_400_000;

/** Round tick values that cover [min, max]: a weight axis that starts near the data, not at zero. */
function niceTicks(min: number, max: number, count = 4): number[] {
  const span = max - min || 1;
  const raw = span / count, mag = 10 ** Math.floor(Math.log10(raw)), norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
  const out: number[] = [];
  for (let v = Math.floor(min / step) * step; v < max + step - 1e-9; v += step) out.push(Math.round(v * 100) / 100);
  return out;
}
const t = (iso: string) => new Date(`${iso}T00:00:00`).getTime();

/** Weight over time with the target line, the projection to the target, and the batch-mates' average.
 * The horizontal axis is real time, so a long gap between weighings looks like a long gap. */
export function WeightProgressChart({ data, height = 260 }: { data: AnimalWeights; height?: number }) {
  const [ref, width] = useElementWidth();
  const pts = data.series;
  const target = data.animal.target_kg;
  if (pts.length === 0) return <p className="py-8 text-center text-sm text-muted">No weights recorded yet.</p>;

  const proj = data.projection;
  const plan = data.plan && data.plan.length === 2 ? data.plan : null;
  const xs = [...pts.map((p) => t(p.date)), ...(proj ? proj.map((p) => t(p.date)) : []), ...(plan ? plan.map((p) => t(p.date)) : [])];
  let x0 = Math.min(...xs), x1 = Math.max(...xs);
  if (x1 === x0) x1 = x0 + 7 * DAY;
  const vals = [...pts.map((p) => p.weight_kg), ...data.batch_avg.map((b) => b.avg_kg), ...(target ? [target] : []), ...(plan ? plan.map((p) => p.weight_kg) : [])];
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = Math.max(3, (hi - lo) * 0.1);
  const ticks = niceTicks(Math.max(0, lo - pad), hi + pad, 4);
  const yMin = ticks[0], yMax = ticks[ticks.length - 1];

  const LEFT = 44, RIGHT = 16, TOP = 14, BOTTOM = 30;
  const w = Math.max(220, width), plotW = w - LEFT - RIGHT, plotH = height - TOP - BOTTOM;
  const px = (ms: number) => LEFT + ((ms - x0) / (x1 - x0)) * plotW;
  const py = (v: number) => TOP + plotH * (1 - (v - yMin) / (yMax - yMin || 1));
  const line = (arr: { x: number; y: number }[]) => arr.map((p, i) => `${i ? "L" : "M"}${px(p.x).toFixed(1)},${py(p.y).toFixed(1)}`).join(" ");
  const xLabels = [x0, x0 + (x1 - x0) / 2, x1].map((ms) => new Date(ms).toISOString().slice(0, 10));
  const hasBatch = data.batch_avg.length > 0;

  return (
    <div ref={ref} className="w-full">
      <svg width={w} height={height} role="img" aria-label={`Weight of ${data.animal.tag} over time${target ? `, target ${target} kg` : ""}`}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={LEFT} x2={w - RIGHT} y1={py(v)} y2={py(v)} stroke="#E6DFD2" strokeWidth={1} />
            <text x={LEFT - 6} y={py(v) + 4} textAnchor="end" fontSize={11} fill="#8A8578">{v}</text>
          </g>
        ))}
        {xLabels.map((d, i) => (
          <text key={d + i} x={px(t(d))} y={height - 8} textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"} fontSize={11} fill="#8A8578">{shortDate(d)}</text>
        ))}
        {target ? (
          <g>
            <line x1={LEFT} x2={w - RIGHT} y1={py(target)} y2={py(target)} stroke="#B8862B" strokeWidth={1.5} strokeDasharray="6 4" />
            <text x={w - RIGHT} y={py(target) - 5} textAnchor="end" fontSize={11} fill="#8a6a1f">Target {target} kg</text>
          </g>
        ) : null}
        {plan && (
          <g>
            <path d={line(plan.map((p) => ({ x: t(p.date), y: p.weight_kg })))} fill="none" stroke="#7B6BA8" strokeWidth={1.5} strokeDasharray="8 3 2 3" />
            <text x={px(t(plan[1].date))} y={py(plan[1].weight_kg) + 14} textAnchor="end" fontSize={11} fill="#5d4f8a">Target day {shortDate(plan[1].date)}</text>
          </g>
        )}
        {hasBatch && (
          <path d={line(data.batch_avg.map((b) => ({ x: t(b.date), y: b.avg_kg })))} fill="none" stroke="#6F9A7B" strokeWidth={1.5} strokeDasharray="2 4" />
        )}
        {proj && proj.length === 2 && (
          <path d={line(proj.map((p) => ({ x: t(p.date), y: p.weight_kg })))} fill="none" stroke="#B8862B" strokeWidth={2} strokeDasharray="5 4" />
        )}
        <path d={line(pts.map((p) => ({ x: t(p.date), y: p.weight_kg })))} fill="none" stroke="#2C4F3E" strokeWidth={2.5} strokeLinejoin="round" />
        {pts.map((p) => (
          <circle key={p.date} cx={px(t(p.date))} cy={py(p.weight_kg)} r={3.5} fill="#2C4F3E" stroke="#fff" strokeWidth={1.5}>
            <title>{`${shortDate(p.date)}: ${p.weight_kg} kg${p.adg != null ? ` (${p.adg.toFixed(2)} kg/day)` : ""}`}</title>
          </circle>
        ))}
      </svg>
      <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <li><span className="mr-1 inline-block h-0.5 w-4 bg-forest-light align-middle" style={{ backgroundColor: "#2C4F3E" }} />Weight</li>
        {target ? <li><span className="mr-1 inline-block w-4 border-t-2 border-dashed align-middle" style={{ borderColor: "#B8862B" }} />Target</li> : null}
        {plan ? <li><span className="mr-1 inline-block w-4 border-t-2 border-dashed align-middle" style={{ borderColor: "#7B6BA8" }} />Plan to reach the target on the target day</li> : null}
        {proj ? <li><span className="mr-1 inline-block w-4 border-t-2 border-dashed align-middle" style={{ borderColor: "#B8862B" }} />Projected</li> : null}
        {hasBatch && <li><span className="mr-1 inline-block w-4 border-t-2 border-dotted align-middle" style={{ borderColor: "#6F9A7B" }} />Batch average (others)</li>}
      </ul>
    </div>
  );
}

/** Daily gain between each pair of weighings, coloured by performance band, with the band lines. */
export function AdgBarsChart({ data, height = 200 }: { data: AnimalWeights; height?: number }) {
  const [ref, width] = useElementWidth();
  const bars = data.series.filter((p) => p.adg != null);
  if (bars.length === 0) return <p className="py-6 text-center text-sm text-muted">Needs at least two weighings on different days.</p>;
  const { approaching_from: lowLine, on_target_from: midLine, excellent_above: highLine } = data.thresholds;
  const vals = bars.map((b) => b.adg as number);
  const lo = Math.min(0, ...vals), hi = Math.max(highLine, ...vals) * 1.1;
  const LEFT = 36, RIGHT = 12, TOP = 12, BOTTOM = 28;
  const w = Math.max(220, width), plotW = w - LEFT - RIGHT, plotH = height - TOP - BOTTOM;
  const py = (v: number) => TOP + plotH * (1 - (v - lo) / (hi - lo || 1));
  const slot = plotW / bars.length, bw = Math.min(40, slot * 0.6);
  const strideN = Math.max(1, Math.ceil(bars.length / Math.max(1, Math.floor(plotW / 52))));
  const used = new Set<Band>(bars.map((b) => b.band as Band));
  const gridTicks = [0, lowLine, midLine, highLine].filter((v) => v >= lo && v <= hi);
  return (
    <div ref={ref} className="w-full">
      <svg width={w} height={height} role="img" aria-label="Daily gain between weighings">
        {gridTicks.map((v) => (
          <g key={v}>
            <line x1={LEFT} x2={w - RIGHT} y1={py(v)} y2={py(v)} stroke={v === 0 ? "#B7A99A" : "#B8862B"} strokeWidth={1} strokeDasharray={v === 0 ? undefined : "4 4"} />
            <text x={LEFT - 5} y={py(v) + 4} textAnchor="end" fontSize={11} fill="#8A8578">{v}</text>
          </g>
        ))}
        {bars.map((b, i) => {
          const v = b.adg as number, cx = LEFT + slot * i + slot / 2;
          const y = py(Math.max(v, 0)), h = Math.max(2, Math.abs(py(v) - py(0)));
          return (
            <g key={b.date}>
              <rect x={cx - bw / 2} y={v >= 0 ? y : py(0)} width={bw} height={h} rx={2} fill={BAND_COLOR[b.band as Band]}>
                <title>{`${shortDate(b.date)}: ${v.toFixed(2)} kg/day (${BAND_LABEL[b.band as Band]})`}</title>
              </rect>
              {bars.length <= 12 && <text x={cx} y={(v >= 0 ? y : py(v)) - 4} textAnchor="middle" fontSize={10} fill="#4a463d">{v.toFixed(2)}</text>}
              {i % strideN === 0 && <text x={cx} y={height - 8} textAnchor="middle" fontSize={10.5} fill="#8A8578">{shortDate(b.date)}</text>}
            </g>
          );
        })}
      </svg>
      <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {(["excellent", "on_target", "approaching_target", "below_target"] as Band[]).filter((b) => used.has(b)).map((b) => (
          <li key={b}><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm align-middle" style={{ backgroundColor: BAND_COLOR[b] }} />
            {BAND_LABEL[b]}{b === "excellent" ? ` (above ${highLine})` : b === "on_target" ? ` (${midLine}–${highLine})` : b === "approaching_target" ? ` (${lowLine}–${midLine})` : ` (below ${lowLine})`}</li>
        ))}
      </ul>
    </div>
  );
}

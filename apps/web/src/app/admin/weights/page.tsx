"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Button, Card, EmptyState, ErrorState, Input, Modal, Select, StatCard } from "@/components/ui";
import { downloadCsv } from "@/components/charts";
import { AnimalPerformance } from "@/components/weights/animal-performance";
import { apiFetch, ApiError } from "@/lib/api";
import { useCan } from "@/lib/use-auth";
import { filterWeightRows, NO_WEIGHT_FILTERS, sortWeightRows, type WeightFilters, type WeightSortKey } from "@/lib/weights-view";
import {
  adgText, BAND_CHIP, BAND_LABEL, fullDate, kg, shortDate, STAGE_CHIP, STAGE_LABEL,
  type DailyWeights, type Stage, type WeightRow, type WeightsOverview,
} from "@/lib/weights-types";

type Tab = "readiness" | "daily" | "batches";
const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

export default function WeightsPage() {
  const [tab, setTab] = useState<Tab>("readiness");
  const ov = useQuery<WeightsOverview>({ queryKey: ["weights", "overview"], queryFn: () => apiFetch<WeightsOverview>("/api/v1/weights/overview") });
  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl text-forest">Weights</h1>
        <p className="text-sm text-muted">How every animal is gaining, how far it is from its target weight, and which ones are ready for market.</p>
      </div>
      <div className="mb-6 flex flex-wrap gap-2 border-b border-hairline">
        {([["readiness", "Readiness"], ["daily", "Daily weights"], ["batches", "Batches"]] as [Tab, string][]).map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${tab === k ? "border-forest text-forest" : "border-transparent text-muted hover:text-ink"}`}>{label}</button>
        ))}
      </div>
      {ov.error ? <ErrorState message={errMsg(ov.error, "Could not load the weights report")} /> : ov.isLoading || !ov.data ? <p className="text-sm text-muted">Loading…</p> : (
        <>
          {tab === "readiness" && <Readiness data={ov.data} />}
          {tab === "daily" && <Daily />}
          {tab === "batches" && <Batches data={ov.data} />}
        </>
      )}
    </AdminShell>
  );
}

function StageChip({ r }: { r: Pick<WeightRow, "stage" | "hold_reason"> }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <span className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${STAGE_CHIP[r.stage]}`}>{STAGE_LABEL[r.stage]}</span>
      {r.hold_reason && <span className="whitespace-nowrap rounded-full bg-clay/15 px-2 py-0.5 text-xs text-clay" title="Held back from alerts until healthy">{r.hold_reason}</span>}
    </span>
  );
}

function Progress({ pct }: { pct: number | null }) {
  if (pct == null) return <span className="text-muted">-</span>;
  return (
    <div className="flex items-center gap-2" aria-label={`${pct.toFixed(0)}% of target`}>
      <div className="h-2 w-20 overflow-hidden rounded-full bg-hairline"><div className="h-full rounded-full bg-forest" style={{ width: `${pct}%` }} /></div>
      <span className="text-xs text-muted">{pct.toFixed(0)}%</span>
    </div>
  );
}

function AdgCell({ r }: { r: Pick<WeightRow, "adg" | "adg_band"> }) {
  if (r.adg == null) return <span className="text-muted">-</span>;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <span className="whitespace-nowrap">{r.adg.toFixed(2)}</span>
      {r.adg_band && <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs ${BAND_CHIP[r.adg_band]}`}>{BAND_LABEL[r.adg_band]}</span>}
    </span>
  );
}

// ------------------------------------------------------------------ readiness
function Readiness({ data }: { data: WeightsOverview }) {
  const [f, setF] = useState<WeightFilters>(NO_WEIGHT_FILTERS);
  const [sort, setSort] = useState<{ key: WeightSortKey; dir: "asc" | "desc" }>({ key: "ready", dir: "asc" });
  const [open, setOpen] = useState<WeightRow | null>(null);
  const s = data.summary;
  const rows = useMemo(() => sortWeightRows(filterWeightRows(data.animals, f), sort.key, sort.dir), [data.animals, f, sort]);
  const th = (key: WeightSortKey, label: string) => (
    <th className="pb-2 pr-3 font-medium">
      <button type="button" className="inline-flex items-center gap-1 hover:text-ink" onClick={() => setSort((p) => ({ key, dir: p.key === key && p.dir === "asc" ? "desc" : "asc" }))}>
        {label}<span aria-hidden className="text-[10px]">{sort.key === key ? (sort.dir === "asc" ? "▲" : "▼") : ""}</span>
      </button>
    </th>
  );
  if (s.head === 0) return <EmptyState title="No animals to track yet" body="Animals on the farm appear here once they are registered and weighed." />;
  const withTarget = s.head - (s.stages.no_target ?? 0);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Ready for market" value={String(s.stages.ready ?? 0)} hint={s.ready_on_hold ? `${s.ready_on_hold} on a health hold` : "at or above target weight"} />
        <StatCard label="Nearly ready" value={String(s.stages.nearly_ready ?? 0)} hint={`within ${data.thresholds.nearly_ready_days} days at the current gain`} />
        <StatCard label="Average daily gain" value={s.avg_adg == null ? "-" : s.avg_adg.toFixed(2)} hint={`${s.bands.below_target ?? 0} below ${data.thresholds.approaching_from} kg/day`} />
        <StatCard label="With a target" value={`${withTarget} / ${s.head}`} hint="set targets on the Batches tab" />
      </div>

      <Card className="p-4 sm:p-6">
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <div className="min-w-[12rem] flex-1"><Input id="w-search" aria-label="Search animals" placeholder="Search tag, name, breed, batch…" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} /></div>
          <Select aria-label="Filter by stage" value={f.stage} onChange={(e) => setF({ ...f, stage: e.target.value as Stage | "" })}>
            <option value="">All stages</option>
            {(Object.keys(STAGE_LABEL) as Stage[]).map((k) => <option key={k} value={k}>{STAGE_LABEL[k]}</option>)}
          </Select>
          <Select aria-label="Filter by batch" value={f.batch} onChange={(e) => setF({ ...f, batch: e.target.value })}>
            <option value="">All batches</option><option value="none">No batch</option>
            {data.batch_options.map((b) => <option key={b.id} value={b.id}>{b.label}</option>)}
          </Select>
          <Button variant="ghost" onClick={() => downloadCsv("weights-readiness.csv", [
            ["Tag", "Batch", "Latest kg", "Last weighed", "Target kg", "Remaining kg", "Progress %", "Daily gain", "Band", "Expected ready", "Stage"],
            ...rows.map((r) => [r.tag, r.batch ?? "", r.current_kg ?? "", r.last_weighed ?? "", r.target_kg ?? "", r.remaining_kg ?? "", r.progress_pct ?? "", r.adg ?? "",
              r.adg_band ? BAND_LABEL[r.adg_band] : "", r.est_ready_date ?? "", STAGE_LABEL[r.stage] + (r.hold_reason ? ` (${r.hold_reason})` : "")]),
          ])}>Download CSV</Button>
        </div>
        {rows.length === 0 ? <p className="py-8 text-center text-sm text-muted">No animals match.</p> : (
          <>
            {/* phones: one card per animal */}
            <ul className="divide-y divide-hairline/60 md:hidden">
              {rows.map((r) => (
                <li key={r.id}>
                  <button type="button" onClick={() => setOpen(r)} className="block w-full py-3 text-left">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="font-medium text-ink">{r.tag}</span><span className="text-lg font-medium text-ink">{kg(r.current_kg)}</span>
                    </div>
                    <div className="mt-0.5 flex items-center justify-between gap-3 text-xs text-muted">
                      <span>{r.batch ?? "No batch"}</span><span>{r.target_kg ? `target ${kg(r.target_kg, 0)}` : "no target"}</span>
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2"><StageChip r={r} /><AdgCell r={r} /></div>
                    {r.progress_pct != null && <div className="mt-2"><Progress pct={r.progress_pct} /></div>}
                    {r.stage === "growing" || r.stage === "nearly_ready" ? <p className="mt-1 text-xs text-muted">Expected ready {shortDate(r.est_ready_date)}</p> : null}
                  </button>
                </li>
              ))}
            </ul>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-left text-sm">
                <thead><tr className="border-b border-hairline text-xs uppercase tracking-wider text-muted">
                  {th("tag", "Animal")}{th("weight", "Weight")}<th className="pb-2 pr-3 font-medium">Target</th>{th("progress", "Progress")}{th("adg", "Daily gain (kg)")}{th("ready", "Expected ready")}<th className="pb-2 font-medium">Status</th>
                </tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} onClick={() => setOpen(r)} className="cursor-pointer border-b border-hairline/60 last:border-0 hover:bg-hairline/30">
                      <td className="py-2 pr-3"><button type="button" className="font-medium text-forest hover:underline" onClick={(e) => { e.stopPropagation(); setOpen(r); }}>{r.tag}</button>
                        <div className="text-xs text-muted">{r.batch ?? "No batch"}</div></td>
                      <td className="whitespace-nowrap py-2 pr-3"><span className="font-medium text-ink">{kg(r.current_kg)}</span><div className="text-xs text-muted">{r.last_weighed ? shortDate(r.last_weighed) : "never weighed"}</div></td>
                      <td className="whitespace-nowrap py-2 pr-3">{r.target_kg ? <>{kg(r.target_kg, 0)}<div className="text-xs text-muted">{r.target_source === "animal" ? "own target" : "batch target"}</div></> : <span className="text-muted">-</span>}</td>
                      <td className="py-2 pr-3"><Progress pct={r.progress_pct} /></td>
                      <td className="py-2 pr-3"><AdgCell r={r} /></td>
                      <td className="whitespace-nowrap py-2 pr-3">{r.stage === "ready" ? "Now" : r.est_ready_date ? <>{shortDate(r.est_ready_date)}<div className="text-xs text-muted">{r.days_to_ready === 0 ? "any day now" : `~${r.days_to_ready} days`}</div></> : <span className="text-muted">-</span>}</td>
                      <td className="py-2"><StageChip r={r} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        <p className="mt-4 text-xs text-muted">
          Daily gain: above {data.thresholds.excellent_above} kg/day is excellent, {data.thresholds.on_target_from}–{data.thresholds.excellent_above} is on target, {data.thresholds.approaching_from}–{data.thresholds.on_target_from} is approaching target, below {data.thresholds.approaching_from} is below target.
          “Nearly ready” means the recent gain (last {data.thresholds.recent_window_days} days) reaches the target within {data.thresholds.nearly_ready_days} days. Animals that are not healthy are shown but held back from alerts.
        </p>
      </Card>

      <Modal open={!!open} onClose={() => setOpen(null)} title={open ? `${open.tag}${open.name ? ` · ${open.name}` : ""}` : ""} size="lg">
        {open && <AnimalPerformance animalId={open.id} showLink />}
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ daily weights
function Daily() {
  const [day, setDay] = useState<string>("");
  const q = useQuery<DailyWeights>({ queryKey: ["weights", "daily", day], queryFn: () => apiFetch<DailyWeights>(`/api/v1/weights/daily${day ? `?day=${day}` : ""}`) });
  const [open, setOpen] = useState<string | null>(null);
  if (q.error) return <ErrorState message={errMsg(q.error, "Could not load daily weights")} />;
  if (q.isLoading || !q.data) return <p className="text-sm text-muted">Loading…</p>;
  const d = q.data;
  if (!d.day) return <EmptyState title="No weights recorded yet" body="Weigh-day entries and single weights show up here, one day at a time." />;
  const avg = d.rows.length ? d.rows.reduce((t, r) => t + r.weight_kg, 0) / d.rows.length : null;
  const gains = d.rows.filter((r) => r.adg != null);
  return (
    <Card className="p-4 sm:p-6">
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="min-w-[14rem]">
          <Select label="Day" value={d.day} onChange={(e) => setDay(e.target.value)}>
            {d.days.map((x) => <option key={x.date} value={x.date}>{fullDate(x.date)} · {x.head} animal{x.head === 1 ? "" : "s"}</option>)}
          </Select>
        </div>
        <p className="pb-2 text-sm text-muted">{d.rows.length} weighed{avg != null ? ` · average ${kg(avg)}` : ""}{gains.length ? ` · average gain ${(gains.reduce((t, r) => t + (r.adg as number), 0) / gains.length).toFixed(2)} kg/day` : ""}</p>
        <Button variant="ghost" className="ml-auto" onClick={() => downloadCsv(`weights-${d.day}.csv`, [
          ["Tag", "Batch", "Weight kg", "Previous kg", "Previous date", "Change kg", "Days between", "Daily gain", "Band", "Target kg", "Remaining kg"],
          ...d.rows.map((r) => [r.tag, r.batch ?? "", r.weight_kg, r.previous_kg ?? "", r.previous_date ?? "", r.change_kg ?? "", r.days_between ?? "", r.adg ?? "", r.band ? BAND_LABEL[r.band] : "", r.target_kg ?? "", r.remaining_kg ?? ""]),
        ])}>Download CSV</Button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead><tr className="border-b border-hairline text-xs uppercase tracking-wider text-muted">
            <th className="pb-2 pr-3 font-medium">Animal</th><th className="pb-2 pr-3 font-medium">Weight</th><th className="pb-2 pr-3 font-medium">Previous</th>
            <th className="pb-2 pr-3 font-medium">Change</th><th className="pb-2 pr-3 font-medium">Daily gain (kg)</th><th className="pb-2 font-medium">To target</th></tr></thead>
          <tbody>
            {d.rows.map((r) => (
              <tr key={r.id} className="border-b border-hairline/60 last:border-0">
                <td className="py-2 pr-3"><button type="button" className="font-medium text-forest hover:underline" onClick={() => setOpen(r.id)}>{r.tag}</button><div className="text-xs text-muted">{r.batch ?? ""}</div></td>
                <td className="whitespace-nowrap py-2 pr-3 font-medium text-ink">{kg(r.weight_kg, 2)}</td>
                <td className="whitespace-nowrap py-2 pr-3 text-muted">{r.previous_kg == null ? "first weight" : `${kg(r.previous_kg, 2)} · ${shortDate(r.previous_date)}`}</td>
                <td className="whitespace-nowrap py-2 pr-3">{r.change_kg == null ? "-" : `${r.change_kg > 0 ? "+" : ""}${r.change_kg} kg`}{r.days_between ? <span className="text-xs text-muted"> in {r.days_between}d</span> : null}</td>
                <td className="py-2 pr-3"><AdgCell r={{ adg: r.adg, adg_band: r.band }} /></td>
                <td className="whitespace-nowrap py-2">{r.remaining_kg == null ? <span className="text-muted">no target</span> : r.remaining_kg === 0 ? "Reached" : `${kg(r.remaining_kg)} to go`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Modal open={!!open} onClose={() => setOpen(null)} title="Animal performance" size="lg">{open && <AnimalPerformance animalId={open} showLink />}</Modal>
    </Card>
  );
}

// ------------------------------------------------------------------ batches
function Batches({ data }: { data: WeightsOverview }) {
  const can = useCan();
  const qc = useQueryClient();
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: ({ id, value }: { id: string; value: number | null }) => apiFetch(`/api/v1/weights/batches/${id}/target`, { method: "PUT", body: JSON.stringify({ target_weight_kg: value }) }),
    onSuccess: (_d, v) => { setEdits((p) => { const n = { ...p }; delete n[v.id]; return n; }); setErr(null); void qc.invalidateQueries({ queryKey: ["weights"] }); void qc.invalidateQueries({ queryKey: ["feedlot"] }); },
    onError: (e) => setErr(errMsg(e, "Could not save the target")),
  });
  const targetFor = (id: string) => data.batch_options.find((b) => b.id === id)?.target_weight_kg ?? null;
  return (
    <Card className="p-4 sm:p-6">
      <p className="mb-4 text-sm text-muted">Set the market-ready weight for each intake batch. Every animal in the batch uses it, unless it has its own target (set from the animal’s row on the Readiness tab).</p>
      {err && <div className="mb-3"><ErrorState message={err} /></div>}
      {data.batches.length === 0 ? <p className="text-sm text-muted">No batches yet.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead><tr className="border-b border-hairline text-xs uppercase tracking-wider text-muted">
              <th className="pb-2 pr-3 font-medium">Batch</th><th className="pb-2 pr-3 font-medium">Head</th><th className="pb-2 pr-3 font-medium">Target weight</th>
              <th className="pb-2 pr-3 font-medium">Avg weight</th><th className="pb-2 pr-3 font-medium">Avg daily gain (kg)</th><th className="pb-2 pr-3 font-medium">Progress</th><th className="pb-2 font-medium">Ready / nearly</th></tr></thead>
            <tbody>
              {data.batches.map((b) => {
                const id = b.batch_id;
                const current = id ? targetFor(id) : null;
                const val = id && id in edits ? edits[id] : current != null ? String(current) : "";
                return (
                  <tr key={id ?? "none"} className="border-b border-hairline/60 align-top last:border-0">
                    <td className="py-2 pr-3 font-medium text-ink">{b.batch}</td>
                    <td className="py-2 pr-3">{b.head}</td>
                    <td className="py-2 pr-3">
                      {id && can("weights.targets") ? (
                        <div className="flex items-center gap-2">
                          <input aria-label={`Target weight for ${b.batch}`} type="number" inputMode="decimal" min="1" step="0.5" placeholder="kg" value={val}
                            onChange={(e) => setEdits({ ...edits, [id]: e.target.value })}
                            className="w-24 rounded-md border border-hairline bg-white px-2 py-1.5 text-sm focus:border-brass focus:outline-none" />
                          <Button disabled={save.isPending || !(id in edits)} className="px-3 py-1.5" onClick={() => save.mutate({ id, value: val === "" ? null : Number(val) })}>Save</Button>
                        </div>
                      ) : current != null ? kg(current, 0) : <span className="text-muted">{id ? "not set" : "-"}</span>}
                    </td>
                    <td className="whitespace-nowrap py-2 pr-3">{kg(b.avg_current_kg)}</td>
                    <td className="py-2 pr-3"><AdgCell r={{ adg: b.avg_adg, adg_band: b.adg_band }} /></td>
                    <td className="py-2 pr-3"><Progress pct={b.avg_progress_pct} /></td>
                    <td className="whitespace-nowrap py-2">{b.ready} / {b.nearly_ready}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

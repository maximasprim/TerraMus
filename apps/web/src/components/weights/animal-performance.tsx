"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, ErrorState, Input } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import { useCan } from "@/lib/use-auth";
import { AdgBarsChart, WeightProgressChart } from "@/components/weights/weight-charts";
import {
  adgText, BAND_CHIP, BAND_LABEL, fullDate, kg, shortDate, STAGE_CHIP, STAGE_LABEL, type AnimalWeights,
} from "@/lib/weights-types";

/** One animal's performance: stage, gain vs target, projection, charts, and a table of every weighing.
 * Used in the Weights page (in a dialog) and in the Weights tab of the animal's own page. */
export function AnimalPerformance({ animalId, showLink = false, showTable = true }: { animalId: string; showLink?: boolean; showTable?: boolean }) {
  const can = useCan();
  const qc = useQueryClient();
  const q = useQuery<AnimalWeights>({ queryKey: ["weights", "animal", animalId], queryFn: () => apiFetch<AnimalWeights>(`/api/v1/weights/animals/${animalId}`) });
  const [target, setTarget] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (value: number | null) => apiFetch(`/api/v1/weights/animals/${animalId}/target`, { method: "PUT", body: JSON.stringify({ target_weight_kg: value }) }),
    onSuccess: () => { setTarget(null); setErr(null); void qc.invalidateQueries({ queryKey: ["weights"] }); },
    onError: (e) => setErr(e instanceof ApiError ? e.message : "Could not save the target"),
  });

  if (q.isLoading) return <p className="text-sm text-muted">Loading…</p>;
  if (q.error || !q.data) return <ErrorState message={q.error instanceof ApiError ? q.error.message : "Could not load this animal's weights"} />;
  const d = q.data, a = d.animal;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STAGE_CHIP[a.stage]}`}>{STAGE_LABEL[a.stage]}</span>
        {a.hold_reason && <span className="rounded-full bg-clay/15 px-2.5 py-0.5 text-xs text-clay">On hold: {a.hold_reason}</span>}
        {a.adg_band && <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${BAND_CHIP[a.adg_band]}`}>{BAND_LABEL[a.adg_band]} growth</span>}
        {a.flags.includes("stale_weight") && <span className="rounded-full bg-brass/25 px-2.5 py-0.5 text-xs text-ink">Not weighed for {a.days_since_weighed} days</span>}
        {showLink && <Link href={`/admin/livestock/${a.id}`} className="ml-auto text-sm text-forest hover:underline">Open animal →</Link>}
      </div>

      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <Fact label="Latest weight" value={kg(a.current_kg)} hint={a.last_weighed ? `on ${fullDate(a.last_weighed)}` : undefined} />
        <Fact label="Target" value={kg(a.target_kg)} hint={a.target_source === "batch" ? "from its batch" : a.target_source === "animal" ? "set for this animal" : "none set"} />
        <Fact label="Still to gain" value={kg(a.remaining_kg)} hint={a.progress_pct != null ? `${a.progress_pct.toFixed(0)}% of the way` : undefined} />
        <Fact label="Daily gain" value={adgText(a.adg)} hint={a.overall_adg != null && a.recent_adg != null ? `overall ${a.overall_adg.toFixed(2)}` : undefined} />
        <Fact label="Gain so far" value={kg(a.gain_kg)} hint={a.start_kg != null ? `from ${kg(a.start_kg)}` : undefined} />
        <Fact label="Expected ready" value={a.stage === "ready" ? "Now" : a.est_ready_date ? shortDate(a.est_ready_date) : "-"}
          hint={a.days_to_ready != null && a.stage !== "ready" ? (a.days_to_ready === 0 ? "any day now" : `in about ${a.days_to_ready} days`) : undefined} />
      </dl>

      {a.progress_pct != null && (
        <div aria-label={`${a.progress_pct}% of target weight`}>
          <div className="h-2.5 overflow-hidden rounded-full bg-hairline"><div className="h-full rounded-full bg-forest" style={{ width: `${a.progress_pct}%` }} /></div>
        </div>
      )}

      <div>
        <h3 className="mb-1 font-display text-base text-forest">Weight over time</h3>
        <WeightProgressChart data={d} />
      </div>
      <div>
        <h3 className="mb-1 font-display text-base text-forest">Daily gain between weighings</h3>
        <AdgBarsChart data={d} />
      </div>

      {can("weights.targets") && (
        <div className="rounded-md border border-hairline bg-white/60 p-3">
          <p className="mb-2 text-sm font-medium text-ink">Target weight for this animal</p>
          <div className="flex flex-wrap items-end gap-2">
            <div className="w-36">
              <Input id={`tw-${animalId}`} type="number" inputMode="decimal" min="1" step="0.5" placeholder="e.g. 450" value={target ?? (a.target_source === "animal" ? String(a.target_kg ?? "") : "")}
                onChange={(e) => setTarget(e.target.value)} aria-label="Target weight in kg" />
            </div>
            <Button disabled={save.isPending || target === null || target === ""} onClick={() => save.mutate(Number(target))}>Save</Button>
            {a.target_source === "animal" && <Button variant="ghost" disabled={save.isPending} onClick={() => save.mutate(null)}>Use batch target</Button>}
          </div>
          <p className="mt-1 text-xs text-muted">This overrides the batch target for this animal only.</p>
          {err && <p className="mt-1 text-xs text-clay">{err}</p>}
        </div>
      )}

      {showTable && d.series.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead><tr className="border-b border-hairline text-xs uppercase tracking-wider text-muted">
              <th className="pb-2 pr-3 font-medium">Date</th><th className="pb-2 pr-3 font-medium">Weight</th>
              <th className="pb-2 pr-3 font-medium">Change</th><th className="pb-2 font-medium">Daily gain</th></tr></thead>
            <tbody>
              {[...d.series].reverse().map((p) => (
                <tr key={p.date} className="border-b border-hairline/60 last:border-0">
                  <td className="whitespace-nowrap py-1.5 pr-3">{fullDate(p.date)}</td>
                  <td className="whitespace-nowrap py-1.5 pr-3 font-medium text-ink">{kg(p.weight_kg, 2)}</td>
                  <td className="whitespace-nowrap py-1.5 pr-3 text-muted">{p.change_kg == null ? "-" : `${p.change_kg > 0 ? "+" : ""}${p.change_kg} kg`}</td>
                  <td className="whitespace-nowrap py-1.5">{p.adg == null ? "-" : <>{p.adg.toFixed(2)} <span className={`ml-1 rounded-full px-2 py-0.5 text-xs ${BAND_CHIP[p.band!]}`}>{BAND_LABEL[p.band!]}</span></>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Fact({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-muted">{label}</dt>
      <dd className="text-base font-medium text-ink">{value}</dd>
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  );
}

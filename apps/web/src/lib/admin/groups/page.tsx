"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Button, Card, EmptyState, ErrorState, Input, Modal, Select, StatusBadge } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";

interface Group {
  id: string; code: string; name: string; species: string; purpose: string | null; start_date: string;
  initial_count: number; current_count: number; status: string;
}
interface Perf {
  days: number; feed_kg: number; estimated_biomass_kg: number | null; approx_fcr?: number;
  mortality: { died: number; culled: number; mortality_pct: number };
  production: Record<string, number>; egg_production?: { hen_day_pct: number; eggs_per_bird: number };
  economics: { revenue: number; acquisition_cost: number; feed_cost: number; margin: number };
}
const today = () => new Date().toISOString().slice(0, 10);
const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);
const kes = (n: number) => new Intl.NumberFormat("en-KE", { maximumFractionDigits: 0 }).format(n);
const RECORD_TYPES = [
  ["mortality", "Mortality (died)"], ["cull", "Cull"], ["production", "Production (eggs / kg harvested)"], ["feed", "Feed given"],
  ["weight_sample", "Weight sample"], ["sale", "Sale"], ["addition", "Addition (restock / hatch)"],
] as const;

export default function GroupsPage() {
  const queryClient = useQueryClient();
  const [newOpen, setNewOpen] = useState(false);
  const [recFor, setRecFor] = useState<Group | null>(null);
  const [perfFor, setPerfFor] = useState<Group | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [g, setG] = useState({ code: "", name: "", species: "poultry", purpose: "", start_date: today(), initial_count: "", acquisition_cost: "" });
  const [r, setR] = useState({ record_type: "mortality", record_date: today(), quantity: "", unit: "", value: "", avg_weight_kg: "" });

  const { data, isLoading, error: loadErr } = useQuery<Group[]>({ queryKey: ["groups"], queryFn: () => apiFetch<Group[]>("/api/v1/groups") });
  const perf = useQuery<Perf>({ queryKey: ["groups", "perf", perfFor?.id], enabled: !!perfFor, queryFn: () => apiFetch<Perf>(`/api/v1/groups/${perfFor?.id}/performance`) });

  const create = useMutation({
    mutationFn: () => apiFetch("/api/v1/groups", { method: "POST", body: JSON.stringify({
      ...g, purpose: g.purpose || undefined, initial_count: Number(g.initial_count), acquisition_cost: g.acquisition_cost || "0" }) }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["groups"] }); setNewOpen(false); setError(null); },
    onError: (e) => setError(errMsg(e, "Could not create group")),
  });
  const record = useMutation({
    mutationFn: () => apiFetch(`/api/v1/groups/${recFor?.id}/records`, { method: "POST", body: JSON.stringify({
      record_type: r.record_type, record_date: r.record_date, quantity: Number(r.quantity), unit: r.unit || undefined,
      value: r.value ? Number(r.value) : undefined, avg_weight_kg: r.avg_weight_kg ? Number(r.avg_weight_kg) : undefined,
      product: r.record_type === "sale" && r.unit === "eggs" ? "eggs" : undefined }) }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["groups"] }); setRecFor(null); setError(null); setR({ ...r, quantity: "", value: "" }); },
    onError: (e) => setError(errMsg(e, "Could not save record")),
  });

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Flocks &amp; Fish</h1>
          <p className="text-sm text-muted">Poultry, rabbits, fish and pigs managed by headcount: mortality, eggs, feed, weights and sales.</p>
        </div>
        <Button onClick={() => { setError(null); setNewOpen(true); }}>+ New group</Button>
      </div>
      {loadErr && <ErrorState message={errMsg(loadErr, "Failed to load groups")} />}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {data && data.length === 0 && <EmptyState title="No groups yet" body="Create a flock, pond or hutch to start recording." />}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {data?.map((x) => (
          <Card key={x.id} className="space-y-2">
            <div className="flex items-center justify-between"><span className="font-mono text-sm">{x.code}</span><StatusBadge status={x.status} /></div>
            <p className="font-display text-lg text-forest">{x.name}</p>
            <p className="text-sm text-muted">{x.species}{x.purpose ? ` · ${x.purpose}` : ""} · since {x.start_date}</p>
            <p className="text-2xl font-display text-forest">{x.current_count}<span className="text-sm text-muted"> / {x.initial_count} head</span></p>
            <div className="flex gap-2">
              {x.status === "active" && <Button variant="ghost" onClick={() => { setError(null); setRecFor(x); }}>Record</Button>}
              <Button variant="ghost" onClick={() => setPerfFor(x)}>Performance</Button>
            </div>
          </Card>))}
      </div>
      <Modal open={newOpen} onClose={() => setNewOpen(false)} title="New group">
        <div className="space-y-3">
          {error && <ErrorState message={error} />}
          <Input label="Code" value={g.code} onChange={(e) => setG({ ...g, code: e.target.value })} placeholder="L-01" />
          <Input label="Name" value={g.name} onChange={(e) => setG({ ...g, name: e.target.value })} placeholder="Layers - House 1" />
          <Select label="Species" value={g.species} onChange={(e) => setG({ ...g, species: e.target.value })}>
            {["poultry", "rabbits", "fish", "pigs", "other"].map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
          <Input label="Purpose (layers, broilers, growout…)" value={g.purpose} onChange={(e) => setG({ ...g, purpose: e.target.value })} />
          <Input label="Start date" type="date" value={g.start_date} onChange={(e) => setG({ ...g, start_date: e.target.value })} />
          <Input label="Number of animals" type="number" min="1" value={g.initial_count} onChange={(e) => setG({ ...g, initial_count: e.target.value })} />
          <Input label="Purchase cost (KES)" type="number" min="0" value={g.acquisition_cost} onChange={(e) => setG({ ...g, acquisition_cost: e.target.value })} />
          <Button disabled={!g.code || g.name.length < 2 || !(Number(g.initial_count) > 0) || create.isPending} onClick={() => create.mutate()}>Create group</Button>
        </div>
      </Modal>
      <Modal open={!!recFor} onClose={() => setRecFor(null)} title={`Record for ${recFor?.name ?? ""}`}>
        <div className="space-y-3">
          {error && <ErrorState message={error} />}
          <Select label="What happened?" value={r.record_type} onChange={(e) => setR({ ...r, record_type: e.target.value })}>
            {RECORD_TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </Select>
          <Input label="Date" type="date" value={r.record_date} onChange={(e) => setR({ ...r, record_date: e.target.value })} />
          <Input label={r.record_type === "weight_sample" ? "Number weighed" : "Quantity"} type="number" min="0" step="any" value={r.quantity} onChange={(e) => setR({ ...r, quantity: e.target.value })} />
          {["production", "feed", "sale"].includes(r.record_type) && <Input label="Unit (eggs, kg, head, trays)" value={r.unit} onChange={(e) => setR({ ...r, unit: e.target.value })} />}
          {r.record_type === "weight_sample" && <Input label="Average weight (kg)" type="number" step="any" value={r.avg_weight_kg} onChange={(e) => setR({ ...r, avg_weight_kg: e.target.value })} />}
          {["sale", "feed"].includes(r.record_type) && <Input label={r.record_type === "sale" ? "Sale proceeds (KES)" : "Feed cost (KES, optional)"} type="number" min="0" value={r.value} onChange={(e) => setR({ ...r, value: e.target.value })} />}
          <Button disabled={!(Number(r.quantity) >= 0) || r.quantity === "" || record.isPending} onClick={() => record.mutate()}>Save record</Button>
        </div>
      </Modal>
      <Modal open={!!perfFor} onClose={() => setPerfFor(null)} title={`Performance: ${perfFor?.name ?? ""}`}>
        {perf.isLoading && <p className="text-sm text-muted">Loading…</p>}
        {perf.data && (
          <div className="space-y-2 text-sm">
            <p>Mortality <b>{perf.data.mortality.mortality_pct}%</b> ({perf.data.mortality.died} died, {perf.data.mortality.culled} culled) over {perf.data.days} days</p>
            <p>Feed {perf.data.feed_kg} kg{perf.data.approx_fcr ? ` · approx. FCR ${perf.data.approx_fcr}` : ""}{perf.data.estimated_biomass_kg ? ` · biomass ≈ ${perf.data.estimated_biomass_kg} kg` : ""}</p>
            {Object.entries(perf.data.production).map(([u, v]) => <p key={u}>Production: {v} {u}</p>)}
            {perf.data.egg_production && <p>Hen-day production <b>{perf.data.egg_production.hen_day_pct}%</b> · {perf.data.egg_production.eggs_per_bird} eggs per bird</p>}
            <p className="border-t border-hairline pt-2">Revenue {kes(perf.data.economics.revenue)} − purchase {kes(perf.data.economics.acquisition_cost)} − feed {kes(perf.data.economics.feed_cost)} = <b className={perf.data.economics.margin < 0 ? "text-clay" : "text-forest"}>{kes(perf.data.economics.margin)}</b></p>
          </div>
        )}
      </Modal>
    </AdminShell>
  );
}

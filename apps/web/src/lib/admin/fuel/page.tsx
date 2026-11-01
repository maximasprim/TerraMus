"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Button, Card, EmptyState, ErrorState, Input, Modal, Select, StatCard } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { Asset } from "@/lib/types";

interface FuelRow { id: string; asset: string | null; date: string; litres: number; cost: number; cost_per_litre: number | null; meter_reading: number | null; purpose: string | null; activity: string | null; driver: string | null }
interface Summary {
  total_litres: number; total_cost: number; cost_by_activity: Record<string, number>;
  by_asset: { asset_id: string; asset: string; fills: number; litres: number; cost: number; avg_cost_per_litre: number | null; litres_per_meter_unit: number | null }[];
  by_month: { month: string; litres: number; cost: number }[];
}
interface Farm { id: string; name: string }
const ACTIVITIES = ["livestock", "feedlot", "dairy", "crops", "fodder", "poultry", "fish", "rabbits", "training", "general"];
const iso = (d: Date) => d.toISOString().slice(0, 10);
const money = (n: number) => new Intl.NumberFormat("en-KE", { maximumFractionDigits: 0 }).format(n);
const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);

export default function FuelPage() {
  const qc = useQueryClient();
  const [from, setFrom] = useState(iso(new Date(Date.now() - 90 * 86400000)));
  const [to, setTo] = useState(iso(new Date()));
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [f, setF] = useState({ asset_id: "", log_date: iso(new Date()), litres: "", cost: "", meter_reading: "", purpose: "", activity: "", farm_id: "", driver: "", post_to_finance: true });

  const assets = useQuery<Asset[]>({ queryKey: ["assets"], queryFn: () => apiFetch<Asset[]>("/api/v1/assets") });
  const farms = useQuery<Farm[]>({ queryKey: ["farms"], queryFn: () => apiFetch<Farm[]>("/api/v1/farms") });
  const logs = useQuery<FuelRow[]>({ queryKey: ["fuel", "list", from, to], queryFn: () => apiFetch<FuelRow[]>(`/api/v1/fuel?start_date=${from}&end_date=${to}`) });
  const summary = useQuery<Summary>({ queryKey: ["fuel", "summary", from, to], queryFn: () => apiFetch<Summary>(`/api/v1/fuel/summary?start_date=${from}&end_date=${to}`) });

  const log = useMutation({
    mutationFn: () => apiFetch("/api/v1/fuel", { method: "POST", body: JSON.stringify({
      asset_id: f.asset_id, log_date: f.log_date, litres: Number(f.litres), cost: f.cost ? Number(f.cost) : 0,
      meter_reading: f.meter_reading ? Number(f.meter_reading) : undefined, purpose: f.purpose || undefined, activity: f.activity || undefined,
      farm_id: f.farm_id || undefined, driver: f.driver || undefined, post_to_finance: f.post_to_finance }) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["fuel"] }); qc.invalidateQueries({ queryKey: ["finance"] }); setOpen(false); setError(null); setF({ ...f, litres: "", cost: "", meter_reading: "", purpose: "" }); },
    onError: (e) => setError(errMsg(e, "Could not save the fuel entry")),
  });
  const err = logs.error ?? summary.error;

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Fuel</h1>
          <p className="text-sm text-muted">Fuel drawn by each machine or vehicle. Each fill posts a fuel expense to Finance, tagged to the sub-farm and activity.</p>
        </div>
        <Button onClick={() => { setError(null); setOpen(true); }}>+ Log fuel</Button>
      </div>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Input label="From" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        <Input label="To" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>
      {err && <ErrorState message={errMsg(err, "Failed to load fuel data")} />}
      {logs.data && logs.data.length === 0 && <EmptyState title="No fuel logged in this period" body="Log each fill-up with the litres, cost and (optionally) the hour-meter or odometer reading." />}
      {summary.data && logs.data && logs.data.length > 0 && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="Litres" value={money(summary.data.total_litres)} />
            <StatCard label="Cost (KES)" value={money(summary.data.total_cost)} />
            <StatCard label="Avg KES / litre" value={summary.data.total_litres ? (summary.data.total_cost / summary.data.total_litres).toFixed(0) : "-"} />
            <StatCard label="Machines" value={String(summary.data.by_asset.length)} />
          </div>
          <Card>
            <h2 className="mb-3 font-display text-lg text-forest">By machine</h2>
            <table className="w-full text-sm"><thead><tr className="border-b border-hairline text-left text-xs uppercase text-muted">
              <th className="py-2">Asset</th><th className="text-right">Fills</th><th className="text-right">Litres</th><th className="text-right">Cost</th><th className="text-right">KES/L</th><th className="text-right">L per hour/km</th></tr></thead>
              <tbody>{summary.data.by_asset.map((a) => (
                <tr key={a.asset_id} className="border-b border-hairline/60"><td className="py-2 font-medium">{a.asset}</td><td className="text-right">{a.fills}</td><td className="text-right">{money(a.litres)}</td>
                  <td className="text-right">{money(a.cost)}</td><td className="text-right">{a.avg_cost_per_litre ?? "-"}</td><td className="text-right">{a.litres_per_meter_unit ?? "-"}</td></tr>))}</tbody></table>
            <p className="mt-2 text-xs text-muted">Litres per hour/km needs at least two fills with a meter reading.</p>
          </Card>
          <Card>
            <h2 className="mb-3 font-display text-lg text-forest">Recent fills</h2>
            <div className="overflow-x-auto"><table className="w-full text-sm"><tbody>{logs.data.map((r) => (
              <tr key={r.id} className="border-b border-hairline/60"><td className="py-1.5">{r.date}</td><td>{r.asset}</td><td className="text-right">{r.litres} L</td>
                <td className="text-right">KES {money(r.cost)}</td><td className="text-xs text-muted">{[r.activity, r.purpose, r.driver].filter(Boolean).join(" · ")}</td></tr>))}</tbody></table></div>
          </Card>
        </div>
      )}
      <Modal open={open} onClose={() => setOpen(false)} title="Log fuel">
        <div className="space-y-3">
          {error && <ErrorState message={error} />}
          <Select label="Machine / vehicle" value={f.asset_id} onChange={(e) => setF({ ...f, asset_id: e.target.value })}>
            <option value="">Choose…</option>{(assets.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </Select>
          <div className="grid grid-cols-2 gap-3">
            <Input label="Date" type="date" value={f.log_date} onChange={(e) => setF({ ...f, log_date: e.target.value })} />
            <Input label="Litres" type="number" min="0" step="any" value={f.litres} onChange={(e) => setF({ ...f, litres: e.target.value })} />
            <Input label="Cost (KES)" type="number" min="0" value={f.cost} onChange={(e) => setF({ ...f, cost: e.target.value })} />
            <Input label="Hour-meter / odometer" type="number" min="0" step="any" value={f.meter_reading} onChange={(e) => setF({ ...f, meter_reading: e.target.value })} />
            <Select label="Activity" value={f.activity} onChange={(e) => setF({ ...f, activity: e.target.value })}>
              <option value="">Not specified</option>{ACTIVITIES.map((a) => <option key={a} value={a}>{a}</option>)}
            </Select>
            <Select label="Sub-farm" value={f.farm_id} onChange={(e) => setF({ ...f, farm_id: e.target.value })}>
              <option value="">Machine's farm</option>{(farms.data ?? []).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
            </Select>
          </div>
          <Input label="Purpose" value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })} placeholder="e.g. ploughing, silage harvest" />
          <Input label="Driver / operator" value={f.driver} onChange={(e) => setF({ ...f, driver: e.target.value })} />
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.post_to_finance} onChange={(e) => setF({ ...f, post_to_finance: e.target.checked })} /> Post the cost to Finance as a fuel expense</label>
          <Button disabled={!f.asset_id || !(Number(f.litres) > 0) || log.isPending} onClick={() => log.mutate()}>Save</Button>
        </div>
      </Modal>
    </AdminShell>
  );
}

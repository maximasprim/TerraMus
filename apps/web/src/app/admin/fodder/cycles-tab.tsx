"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, EmptyState, ErrorState, Input, Modal, Select } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useCan } from "@/lib/use-auth";
import { COST_CATEGORIES, Cycle, CycleDetail, errMsg, money, Plot, Product, todayIso } from "./shared";

export function CyclesTab() {
  const qc = useQueryClient();
  const can = useCan();
  const [newOpen, setNewOpen] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [f, setF] = useState({ plot_id: "", product_id: "", label: "", start_date: todayIso(), acres: "", budget_name: "" });
  const cycles = useQuery<Cycle[]>({ queryKey: ["fodder", "cycles"], queryFn: () => apiFetch<Cycle[]>("/api/v1/fodder/cycles") });
  const plots = useQuery<Plot[]>({ queryKey: ["fodder", "plots"], queryFn: () => apiFetch<Plot[]>("/api/v1/fodder/plots") });
  const products = useQuery<Product[]>({ queryKey: ["fodder", "products"], queryFn: () => apiFetch<Product[]>("/api/v1/fodder/products?active_only=true") });
  const budgets = useQuery<{ name: string }[]>({ queryKey: ["feedlot", "costing", "budgets"], retry: false, queryFn: () => apiFetch<{ name: string }[]>("/api/v1/feedlot/costing?kind=enterprise_budget") });
  const refresh = () => qc.invalidateQueries({ queryKey: ["fodder"] });
  const create = useMutation({
    mutationFn: () => apiFetch("/api/v1/fodder/cycles", { method: "POST", body: JSON.stringify({ plot_id: f.plot_id, product_id: f.product_id, label: f.label, start_date: f.start_date, acres: f.acres ? Number(f.acres) : undefined, budget_name: f.budget_name || undefined }) }),
    onSuccess: () => { refresh(); setNewOpen(false); setError(null); }, onError: (e) => setError(errMsg(e, "Could not start the cycle")),
  });
  const plot = (plots.data ?? []).find((p) => p.id === f.plot_id);
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted">A cycle is one crop on one plot over a season. Costs and harvests go against it; the cost per kg falls out of them.</p>
        {can("fodder.manage") && <Button disabled={!plots.data?.length || !products.data?.length} onClick={() => { setError(null); setF({ ...f, plot_id: plots.data?.[0]?.id ?? "", product_id: products.data?.[0]?.id ?? "" }); setNewOpen(true); }}>+ Start a cycle</Button>}
      </div>
      {cycles.error && <ErrorState message={errMsg(cycles.error, "Failed to load cycles")} />}
      {cycles.data && cycles.data.length === 0 && <EmptyState title="No production cycles yet" body={plots.data?.length && products.data?.length ? "Start a cycle to begin recording costs and harvests." : "Add a product and a plot on the setup tab first."} />}
      <Card>
        <div className="overflow-x-auto"><table className="w-full text-sm"><tbody>
          {(cycles.data ?? []).map((c) => {
            const e = c.economics;
            return (
              <tr key={c.id} className="cursor-pointer border-b border-hairline/60 hover:bg-forest/5" onClick={() => setOpenId(c.id)}>
                <td className="py-2"><div className="font-medium text-forest">{c.label}</div><div className="text-xs text-muted">{c.plot} · {c.product} · {c.acres} acres · {c.start_date}{c.end_date ? ` → ${c.end_date}` : " (open)"}</div></td>
                <td className="text-right text-xs">{e?.harvested_units != null ? `${money(e.harvested_units, 0)} ${c.unit_label}s` : "-"}<div className="text-muted">{e?.yield_kg_per_acre != null ? `${money(e.yield_kg_per_acre)} kg/acre` : "no harvest yet"}</div></td>
                <td className="text-right text-xs">{e?.cost_per_kg != null ? `KES ${e.cost_per_kg.toFixed(2)}/kg` : "-"}<div className="text-muted">{e?.cost_per_unit != null ? `KES ${money(e.cost_per_unit)} per ${c.unit_label}` : ""}</div></td>
                <td className={`text-right text-xs font-medium ${(e?.saving_vs_buying ?? 0) < 0 ? "text-clay" : "text-forest"}`}>{e?.saving_vs_buying != null ? `${e.saving_vs_buying < 0 ? "" : "+"}${money(e.saving_vs_buying)}` : "-"}<div className="font-normal text-muted">vs buying</div></td>
              </tr>);
          })}</tbody></table></div>
      </Card>
      <Modal open={newOpen} onClose={() => setNewOpen(false)} title="Start a production cycle">
        <div className="space-y-3">
          {error && <ErrorState message={error} />}
          <Select label="Plot" value={f.plot_id} onChange={(e) => setF({ ...f, plot_id: e.target.value })}>{(plots.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name} ({p.acres_free} of {p.acres} acres free)</option>)}</Select>
          <Select label="Producing" value={f.product_id} onChange={(e) => setF({ ...f, product_id: e.target.value })}>{(products.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select>
          <Input label="Name of this cycle" value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} placeholder="Lucerne - long rains 2026" />
          <div className="grid grid-cols-2 gap-3">
            <Input label="Start date" type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} />
            <Input label={`Acres (max ${plot?.acres_free ?? "-"})`} type="number" min="0" step="any" value={f.acres} onChange={(e) => setF({ ...f, acres: e.target.value })} placeholder="whole plot" />
          </div>
          {!budgets.error && (budgets.data?.length ?? 0) > 0 && (
            <Select label="Compare against budget (optional)" value={f.budget_name} onChange={(e) => setF({ ...f, budget_name: e.target.value })}>
              <option value="">No budget</option>{(budgets.data ?? []).map((b) => <option key={b.name} value={b.name}>{b.name}</option>)}</Select>)}
          <Button disabled={!f.plot_id || !f.product_id || f.label.trim().length < 2 || create.isPending} onClick={() => create.mutate()}>Start cycle</Button>
        </div>
      </Modal>
      {openId && <CycleModal id={openId} onClose={() => setOpenId(null)} />}
    </div>
  );
}

function CycleModal({ id, onClose }: { id: string; onClose: () => void }) {
  const qc = useQueryClient();
  const can = useCan();
  const [error, setError] = useState<string | null>(null);
  const [cost, setCost] = useState({ cost_date: todayIso(), category: "seed", amount: "", description: "", post: true });
  const [harv, setHarv] = useState({ harvest_date: todayIso(), quantity: "", kg: "", quality: "" });
  const [endDate, setEndDate] = useState(todayIso());
  const d = useQuery<CycleDetail>({ queryKey: ["fodder", "cycle", id], queryFn: () => apiFetch<CycleDetail>(`/api/v1/fodder/cycles/${id}`) });
  const done = () => { qc.invalidateQueries({ queryKey: ["fodder"] }); setError(null); };
  const addCost = useMutation({
    mutationFn: () => apiFetch(`/api/v1/fodder/cycles/${id}/costs`, { method: "POST", body: JSON.stringify({ cost_date: cost.cost_date, category: cost.category, amount: Number(cost.amount), description: cost.description || undefined, post_to_finance: cost.post }) }),
    onSuccess: () => { done(); setCost({ ...cost, amount: "", description: "" }); }, onError: (e) => setError(errMsg(e, "Could not save the cost")),
  });
  const addHarvest = useMutation({
    mutationFn: () => apiFetch(`/api/v1/fodder/cycles/${id}/harvests`, { method: "POST", body: JSON.stringify({ harvest_date: harv.harvest_date, quantity: Number(harv.quantity), kg: harv.kg ? Number(harv.kg) : undefined, quality: harv.quality || undefined }) }),
    onSuccess: () => { done(); setHarv({ ...harv, quantity: "", kg: "" }); }, onError: (e) => setError(errMsg(e, "Could not save the harvest")),
  });
  const close = useMutation({
    mutationFn: () => apiFetch(`/api/v1/fodder/cycles/${id}/close`, { method: "POST", body: JSON.stringify({ end_date: endDate }) }),
    onSuccess: done, onError: (e) => setError(errMsg(e, "Could not close the cycle")),
  });
  const c = d.data; const e = c?.economics;
  return (
    <Modal open onClose={onClose} title={c ? `${c.label} · ${c.plot}` : "Cycle"} size="lg">
      {d.isLoading && <p className="text-sm text-muted">Loading…</p>}
      {c && e && (
        <div className="space-y-4 text-sm">
          {error && <ErrorState message={error} />}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <div><div className="text-xs text-muted">Harvested</div><div className="font-medium">{money(e.harvested_units, 0)} {c.unit_label}s</div><div className="text-xs text-muted">{money(e.harvested_kg)} kg</div></div>
            <div><div className="text-xs text-muted">Cost per kg</div><div className="font-medium">{e.cost_per_kg?.toFixed(2) ?? "-"}</div><div className="text-xs text-muted">{e.cost_per_unit != null ? `${money(e.cost_per_unit)} per ${c.unit_label}` : ""}</div></div>
            <div><div className="text-xs text-muted">Yield</div><div className="font-medium">{money(e.yield_kg_per_acre)} kg/acre</div>{e.yield_vs_target_pct != null && <div className={`text-xs ${e.yield_vs_target_pct < 0 ? "text-clay" : "text-forest"}`}>{e.yield_vs_target_pct > 0 ? "+" : ""}{e.yield_vs_target_pct}% vs budget</div>}</div>
            <div><div className="text-xs text-muted">Saved vs buying</div><div className={`font-medium ${(e.saving_vs_buying ?? 0) < 0 ? "text-clay" : "text-forest"}`}>{money(e.saving_vs_buying)}</div><div className="text-xs text-muted">worth {money(e.replacement_value)}</div></div>
          </div>
          <p className="text-xs text-muted">Total cost KES {money(e.total_cost)} = direct KES {money(e.direct_cost)} + amortised establishment and shared assets KES {money(e.amortised_cost)}.
            {e.cost_per_kg_vs_budget_pct != null && ` Cost per kg is ${Math.abs(e.cost_per_kg_vs_budget_pct)}% ${e.cost_per_kg_vs_budget_pct > 0 ? "over" : "under"} budget.`}
            {e.unpriced_kg > 0 && ` ${money(e.unpriced_kg)} kg were harvested before any market price was entered, so they are not valued.`}</p>
          {c.status === "open" && can("fodder.record") && (
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2 rounded border border-hairline p-3">
                <p className="font-medium">Record a cost</p>
                <div className="grid grid-cols-2 gap-2"><Input label="Date" type="date" value={cost.cost_date} onChange={(x) => setCost({ ...cost, cost_date: x.target.value })} />
                  <Select label="Type" value={cost.category} onChange={(x) => setCost({ ...cost, category: x.target.value })}>{COST_CATEGORIES.map((k) => <option key={k} value={k}>{k.replace("_", " ")}</option>)}</Select></div>
                <Input label="Amount (KES)" type="number" min="0" value={cost.amount} onChange={(x) => setCost({ ...cost, amount: x.target.value })} />
                <Input label="Note" value={cost.description} onChange={(x) => setCost({ ...cost, description: x.target.value })} />
                <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={cost.post} onChange={(x) => setCost({ ...cost, post: x.target.checked })} /> Also record as an expense in Finance (untick if you already entered it there)</label>
                <Button disabled={!(Number(cost.amount) > 0) || addCost.isPending} onClick={() => addCost.mutate()}>Save cost</Button>
              </div>
              <div className="space-y-2 rounded border border-hairline p-3">
                <p className="font-medium">Record a harvest</p>
                <Input label="Date" type="date" value={harv.harvest_date} onChange={(x) => setHarv({ ...harv, harvest_date: x.target.value })} />
                <div className="grid grid-cols-2 gap-2"><Input label={`How many ${c.unit_label}s`} type="number" min="0" step="any" value={harv.quantity} onChange={(x) => setHarv({ ...harv, quantity: x.target.value })} />
                  <Input label="Weighed kg (optional)" type="number" min="0" step="any" value={harv.kg} onChange={(x) => setHarv({ ...harv, kg: x.target.value })} /></div>
                <Select label="Quality" value={harv.quality} onChange={(x) => setHarv({ ...harv, quality: x.target.value })}><option value="">-</option><option value="good">good</option><option value="fair">fair</option><option value="poor">poor</option></Select>
                <Button disabled={!(Number(harv.quantity) > 0) || addHarvest.isPending} onClick={() => addHarvest.mutate()}>Save harvest (adds to stock)</Button>
              </div>
            </div>)}
          <div className="grid gap-4 md:grid-cols-2">
            <div><p className="mb-1 font-medium">Costs</p>{c.costs.length === 0 && <p className="text-xs text-muted">None yet.</p>}
              {c.costs.map((x) => <div key={x.id} className="flex justify-between border-b border-hairline/60 py-1 text-xs"><span>{x.date} · {x.category.replace("_", " ")}{x.description ? ` · ${x.description}` : ""}</span><span>{money(x.amount)}</span></div>)}</div>
            <div><p className="mb-1 font-medium">Harvests</p>{c.harvests.length === 0 && <p className="text-xs text-muted">None yet.</p>}
              {c.harvests.map((x) => <div key={x.id} className="flex justify-between border-b border-hairline/60 py-1 text-xs"><span>{x.date}{x.quality ? ` · ${x.quality}` : ""}</span><span>{money(x.quantity, 1)} {c.unit_label}s · {money(x.kg)} kg</span></div>)}</div>
          </div>
          {c.status === "open" && can("fodder.manage") && (
            <div className="flex items-end gap-2 border-t border-hairline pt-3"><Input label="Close the cycle on" type="date" value={endDate} onChange={(x) => setEndDate(x.target.value)} />
              <Button variant="ghost" disabled={close.isPending} onClick={() => { if (window.confirm("Close this cycle? The plot's acres are freed for the next one, and no more costs can be added.")) close.mutate(); }}>Close cycle</Button></div>)}
        </div>
      )}
    </Modal>
  );
}

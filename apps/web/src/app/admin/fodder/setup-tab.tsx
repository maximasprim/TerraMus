"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, ErrorState, Input, Modal, Select } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useCan } from "@/lib/use-auth";
import { errMsg, money, Plot, Product, Schedule, todayIso } from "./shared";

type Dlg = "product" | "price" | "plot" | "investment" | null;
interface Farm { id: string; name: string }

export function SetupTab() {
  const qc = useQueryClient();
  const can = useCan();
  const manage = can("fodder.manage");
  const [dlg, setDlg] = useState<Dlg>(null);
  const [priceFor, setPriceFor] = useState<Product | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [p, setP] = useState({ name: "", category: "hay", unit_label: "bale", kg_per_unit: "14", reorder_days: "14" });
  const [pr, setPr] = useState({ effective_from: todayIso(), price_per_kg: "", source: "" });
  const [pl, setPl] = useState({ name: "", acres: "", farm_id: "", irrigated: false, crop: "" });
  const [iv, setIv] = useState({ name: "", cost: "", salvage_value: "", in_service_on: todayIso(), life_years: "5", plot_id: "" });
  const products = useQuery<Product[]>({ queryKey: ["fodder", "products"], queryFn: () => apiFetch<Product[]>("/api/v1/fodder/products") });
  const plots = useQuery<Plot[]>({ queryKey: ["fodder", "plots"], queryFn: () => apiFetch<Plot[]>("/api/v1/fodder/plots") });
  const sched = useQuery<Schedule>({ queryKey: ["fodder", "investments"], queryFn: () => apiFetch<Schedule>("/api/v1/fodder/investments") });
  const farms = useQuery<Farm[]>({ queryKey: ["farms"], queryFn: () => apiFetch<Farm[]>("/api/v1/farms") });
  const done = () => { qc.invalidateQueries({ queryKey: ["fodder"] }); setDlg(null); setError(null); };
  const fail = (m: string) => (e: unknown) => setError(errMsg(e, m));
  const post = (path: string, body: object) => apiFetch(path, { method: "POST", body: JSON.stringify(body) });
  const mkProduct = useMutation({ mutationFn: () => post("/api/v1/fodder/products", { name: p.name, category: p.category, unit_label: p.unit_label, kg_per_unit: Number(p.kg_per_unit), reorder_days: Number(p.reorder_days) }), onSuccess: done, onError: fail("Could not add the product") });
  const mkPrice = useMutation({ mutationFn: () => post(`/api/v1/fodder/products/${priceFor?.id}/prices`, { effective_from: pr.effective_from, price_per_kg: Number(pr.price_per_kg), source: pr.source || undefined }), onSuccess: done, onError: fail("Could not save the price") });
  const mkPlot = useMutation({ mutationFn: () => post("/api/v1/fodder/plots", { name: pl.name, acres: Number(pl.acres), farm_id: pl.farm_id || undefined, irrigated: pl.irrigated, crop: pl.crop || undefined }), onSuccess: done, onError: fail("Could not add the plot") });
  const mkInv = useMutation({ mutationFn: () => post("/api/v1/fodder/investments", { name: iv.name, cost: Number(iv.cost), salvage_value: iv.salvage_value ? Number(iv.salvage_value) : 0, in_service_on: iv.in_service_on, life_years: Number(iv.life_years), plot_id: iv.plot_id || undefined }), onSuccess: done, onError: fail("Could not add the investment") });
  const dispose = useMutation({ mutationFn: (id: string) => post(`/api/v1/fodder/investments/${id}/dispose`, { disposed_on: todayIso() }), onSuccess: done, onError: fail("Could not record the disposal") });
  const perDay = Number(iv.cost) > 0 && Number(iv.life_years) > 0 ? (Number(iv.cost) - Number(iv.salvage_value || 0)) / (Number(iv.life_years) * 365) : null;
  return (
    <div className="space-y-6">
      {error && !dlg && <ErrorState message={error} />}
      <Card>
        <div className="mb-2 flex items-center justify-between"><div><h2 className="font-display text-lg text-forest">Fodder products &amp; market prices</h2>
          <p className="text-xs text-muted">The market price is what buying it would cost. It values your production and shows what growing saved you.</p></div>
          {manage && <Button variant="ghost" onClick={() => { setError(null); setDlg("product"); }}>+ Product</Button>}</div>
        {(products.data ?? []).map((x) => (
          <div key={x.id} className="flex items-center justify-between border-t border-hairline/60 py-2 text-sm"><div><div className="font-medium">{x.name}</div>
            <div className="text-xs text-muted">{x.category} · 1 {x.unit_label} = {x.kg_per_unit} kg · reorder at {x.reorder_days} days of cover</div></div>
            <div className="flex items-center gap-3"><span className="text-xs">{x.current_price_per_kg != null ? `KES ${x.current_price_per_kg}/kg` : <span className="text-clay">no market price</span>}</span>
              {manage && <Button variant="ghost" onClick={() => { setError(null); setPriceFor(x); setDlg("price"); }}>Set price</Button>}</div></div>))}
      </Card>
      <Card>
        <div className="mb-2 flex items-center justify-between"><h2 className="font-display text-lg text-forest">Plots</h2>{manage && <Button variant="ghost" onClick={() => { setError(null); setDlg("plot"); }}>+ Plot</Button>}</div>
        <table className="w-full text-sm"><tbody>{(plots.data ?? []).map((x) => (
          <tr key={x.id} className="border-t border-hairline/60"><td className="py-2 font-medium">{x.name}</td><td>{x.crop ?? "-"}</td><td className="text-right">{x.acres} acres</td>
            <td className="text-right text-xs text-muted">{x.acres_in_use} planted · {x.acres_free} free</td><td className="text-right text-xs">{x.irrigated ? "Irrigated" : "Rain-fed"}</td></tr>))}</tbody></table>
      </Card>
      <Card>
        <div className="mb-1 flex items-center justify-between"><div><h2 className="font-display text-lg text-forest">Investments &amp; amortisation</h2>
          <p className="text-xs text-muted">Land preparation, bunkers, balers, irrigation: spread evenly over their life and shared between cycles by acre-days. Time nobody is using an asset shows as idle capacity.</p></div>
          {manage && <Button variant="ghost" onClick={() => { setError(null); setDlg("investment"); }}>+ Investment</Button>}</div>
        {sched.data && sched.data.investments.length > 0 && (
          <>
            <div className="my-3 grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
              <div><div className="text-xs text-muted">Invested</div><div className="font-medium">KES {money(sched.data.totals.cost)}</div></div>
              <div><div className="text-xs text-muted">Amortised so far</div><div className="font-medium">KES {money(sched.data.totals.amortised_to_date)}</div></div>
              <div><div className="text-xs text-muted">Charge per year</div><div className="font-medium">KES {money(sched.data.totals.per_year)}</div></div>
              <div><div className="text-xs text-muted">Idle capacity cost</div><div className={`font-medium ${sched.data.totals.idle_capacity_cost > 0 ? "text-clay" : ""}`}>KES {money(sched.data.totals.idle_capacity_cost)}</div></div>
            </div>
            <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-hairline text-left text-xs uppercase text-muted">
              <th className="py-2">Asset</th><th className="text-right">Cost</th><th className="text-right">Life</th><th className="text-right">Per year</th><th className="text-right">Book value</th><th className="text-right">Idle</th><th /></tr></thead>
              <tbody>{sched.data.investments.map((i) => (
                <tr key={i.id} className="border-b border-hairline/60"><td className="py-2"><div className="font-medium">{i.name}</div><div className="text-xs text-muted">{i.shared ? "shared by all plots" : "one plot"} · from {i.in_service_on}{i.disposed_on ? ` · disposed ${i.disposed_on}` : ""}</div></td>
                  <td className="text-right">{money(i.cost)}</td><td className="text-right">{i.life_years} yrs</td><td className="text-right">{money(i.per_year)}</td><td className="text-right">{money(i.book_value)}</td>
                  <td className="text-right">{money(i.idle_capacity_cost ?? 0)}</td>
                  <td className="text-right">{manage && !i.disposed_on && <Button variant="ghost" onClick={() => { if (window.confirm(`Record ${i.name} as sold or scrapped today? Amortisation stops.`)) dispose.mutate(i.id); }}>Dispose</Button>}</td></tr>))}</tbody></table></div>
          </>)}
      </Card>
      <Modal open={dlg === "product"} onClose={() => setDlg(null)} title="New fodder product"><div className="space-y-3">{error && <ErrorState message={error} />}
        <Input label="Name" value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} placeholder="Hay (Rhodes) bale" />
        <div className="grid grid-cols-2 gap-3"><Select label="Type" value={p.category} onChange={(e) => setP({ ...p, category: e.target.value })}>{["hay", "silage", "haylage", "straw", "green_chop", "other"].map((c) => <option key={c} value={c}>{c.replace("_", " ")}</option>)}</Select>
          <Input label="Counted in (bale, tonne…)" value={p.unit_label} onChange={(e) => setP({ ...p, unit_label: e.target.value })} /></div>
        <div className="grid grid-cols-2 gap-3"><Input label="Kg in one unit" type="number" min="0" step="any" value={p.kg_per_unit} onChange={(e) => setP({ ...p, kg_per_unit: e.target.value })} />
          <Input label="Warn when cover is under (days)" type="number" min="0" value={p.reorder_days} onChange={(e) => setP({ ...p, reorder_days: e.target.value })} /></div>
        <Button disabled={p.name.trim().length < 2 || !(Number(p.kg_per_unit) > 0) || mkProduct.isPending} onClick={() => mkProduct.mutate()}>Add product</Button></div></Modal>
      <Modal open={dlg === "price"} onClose={() => setDlg(null)} title={`Market price: ${priceFor?.name ?? ""}`}><div className="space-y-3">{error && <ErrorState message={error} />}
        <Input label="Price per kg (KES)" type="number" min="0" step="any" value={pr.price_per_kg} onChange={(e) => setPr({ ...pr, price_per_kg: e.target.value })} />
        <Input label="In force from" type="date" value={pr.effective_from} onChange={(e) => setPr({ ...pr, effective_from: e.target.value })} />
        <Input label="Source (optional)" value={pr.source} onChange={(e) => setPr({ ...pr, source: e.target.value })} placeholder="e.g. quote from Nanyuki supplier" />
        <p className="text-xs text-muted">Each harvest is valued at the price in force on its date, so enter a new price whenever the market moves. Earlier harvests keep their old value.</p>
        <Button disabled={!(Number(pr.price_per_kg) > 0) || mkPrice.isPending} onClick={() => mkPrice.mutate()}>Save price</Button></div></Modal>
      <Modal open={dlg === "plot"} onClose={() => setDlg(null)} title="New plot"><div className="space-y-3">{error && <ErrorState message={error} />}
        <Input label="Name" value={pl.name} onChange={(e) => setPl({ ...pl, name: e.target.value })} />
        <div className="grid grid-cols-2 gap-3"><Input label="Acres" type="number" min="0" step="any" value={pl.acres} onChange={(e) => setPl({ ...pl, acres: e.target.value })} />
          <Input label="Crop" value={pl.crop} onChange={(e) => setPl({ ...pl, crop: e.target.value })} placeholder="Lucerne, Napier…" /></div>
        <Select label="Sub-farm" value={pl.farm_id} onChange={(e) => setPl({ ...pl, farm_id: e.target.value })}><option value="">Not specified</option>{(farms.data ?? []).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</Select>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={pl.irrigated} onChange={(e) => setPl({ ...pl, irrigated: e.target.checked })} /> Irrigated</label>
        <Button disabled={!pl.name.trim() || !(Number(pl.acres) > 0) || mkPlot.isPending} onClick={() => mkPlot.mutate()}>Add plot</Button></div></Modal>
      <Modal open={dlg === "investment"} onClose={() => setDlg(null)} title="New investment"><div className="space-y-3">{error && <ErrorState message={error} />}
        <Input label="What is it?" value={iv.name} onChange={(e) => setIv({ ...iv, name: e.target.value })} placeholder="Land preparation, silage bunker, baler…" />
        <div className="grid grid-cols-2 gap-3"><Input label="Cost (KES)" type="number" min="0" value={iv.cost} onChange={(e) => setIv({ ...iv, cost: e.target.value })} />
          <Input label="Worth at the end (KES)" type="number" min="0" value={iv.salvage_value} onChange={(e) => setIv({ ...iv, salvage_value: e.target.value })} />
          <Input label="In use from" type="date" value={iv.in_service_on} onChange={(e) => setIv({ ...iv, in_service_on: e.target.value })} />
          <Input label="Useful life (years)" type="number" min="0" step="any" value={iv.life_years} onChange={(e) => setIv({ ...iv, life_years: e.target.value })} /></div>
        <Select label="Used by" value={iv.plot_id} onChange={(e) => setIv({ ...iv, plot_id: e.target.value })}><option value="">All plots (shared)</option>{(plots.data ?? []).map((x) => <option key={x.id} value={x.id}>Only {x.name}</option>)}</Select>
        {perDay != null && <p className="text-sm text-muted">Amortises at <b className="text-forest">KES {money(perDay, 2)} a day</b> (KES {money(perDay * 365)} a year).</p>}
        <Button disabled={iv.name.trim().length < 2 || !(Number(iv.cost) > 0) || !(Number(iv.life_years) > 0) || mkInv.isPending} onClick={() => mkInv.mutate()}>Add investment</Button></div></Modal>
    </div>
  );
}

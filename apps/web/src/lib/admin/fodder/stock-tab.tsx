"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, EmptyState, ErrorState, Input, Modal, Select } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useCan } from "@/lib/use-auth";
import { errMsg, money, StockRow, todayIso } from "./shared";

interface Movement { id: string; date: string; product: string; type: string; kg: number; value: number | null; destination: string | null; reason: string | null }
interface Customer { id: string; name: string }
type MType = "issue" | "loss" | "count" | "purchase" | "sale";
const LABEL: Record<MType, string> = { issue: "Feed out", loss: "Spoiled or lost", count: "Stock count", purchase: "Bought in", sale: "Sold" };

export function StockTab() {
  const qc = useQueryClient();
  const can = useCan();
  const [open, setOpen] = useState<MType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [f, setF] = useState({ product_id: "", date: todayIso(), qty: "", unit: "kg", value: "", destination: "", customer_id: "", reason: "", post: true });
  const stock = useQuery<StockRow[]>({ queryKey: ["fodder", "stock"], queryFn: () => apiFetch<StockRow[]>("/api/v1/fodder/stock") });
  const moves = useQuery<Movement[]>({ queryKey: ["fodder", "movements"], queryFn: () => apiFetch<Movement[]>("/api/v1/fodder/movements") });
  const customers = useQuery<Customer[]>({ queryKey: ["customers"], enabled: open === "sale", retry: false, queryFn: () => apiFetch<Customer[]>("/api/v1/customers") });
  const row = (stock.data ?? []).find((s) => s.product_id === f.product_id);
  const save = useMutation({
    mutationFn: () => apiFetch<{ difference_kg?: number; difference_pct?: number | null; status?: string; balance_kg?: number }>("/api/v1/fodder/movements", { method: "POST", body: JSON.stringify({
      product_id: f.product_id, movement_date: f.date, movement_type: open, ...(f.unit === "kg" ? { kg: Number(f.qty) } : { units: Number(f.qty) }),
      value: f.value ? Number(f.value) : undefined, destination_type: open === "issue" ? "other" : undefined, destination_label: f.destination || undefined,
      customer_id: f.customer_id || undefined, reason: f.reason || undefined, post_to_finance: f.post }) }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["fodder"] });
      qc.invalidateQueries({ queryKey: ["finance"] });
      setNotice(open === "count" ? (r.status === "no_difference" ? "Your count matches the records." : `Stock corrected by ${money(r.difference_kg ?? 0, 1)} kg (${r.difference_pct ?? "?"}%).`) : `Saved. ${money(r.balance_kg ?? 0)} kg now in stock.`);
      setOpen(null); setError(null); setF({ ...f, qty: "", value: "", reason: "" });
    },
    onError: (e) => setError(errMsg(e, "Could not save")),
  });
  const start = (t: MType) => { setError(null); setNotice(null); setF({ ...f, product_id: f.product_id || stock.data?.[0]?.product_id || "" }); setOpen(t); };
  const needsValue = open === "purchase" || open === "sale";
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => start("issue")}>Feed out</Button>
        <Button variant="ghost" onClick={() => start("loss")}>Spoiled / lost</Button>
        <Button variant="ghost" onClick={() => start("count")}>Stock count</Button>
        {can("fodder.manage") && <Button variant="ghost" onClick={() => start("purchase")}>Bought in</Button>}
        {can("fodder.manage") && <Button variant="ghost" onClick={() => start("sale")}>Sold</Button>}
        <span className="text-xs text-muted">Harvests are recorded on the cycle and add to stock automatically.</span>
      </div>
      {notice && <div className="rounded border border-forest/30 bg-forest/5 px-4 py-2 text-sm text-forest">{notice}</div>}
      {stock.data && stock.data.length === 0 && <EmptyState title="No fodder products" body="Add a product on the setup tab first." />}
      <div className="grid gap-4 md:grid-cols-3">
        {(stock.data ?? []).map((s) => (
          <Card key={s.product_id}><p className="text-sm text-muted">{s.name}</p><p className="font-display text-2xl text-forest">{money(s.balance_units, 1)} <span className="text-sm text-muted">{s.unit_label}s</span></p>
            <p className="text-xs text-muted">{money(s.balance_kg)} kg{s.days_of_cover != null ? ` · ${s.days_of_cover.toFixed(0)} days of cover` : ""}</p></Card>))}
      </div>
      <Card>
        <h2 className="mb-3 font-display text-lg text-forest">Recent movements</h2>
        {moves.error && <ErrorState message={errMsg(moves.error, "Failed to load movements")} />}
        <div className="overflow-x-auto"><table className="w-full text-sm"><tbody>
          {(moves.data ?? []).slice(0, 60).map((m) => (
            <tr key={m.id} className="border-b border-hairline/60"><td className="py-1.5">{m.date}</td><td>{m.product}</td><td className="capitalize">{m.type.replace("_", " ")}</td>
              <td className={`text-right ${m.kg < 0 ? "text-clay" : "text-forest"}`}>{m.kg > 0 ? "+" : ""}{money(m.kg)} kg</td><td className="text-right">{m.value != null ? `KES ${money(m.value)}` : ""}</td>
              <td className="text-xs text-muted">{m.destination ?? m.reason ?? ""}</td></tr>))}</tbody></table></div>
        <p className="mt-2 text-xs text-muted">Movements are never edited. A mistake is corrected with a stock count.</p>
      </Card>
      <Modal open={!!open} onClose={() => setOpen(null)} title={open ? LABEL[open] : ""}>
        <div className="space-y-3">
          {error && <ErrorState message={error} />}
          <Select label="Product" value={f.product_id} onChange={(e) => setF({ ...f, product_id: e.target.value })}>{(stock.data ?? []).map((s) => <option key={s.product_id} value={s.product_id}>{s.name} ({money(s.balance_kg)} kg in stock)</option>)}</Select>
          <div className="grid grid-cols-3 gap-3">
            <Input label="Date" type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} />
            <Input label={open === "count" ? "Counted" : "Quantity"} type="number" min="0" step="any" value={f.qty} onChange={(e) => setF({ ...f, qty: e.target.value })} />
            <Select label="In" value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })}><option value="kg">kg</option><option value="units">{row?.unit_label ?? "unit"}s</option></Select>
          </div>
          {open === "issue" && <Input label="Fed to" value={f.destination} onChange={(e) => setF({ ...f, destination: e.target.value })} placeholder="e.g. Feedlot batch 3, dairy herd" />}
          {needsValue && <Input label={open === "purchase" ? "Total price paid (KES)" : "Total sale value (KES)"} type="number" min="0" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} />}
          {open === "sale" && <Select label="Customer (leave empty for a cash sale)" value={f.customer_id} onChange={(e) => setF({ ...f, customer_id: e.target.value })}><option value="">Cash sale</option>{(customers.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>}
          {open === "purchase" && <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={f.post} onChange={(e) => setF({ ...f, post: e.target.checked })} /> Record the cost as a feed expense in Finance</label>}
          {(open === "loss" || open === "count") && <Input label="Reason / note" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} placeholder={open === "loss" ? "e.g. rain damage, rodents" : "optional"} />}
          {open === "count" && <p className="text-xs text-muted">Enter what you actually counted. The records are corrected to match and the difference is kept as a shrinkage figure.</p>}
          <Button disabled={!f.product_id || !(Number(f.qty) > 0) || (needsValue && !(Number(f.value) > 0)) || save.isPending} onClick={() => save.mutate()}>Save</Button>
        </div>
      </Modal>
    </div>
  );
}

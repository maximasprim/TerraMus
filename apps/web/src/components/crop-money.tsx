"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, ErrorState, Input, Modal, Select, Textarea } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import { useCan } from "@/lib/use-auth";
import type { CropCostRow, CropSaleResult, CropSaleRow, Customer, PlantingBreakdown } from "@/lib/types";

const kes = (v: string | number | null | undefined) =>
  v === null || v === undefined || v === "" ? "-" : `KES ${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
const qty = (v: string | number | null | undefined, unit?: string | null) =>
  `${Number(v ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ""}`;
const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);
const today = () => new Date().toISOString().slice(0, 10);

const COST_CATEGORIES: [string, string][] = [
  ["seed", "Seed / seedlings"], ["fertilizer", "Fertiliser"], ["chemicals", "Chemicals / pesticides"], ["labour", "Labour"],
  ["fuel", "Fuel"], ["transport", "Transport"], ["equipment", "Equipment"], ["maintenance", "Maintenance"],
  ["lease", "Land lease"], ["insurance", "Insurance"], ["utilities", "Water / utilities"], ["other_expense", "Other"],
];

export function CropMoneyTab({ plantingId }: { plantingId: string }) {
  const can = useCan();
  const queryClient = useQueryClient();
  const key = ["crop-planting", plantingId, "economics"];
  const { data, isLoading, error } = useQuery<PlantingBreakdown>({
    queryKey: key,
    queryFn: () => apiFetch<PlantingBreakdown>(`/api/v1/crops/${plantingId}/economics`),
  });
  const [open, setOpen] = useState<"sale" | "cost" | null>(null);
  const [voiding, setVoiding] = useState<{ kind: "sale" | "cost"; id: string; label: string } | null>(null);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["crop-planting", plantingId] });
    queryClient.invalidateQueries({ queryKey: ["profitability-crops"] });
  };

  if (isLoading) return <p className="text-sm text-muted">Loading…</p>;
  if (error || !data) return <ErrorState message={errMsg(error, "Failed to load the money view")} />;
  const s = data.summary;
  const profit = Number(s.profit);
  const canEdit = can("crops.update");

  return (
    <div className="space-y-4">
      {notice && (
        <div className={`rounded-md border p-3 text-sm ${notice.ok ? "border-forest/30 bg-forest/5 text-forest" : "border-amber-300 bg-amber-50 text-amber-900"}`}>
          {notice.text}
          <button className="float-right text-xs underline" onClick={() => setNotice(null)}>dismiss</button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Spent so far" value={kes(s.total_investment)} hint={`planting ${kes(s.acquisition_cost)} · inputs ${kes(s.input_cost)} · labour ${kes(s.labour_cost)} · other ${kes(s.other_cost)}`} />
        <Stat label="Sold so far" value={kes(s.total_revenue)} hint={`web ${kes(s.revenue_web)} · direct ${kes(s.revenue_direct)}`} />
        <Stat label={s.is_closed ? "Final profit / loss" : "Profit / loss so far"} value={kes(s.profit)} negative={profit < 0}
          hint={s.is_closed ? "This cycle is finished" : "A crop still growing shows its cost until it sells"} />
        <Stat label="Stock on hand" value={qty(s.stock_on_hand, s.unit)} negative={Number(s.stock_on_hand) < 0}
          hint={s.stock_value ? `about ${kes(s.stock_value)} at the listed price (an estimate, not counted as profit)` : `${qty(s.quantity_harvested, s.unit)} harvested`} />
      </div>
      {(s.avg_price_per_unit || s.cost_per_unit) && (
        <p className="text-xs text-muted">
          {s.avg_price_per_unit && <>Average selling price {kes(s.avg_price_per_unit)} per {s.unit ?? "unit"}. </>}
          {s.cost_per_unit && <>Cost to grow {kes(s.cost_per_unit)} per {s.unit ?? "unit"} harvested.</>}
        </p>
      )}

      {canEdit && (
        <div className="flex gap-2">
          <Button onClick={() => setOpen("sale")}>Record a sale</Button>
          <Button variant="ghost" onClick={() => setOpen("cost")}>Add a cost</Button>
        </div>
      )}

      <Card>
        <h2 className="mb-1 font-display text-lg text-forest">Sales made outside the web shop</h2>
        <p className="mb-3 text-xs text-muted">Sales through the web shop appear below automatically. A wrong entry is voided, not deleted, so the record stays honest.</p>
        {data.direct_sales.length === 0 ? <p className="text-sm text-muted">None recorded yet.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-muted"><tr>
                <th className="py-1 pr-3 font-medium">Date</th><th className="py-1 pr-3 font-medium">Quantity</th><th className="py-1 pr-3 font-medium">Price</th>
                <th className="py-1 pr-3 font-medium">Amount</th><th className="py-1 pr-3 font-medium">Buyer</th><th className="py-1 pr-3 font-medium">Finance</th><th />
              </tr></thead>
              <tbody>
                {data.direct_sales.map((r) => <SaleRow key={r.id} r={r} canEdit={canEdit} onVoid={() => setVoiding({ kind: "sale", id: r.id, label: `${qty(r.quantity, r.unit)} on ${r.sale_date}` })} />)}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {data.web_sales.length > 0 && (
        <Card>
          <h2 className="mb-3 font-display text-lg text-forest">Sales through the web shop</h2>
          <table className="w-full text-left text-sm"><tbody>
            {data.web_sales.map((w) => (
              <tr key={w.order_id + w.date} className="border-b border-hairline/60">
                <td className="py-1.5 pr-3">{w.date}</td><td className="pr-3">{qty(w.quantity, s.unit)}</td>
                <td className="pr-3 text-muted">{kes(w.unit_price)} each</td><td className="pr-3 font-medium">{kes(w.amount)}</td>
                <td className="text-xs capitalize text-muted">{w.status.replace(/_/g, " ")}</td>
              </tr>
            ))}
          </tbody></table>
        </Card>
      )}

      <Card>
        <h2 className="mb-3 font-display text-lg text-forest">Costs</h2>
        {data.costs.length === 0 ? <p className="text-sm text-muted">No costs recorded yet. The planting cost ({kes(s.acquisition_cost)}) is already counted above.</p> : (
          <table className="w-full text-left text-sm"><tbody>
            {data.costs.map((c) => <CostRow key={c.id} c={c} canEdit={canEdit} onVoid={() => setVoiding({ kind: "cost", id: c.id, label: `${c.category} ${kes(c.amount)} on ${c.cost_date}` })} />)}
          </tbody></table>
        )}
      </Card>

      <Modal open={open === "sale"} onClose={() => setOpen(null)} title="Record a sale">
        <SaleForm plantingId={plantingId} unit={s.unit ?? ""} onDone={(r) => {
          setOpen(null); refresh();
          setNotice({ ok: !r.stock_warning, text: `Sale recorded${r.ledger === "income_posted" ? " and added to Finance as income" : r.ledger === "charged_to_customer_account" ? " and charged to the customer's account" : " (not added to Finance)"}.${r.stock_warning ? " " + r.stock_warning : ""}` });
        }} />
      </Modal>
      <Modal open={open === "cost"} onClose={() => setOpen(null)} title="Add a cost">
        <CostForm plantingId={plantingId} onDone={() => { setOpen(null); refresh(); setNotice({ ok: true, text: "Cost recorded." }); }} />
      </Modal>
      <Modal open={!!voiding} onClose={() => setVoiding(null)} title={`Void ${voiding?.kind === "sale" ? "sale" : "cost"}`}>
        {voiding && <VoidForm target={voiding} onDone={() => { setVoiding(null); refresh(); setNotice({ ok: true, text: "Voided. Its Finance entry (if any) was reversed." }); }} />}
      </Modal>
    </div>
  );
}

function Stat({ label, value, hint, negative }: { label: string; value: string; hint?: string; negative?: boolean }) {
  return (
    <div className="rounded-lg border border-hairline bg-white/60 px-4 py-3">
      <span className="text-xs uppercase tracking-wider text-muted">{label}</span>
      <p className={`font-display text-xl ${negative ? "text-clay" : "text-forest"}`}>{value}</p>
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  );
}

function FinanceBadge({ inFinance, hasCustomer }: { inFinance: boolean; hasCustomer: boolean }) {
  if (inFinance) return <span className="rounded-full bg-forest/10 px-2 py-0.5 text-xs text-forest">{hasCustomer ? "On customer account" : "In Finance"}</span>;
  return <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800">Not in Finance</span>;
}

function SaleRow({ r, canEdit, onVoid }: { r: CropSaleRow; canEdit: boolean; onVoid: () => void }) {
  const voided = !!r.voided_at;
  return (
    <>
      <tr className={`border-b border-hairline/60 ${voided ? "text-muted line-through" : ""}`}>
        <td className="py-1.5 pr-3">{r.sale_date}</td><td className="pr-3">{qty(r.quantity, r.unit)}</td><td className="pr-3">{kes(r.unit_price)}</td>
        <td className="pr-3 font-medium">{kes(r.amount)}</td><td className="pr-3">{r.buyer_name ?? "-"}</td>
        <td className="pr-3 no-underline">{voided ? <span className="text-xs no-underline">Voided</span> : <FinanceBadge inFinance={r.in_finance} hasCustomer={!!r.customer_id} />}</td>
        <td className="text-right">{canEdit && !voided && <button className="text-xs text-clay underline" onClick={onVoid}>Void</button>}</td>
      </tr>
      {voided && <tr><td colSpan={7} className="pb-2 text-xs text-muted">Voided: {r.void_reason}</td></tr>}
    </>
  );
}

function CostRow({ c, canEdit, onVoid }: { c: CropCostRow; canEdit: boolean; onVoid: () => void }) {
  const voided = !!c.voided_at;
  return (
    <>
      <tr className={`border-b border-hairline/60 ${voided ? "text-muted line-through" : ""}`}>
        <td className="py-1.5 pr-3">{c.cost_date}</td>
        <td className="pr-3 capitalize">{COST_CATEGORIES.find(([k]) => k === c.category)?.[1] ?? c.category}</td>
        <td className="pr-3 text-muted">{c.description ?? ""}</td><td className="pr-3 font-medium">{kes(c.amount)}</td>
        <td className="pr-3 no-underline">{voided ? <span className="text-xs">Voided</span> : <FinanceBadge inFinance={c.in_finance} hasCustomer={false} />}</td>
        <td className="text-right">{canEdit && !voided && <button className="text-xs text-clay underline" onClick={onVoid}>Void</button>}</td>
      </tr>
      {voided && <tr><td colSpan={6} className="pb-2 text-xs text-muted">Voided: {c.void_reason}</td></tr>}
    </>
  );
}

function SaleForm({ plantingId, unit, onDone }: { plantingId: string; unit: string; onDone: (r: CropSaleResult) => void }) {
  const [f, setF] = useState({ sale_date: today(), quantity: "", unit, unit_price: "", amount: "", customer_id: "", buyer_name: "", notes: "", post: true });
  const [error, setError] = useState<string | null>(null);
  const customers = useQuery<Customer[]>({ queryKey: ["customers"], retry: false, queryFn: () => apiFetch<Customer[]>("/api/v1/customers") });
  const save = useMutation({
    mutationFn: () => apiFetch<CropSaleResult>(`/api/v1/crops/${plantingId}/sales`, {
      method: "POST",
      body: JSON.stringify({
        sale_date: f.sale_date, quantity: f.quantity, unit: f.unit || undefined,
        unit_price: f.unit_price || undefined, amount: f.amount || undefined,
        customer_id: f.customer_id || undefined, buyer_name: f.buyer_name || undefined, notes: f.notes || undefined,
        post_to_finance: f.post,
      }),
    }),
    onSuccess: onDone,
    onError: (e) => setError(errMsg(e, "Could not record the sale")),
  });
  const set = (k: string, v: string | boolean) => setF((p) => ({ ...p, [k]: v }));
  const total = f.amount ? Number(f.amount) : f.quantity && f.unit_price ? Number(f.quantity) * Number(f.unit_price) : null;
  return (
    <form onSubmit={(e) => { e.preventDefault(); setError(null); save.mutate(); }} className="space-y-3">
      {error && <ErrorState message={error} />}
      <div className="grid grid-cols-2 gap-3">
        <Input label="Date sold" type="date" required value={f.sale_date} onChange={(e) => set("sale_date", e.target.value)} />
        <Input label="Quantity" type="number" min="0" step="0.01" required value={f.quantity} onChange={(e) => set("quantity", e.target.value)} />
        <Input label="Unit" placeholder="kg, bags, crates…" value={f.unit} onChange={(e) => set("unit", e.target.value)} />
        <Input label="Price per unit (KES)" type="number" min="0" step="0.01" value={f.unit_price} onChange={(e) => set("unit_price", e.target.value)} />
      </div>
      <Input label="…or the total amount (KES)" type="number" min="0" step="0.01" value={f.amount} onChange={(e) => set("amount", e.target.value)} />
      {total !== null && !Number.isNaN(total) && <p className="text-xs text-muted">Total: <b>{kes(total)}</b></p>}
      <Select label="Sold to" value={f.customer_id} onChange={(e) => set("customer_id", e.target.value)}>
        <option value="">Cash sale (paid now)</option>
        {(customers.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name} (on credit)</option>)}
      </Select>
      <Input label="Buyer name (optional)" placeholder="e.g. Wakulima Traders" value={f.buyer_name} onChange={(e) => set("buyer_name", e.target.value)} />
      <Textarea label="Notes" value={f.notes} onChange={(e) => set("notes", e.target.value)} />
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-1" checked={f.post} onChange={(e) => set("post", e.target.checked)} />
        <span>Also record it in Finance{f.customer_id ? " (charged to the customer's account; income is recorded when they pay)" : " as income"}. Recorded once only.</span>
      </label>
      <Button type="submit" disabled={save.isPending || !f.quantity || (!f.unit_price && !f.amount)} className="w-full">{save.isPending ? "Saving…" : "Record sale"}</Button>
    </form>
  );
}

function CostForm({ plantingId, onDone }: { plantingId: string; onDone: () => void }) {
  const [f, setF] = useState({ cost_date: today(), category: "fertilizer", amount: "", description: "", post: true });
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => apiFetch(`/api/v1/crops/${plantingId}/costs`, {
      method: "POST",
      body: JSON.stringify({ cost_date: f.cost_date, category: f.category, amount: f.amount, description: f.description || undefined, post_to_finance: f.post }),
    }),
    onSuccess: onDone,
    onError: (e) => setError(errMsg(e, "Could not record the cost")),
  });
  const set = (k: string, v: string | boolean) => setF((p) => ({ ...p, [k]: v }));
  return (
    <form onSubmit={(e) => { e.preventDefault(); setError(null); save.mutate(); }} className="space-y-3">
      {error && <ErrorState message={error} />}
      <div className="grid grid-cols-2 gap-3">
        <Input label="Date" type="date" required value={f.cost_date} onChange={(e) => set("cost_date", e.target.value)} />
        <Input label="Amount (KES)" type="number" min="0" step="0.01" required value={f.amount} onChange={(e) => set("amount", e.target.value)} />
      </div>
      <Select label="Type of cost" value={f.category} onChange={(e) => set("category", e.target.value)}>
        {COST_CATEGORIES.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
      </Select>
      <Input label="Description (optional)" placeholder="e.g. CAN 50 kg, weeding crew" value={f.description} onChange={(e) => set("description", e.target.value)} />
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-1" checked={f.post} onChange={(e) => set("post", e.target.checked)} />
        <span>Also record it in Finance as an expense. Recorded once only.</span>
      </label>
      <Button type="submit" disabled={save.isPending || !f.amount} className="w-full">{save.isPending ? "Saving…" : "Add cost"}</Button>
    </form>
  );
}

function VoidForm({ target, onDone }: { target: { kind: "sale" | "cost"; id: string; label: string }; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => apiFetch(`/api/v1/crops/${target.kind === "sale" ? "sales" : "costs"}/${target.id}/void`, { method: "POST", body: JSON.stringify({ reason }) }),
    onSuccess: onDone,
    onError: (e) => setError(errMsg(e, "Could not void")),
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); setError(null); save.mutate(); }} className="space-y-3">
      {error && <ErrorState message={error} />}
      <p className="text-sm text-muted">Voiding <b>{target.label}</b> keeps the record (marked as voided) and reverses its Finance entry. It cannot be undone, but you can record the correct entry afterwards.</p>
      <Textarea label="Why is it being voided?" required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} />
      <Button type="submit" disabled={save.isPending || reason.trim().length < 3} className="w-full">{save.isPending ? "Voiding…" : "Void"}</Button>
    </form>
  );
}

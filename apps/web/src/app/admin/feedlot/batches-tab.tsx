"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, EmptyState, ErrorState, Input, Modal, Select } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { errMsg, FarmOption, FIELD, IntakeBatch, kes, parseTagLines, SaleBatch, todayIso } from "./shared";

interface RegisterResult { created: number; results: { animal_number: string; status: string; detail?: string }[] }

export function BatchesTab() {
  const qc = useQueryClient();
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [saleOpen, setSaleOpen] = useState(false);
  const [addFor, setAddFor] = useState<IntakeBatch | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reg, setReg] = useState<RegisterResult | null>(null);
  const [lines, setLines] = useState("");
  const [ib, setIb] = useState({ delivered_on: todayIso(), farm_id: "", source: "", sex_class: "bull", head_purchased: "", purchase_cost: "", transport_cost: "", other_fees: "", handlers_cost: "" });
  const [sb, setSb] = useState({ sold_on: todayIso(), price_per_kg: "", buyer_name: "" });

  const farms = useQuery<FarmOption[]>({ queryKey: ["farms"], queryFn: () => apiFetch<FarmOption[]>("/api/v1/farms") });
  const intake = useQuery<IntakeBatch[]>({ queryKey: ["feedlot", "batches"], queryFn: () => apiFetch<IntakeBatch[]>("/api/v1/feedlot/intake-batches") });
  const sales = useQuery<SaleBatch[]>({ queryKey: ["feedlot", "sale-batches"], queryFn: () => apiFetch<SaleBatch[]>("/api/v1/feedlot/sale-batches") });
  const refresh = () => qc.invalidateQueries({ queryKey: ["feedlot"] });

  const money = (v: string) => (v === "" ? "0" : v);
  const makeIntake = useMutation({
    mutationFn: () => apiFetch("/api/v1/feedlot/intake-batches", { method: "POST", body: JSON.stringify({
      delivered_on: ib.delivered_on, farm_id: ib.farm_id || undefined, source: ib.source || undefined, sex_class: ib.sex_class,
      head_purchased: Number(ib.head_purchased) || 0, purchase_cost: money(ib.purchase_cost), transport_cost: money(ib.transport_cost),
      other_fees: money(ib.other_fees), handlers_cost: money(ib.handlers_cost) }) }),
    onSuccess: () => { refresh(); setIntakeOpen(false); setError(null); },
    onError: (e) => setError(errMsg(e, "Could not create the batch")),
  });
  const makeSale = useMutation({
    mutationFn: () => apiFetch("/api/v1/feedlot/sale-batches", { method: "POST", body: JSON.stringify({
      sold_on: sb.sold_on, price_per_kg: sb.price_per_kg || undefined, buyer_name: sb.buyer_name || undefined }) }),
    onSuccess: () => { refresh(); setSaleOpen(false); setError(null); },
    onError: (e) => setError(errMsg(e, "Could not create the sale batch")),
  });
  const parsed = parseTagLines(lines);
  const register = useMutation({
    mutationFn: () => apiFetch<RegisterResult>(`/api/v1/feedlot/intake-batches/${addFor?.id}/animals`, { method: "POST", body: JSON.stringify({
      animals: parsed.rows.map((r) => ({ animal_number: r.tag, entry_weight_kg: r.weight })) }) }),
    onSuccess: (d) => { setReg(d); setError(null); refresh(); qc.invalidateQueries({ queryKey: ["livestock"] }); },
    onError: (e) => setError(errMsg(e, "Could not add the animals")),
  });

  const perHead = Number(ib.head_purchased) > 0
    ? (Number(money(ib.purchase_cost)) + Number(money(ib.transport_cost)) + Number(money(ib.other_fees)) + Number(money(ib.handlers_cost))) / Number(ib.head_purchased) : null;

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <Card>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-display text-lg text-forest">Intake batches</h2>
          <Button onClick={() => { setError(null); setIb({ ...ib, farm_id: ib.farm_id || farms.data?.[0]?.id || "" }); setIntakeOpen(true); }}>+ New intake batch</Button>
        </div>
        {intake.error && <ErrorState message={errMsg(intake.error, "Failed to load batches")} />}
        {intake.data && intake.data.length === 0 && <EmptyState title="No intake batches" body="Create one when a group of animals arrives, then add the animals with their entry weights." />}
        <div className="overflow-x-auto"><table className="w-full text-sm"><tbody>
          {(intake.data ?? []).map((b) => (
            <tr key={b.id} className="border-b border-hairline/60">
              <td className="py-2"><div className="font-medium">{b.name}</div><div className="text-xs text-muted">{b.delivered_on}{b.source ? ` · ${b.source}` : ""} · {b.sex_class}</div></td>
              <td className="text-right text-xs">{b.head_registered} of {b.head_purchased} added<div className="text-muted">KES {kes(b.landed_cost_per_head)} / head</div></td>
              <td className="text-right"><Button variant="ghost" onClick={() => { setError(null); setReg(null); setLines(""); setAddFor(b); }}>Add animals</Button></td>
            </tr>))}
        </tbody></table></div>
      </Card>

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-display text-lg text-forest">Sale batches</h2>
          <Button onClick={() => { setError(null); setSaleOpen(true); }}>+ New sale batch</Button>
        </div>
        {sales.error && <ErrorState message={errMsg(sales.error, "Failed to load sale batches")} />}
        {sales.data && sales.data.length === 0 && <EmptyState title="No sale batches" body="A sale batch is one dispatch day. Create it, then record the animals sold on the Sales & exits tab." />}
        <div className="overflow-x-auto"><table className="w-full text-sm"><tbody>
          {(sales.data ?? []).map((b) => (
            <tr key={b.id} className="border-b border-hairline/60">
              <td className="py-2"><div className="font-medium">Sale {b.batch_number}</div><div className="text-xs text-muted">{b.sold_on}{b.buyer_name ? ` · ${b.buyer_name}` : ""}</div></td>
              <td className="text-right text-xs">{b.price_per_kg ? `KES ${b.price_per_kg}/kg` : "no price set"}</td>
              <td className="text-right text-xs">{b.head_sold} sold<div className="text-muted">KES {kes(b.total_amount)}</div></td>
            </tr>))}
        </tbody></table></div>
      </Card>

      <Modal open={intakeOpen} onClose={() => setIntakeOpen(false)} title="New intake batch">
        <div className="space-y-3">
          {error && <ErrorState message={error} />}
          <div className="grid grid-cols-2 gap-3">
            <Input label="Delivered on" type="date" value={ib.delivered_on} onChange={(e) => setIb({ ...ib, delivered_on: e.target.value })} />
            <Select label="Sub-farm" value={ib.farm_id} onChange={(e) => setIb({ ...ib, farm_id: e.target.value })}>
              <option value="">Choose…</option>{(farms.data ?? []).map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
            </Select>
            <Input label="Source (e.g. Isiolo)" value={ib.source} onChange={(e) => setIb({ ...ib, source: e.target.value })} />
            <Select label="Animal class" value={ib.sex_class} onChange={(e) => setIb({ ...ib, sex_class: e.target.value })}>
              {["bull", "steer", "heifer", "mixed"].map((c) => <option key={c} value={c}>{c}</option>)}
            </Select>
          </div>
          <Input label="Head purchased" type="number" min="0" value={ib.head_purchased} onChange={(e) => setIb({ ...ib, head_purchased: e.target.value })} />
          <div className="grid grid-cols-2 gap-3">
            <Input label="Purchase cost (KES)" type="number" min="0" value={ib.purchase_cost} onChange={(e) => setIb({ ...ib, purchase_cost: e.target.value })} />
            <Input label="Transport (KES)" type="number" min="0" value={ib.transport_cost} onChange={(e) => setIb({ ...ib, transport_cost: e.target.value })} />
            <Input label="Other fees (KES)" type="number" min="0" value={ib.other_fees} onChange={(e) => setIb({ ...ib, other_fees: e.target.value })} />
            <Input label="Handlers (KES)" type="number" min="0" value={ib.handlers_cost} onChange={(e) => setIb({ ...ib, handlers_cost: e.target.value })} />
          </div>
          {perHead != null && <p className="text-sm text-muted">Landed cost per head: <b className="text-forest">KES {kes(perHead)}</b>. Every animal added carries this as its buying price.</p>}
          <Button disabled={!ib.farm_id || !(Number(ib.head_purchased) > 0) || makeIntake.isPending} onClick={() => makeIntake.mutate()}>Create batch</Button>
        </div>
      </Modal>

      <Modal open={saleOpen} onClose={() => setSaleOpen(false)} title="New sale batch">
        <div className="space-y-3">
          {error && <ErrorState message={error} />}
          <Input label="Sale date" type="date" value={sb.sold_on} onChange={(e) => setSb({ ...sb, sold_on: e.target.value })} />
          <Input label="Price per kg liveweight (KES)" type="number" min="0" step="any" value={sb.price_per_kg} onChange={(e) => setSb({ ...sb, price_per_kg: e.target.value })} />
          <Input label="Buyer (optional)" value={sb.buyer_name} onChange={(e) => setSb({ ...sb, buyer_name: e.target.value })} />
          <Button disabled={makeSale.isPending} onClick={() => makeSale.mutate()}>Create sale batch</Button>
        </div>
      </Modal>

      <Modal open={!!addFor} onClose={() => setAddFor(null)} title={`Add animals to ${addFor?.name ?? ""}`} size="lg">
        <div className="space-y-3">
          {error && <ErrorState message={error} />}
          <label className="block text-sm font-medium text-ink" htmlFor="addlines">One animal per line: tag, then entry weight in kg</label>
          <textarea id="addlines" rows={10} value={lines} onChange={(e) => { setLines(e.target.value); setReg(null); }} placeholder={"A01 210\nA02 200\nA03 190"} className={`${FIELD} font-mono`} />
          <p className="text-xs text-muted">{parsed.rows.length} animal(s) ready{parsed.bad.length > 0 && <span className="text-clay"> · cannot use: {parsed.bad.slice(0, 3).join(" | ")}</span>}. Tags that already exist are skipped, never duplicated.</p>
          <Button disabled={!parsed.rows.length || parsed.bad.length > 0 || register.isPending} onClick={() => register.mutate()}>{register.isPending ? "Adding…" : "Add animals"}</Button>
          {reg && (
            <div className="border-t border-hairline pt-3 text-sm">
              <p className="font-medium text-forest">{reg.created} animal(s) added</p>
              {reg.results.filter((r) => r.status !== "created").map((r) => (
                <p key={r.animal_number} className="text-xs text-clay"><span className="font-mono">{r.animal_number}</span>: {r.status}{r.detail ? ` - ${r.detail}` : ""}</p>))}
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}

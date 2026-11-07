"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, ErrorState, Input, Select } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { TagRowsEditor } from "@/components/tag-rows-editor";
import { analyseTagRows, blankTagRows, type TagRow } from "@/lib/tag-rows";
import { ActiveAnimal, errMsg, kes, SaleBatch, todayIso } from "./shared";

interface Customer { id: string; name: string }
interface SalesResult { sold: number; results: { animal: string; status: string; amount?: number; detail?: string }[] }
interface PerfList { animals: ActiveAnimal[] }

export function SalesTab() {
  const qc = useQueryClient();
  const [batchId, setBatchId] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [salesperson, setSalesperson] = useState("");
  const [rows, setRows] = useState<TagRow[]>(() => blankTagRows());
  const [attempted, setAttempted] = useState(false);
  const [result, setResult] = useState<SalesResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const batches = useQuery<SaleBatch[]>({ queryKey: ["feedlot", "sale-batches"], queryFn: () => apiFetch<SaleBatch[]>("/api/v1/feedlot/sale-batches") });
  const perf = useQuery<PerfList>({ queryKey: ["feedlot", "performance"], queryFn: () => apiFetch<PerfList>("/api/v1/feedlot/performance") });
  const customers = useQuery<Customer[]>({ queryKey: ["customers"], queryFn: () => apiFetch<Customer[]>("/api/v1/customers") });
  const active = useMemo(() => (perf.data?.animals ?? []).filter((a) => a.status === "active"), [perf.data]);
  const known = useMemo(() => new Set(active.map((a) => a.tag)), [active]);
  const batch = (batches.data ?? []).find((b) => b.id === batchId);
  const batchPrice = batch?.price_per_kg ? Number(batch.price_per_kg) : null;

  // One row per animal: Tag | Sale weight | Price per kg (optional - blank uses the sale batch's price).
  const analysis = useMemo(() => analyseTagRows(rows, { allowPrice: true }), [rows]);
  const preview = analysis.entries.map((r) => {
    const price = r.price ?? batchPrice;
    return { ...r, price, amount: price ? r.weight * price : null, unknown: !known.has(r.tag) };
  });
  const total = preview.reduce((s, r) => s + (r.amount ?? 0), 0);
  const blocked = !batchId || !preview.length || analysis.blocking > 0 || preview.some((r) => r.unknown || r.price == null);
  const byTag = new Map(preview.map((r) => [r.tag, r]));

  const sell = useMutation({
    mutationFn: () => apiFetch<SalesResult>(`/api/v1/feedlot/sale-batches/${batchId}/sales`, { method: "POST", body: JSON.stringify({
      entries: preview.map((r) => ({ animal_number: r.tag, exit_weight_kg: r.weight, price_per_kg: r.price ?? undefined,
        customer_id: customerId || undefined, salesperson: salesperson || undefined })) }) }),
    onSuccess: (d) => {
      setResult(d); setError(null); setRows(blankTagRows()); setAttempted(false);
      for (const k of ["feedlot", "receivables", "finance-summary", "finance-transactions", "livestock"]) qc.invalidateQueries({ queryKey: [k] });
    },
    onError: (e) => setError(errMsg(e, "Could not record the sales")),
  });

  return (
    <div className="grid gap-6 xl:grid-cols-5">
      <Card className="space-y-3 xl:col-span-3">
        <h2 className="font-display text-lg text-forest">Record sales</h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Select label="Sale batch" value={batchId} onChange={(e) => { setBatchId(e.target.value); setResult(null); }}>
            <option value="">Choose…</option>
            {(batches.data ?? []).map((b) => <option key={b.id} value={b.id}>Sale {b.batch_number} · {b.sold_on}</option>)}
          </Select>
          <Select label="Customer (credit sale)" value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
            <option value="">Cash sale / no customer</option>
            {(customers.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Input label="Salesperson" value={salesperson} onChange={(e) => setSalesperson(e.target.value)} />
        </div>
        {batch && <p className="text-xs text-muted">{batchPrice ? `Default price KES ${batchPrice}/kg for this batch (type a price on a row to override it).` : "This batch has no price: give a price on every row."}</p>}
        <TagRowsEditor
          idPrefix="sale" rows={rows} setRows={setRows} analysis={analysis} allowPrice
          weightLabel="Sale weight (kg)" weightPlaceholder="e.g. 324" priceLabel="Price per kg" pricePlaceholder={batchPrice ? `${batchPrice} (batch)` : "required"}
          pasteHelp="One animal per line: tag, sale weight (kg), optional price per kg (for example A02 331 335). Use a dot for decimals."
          showAllProblems={attempted} onEdit={() => setResult(null)}
          rowNote={(entry) => {
            const r = byTag.get(entry.tag);
            if (!r) return null;
            if (r.unknown) return { text: "not an active animal", error: true };
            if (r.price == null) return { text: "no price: type one, or choose a sale batch that has a price", error: true };
            return { text: `KES ${kes(r.amount)}` };
          }}
        />
        {error && <ErrorState message={error} />}
        <div className="flex items-center justify-between">
          <p className="text-sm">{preview.length} animal(s) · <b>KES {kes(total)}</b>{customerId ? " on the customer's account (unpaid)" : " as cash income"}</p>
          <Button disabled={sell.isPending || !batchId || !preview.length} onClick={() => {
            if (blocked) { setAttempted(true); setError("Fix the highlighted rows (or clear them) before recording the sales."); return; }
            sell.mutate();
          }}>{sell.isPending ? "Saving…" : "Record sales"}</Button>
        </div>
        {result && (
          <div className="border-t border-hairline pt-3 text-sm">
            <p className="font-medium text-forest">{result.sold} sold</p>
            {result.results.filter((r) => r.status !== "sold").map((r) => <p key={r.animal} className="text-xs text-clay"><span className="font-mono">{r.animal}</span>: {r.status}{r.detail ? ` - ${r.detail}` : ""}</p>)}
          </div>
        )}
      </Card>
      <CullCard animals={active} />
    </div>
  );
}

function CullCard({ animals }: { animals: ActiveAnimal[] }) {
  const qc = useQueryClient();
  const [animalId, setAnimalId] = useState("");
  const [type, setType] = useState("culled");
  const [date, setDate] = useState(todayIso());
  const [weight, setWeight] = useState("");
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const cull = useMutation({
    mutationFn: () => apiFetch(`/api/v1/feedlot/animals/${animalId}/cull`, { method: "POST", body: JSON.stringify({
      exit_type: type, exit_date: date, exit_weight_kg: weight ? Number(weight) : undefined, reason: reason || undefined }) }),
    onSuccess: () => {
      setMsg({ ok: true, text: "Recorded. Its cost now shows as a loss in profitability." }); setAnimalId(""); setReason(""); setWeight("");
      for (const k of ["feedlot", "livestock"]) qc.invalidateQueries({ queryKey: [k] });
    },
    onError: (e) => setMsg({ ok: false, text: errMsg(e, "Could not record") }),
  });
  return (
    <Card className="space-y-3 xl:col-span-2">
      <h2 className="font-display text-lg text-forest">Cull or mortality</h2>
      <p className="text-sm text-muted">An animal that leaves without a sale. Its purchase, feed and overhead cost is charged as a loss, not hidden.</p>
      <Select label="Animal" value={animalId} onChange={(e) => { setAnimalId(e.target.value); setMsg(null); }}>
        <option value="">Choose…</option>{animals.map((a) => <option key={a.animal_id} value={a.animal_id}>{a.tag}{a.latest_weight ? ` · ${a.latest_weight} kg` : ""}</option>)}
      </Select>
      <Select label="What happened?" value={type} onChange={(e) => setType(e.target.value)}>
        <option value="culled">Culled (removed as unfit)</option><option value="died">Died</option>
      </Select>
      <div className="grid grid-cols-2 gap-3">
        <Input label="Date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        <Input label="Weight (kg, optional)" type="number" min="0" step="any" value={weight} onChange={(e) => setWeight(e.target.value)} />
      </div>
      <Input label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. lame, pneumonia" />
      {msg && <p className={`text-sm ${msg.ok ? "text-forest" : "text-clay"}`}>{msg.text}</p>}
      <Button disabled={!animalId || cull.isPending} onClick={() => cull.mutate()}>Record</Button>
    </Card>
  );
}

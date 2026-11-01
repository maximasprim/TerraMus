"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, ErrorState, Input, Select } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { ActiveAnimal, errMsg, FIELD, kes, parseTagLines, SaleBatch, todayIso } from "./shared";

interface Customer { id: string; name: string }
interface SalesResult { sold: number; results: { animal: string; status: string; amount?: number; detail?: string }[] }
interface PerfList { animals: ActiveAnimal[] }

export function SalesTab() {
  const qc = useQueryClient();
  const [batchId, setBatchId] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [salesperson, setSalesperson] = useState("");
  const [lines, setLines] = useState("");
  const [result, setResult] = useState<SalesResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const batches = useQuery<SaleBatch[]>({ queryKey: ["feedlot", "sale-batches"], queryFn: () => apiFetch<SaleBatch[]>("/api/v1/feedlot/sale-batches") });
  const perf = useQuery<PerfList>({ queryKey: ["feedlot", "performance"], queryFn: () => apiFetch<PerfList>("/api/v1/feedlot/performance") });
  const customers = useQuery<Customer[]>({ queryKey: ["customers"], queryFn: () => apiFetch<Customer[]>("/api/v1/customers") });
  const active = useMemo(() => (perf.data?.animals ?? []).filter((a) => a.status === "active"), [perf.data]);
  const known = useMemo(() => new Set(active.map((a) => a.tag)), [active]);
  const batch = (batches.data ?? []).find((b) => b.id === batchId);
  const batchPrice = batch?.price_per_kg ? Number(batch.price_per_kg) : null;

  const parsed = parseTagLines(lines, true);
  const preview = parsed.rows.map((r) => {
    const price = r.price ?? batchPrice;
    return { ...r, price, amount: price ? r.weight * price : null, unknown: !known.has(r.tag) };
  });
  const total = preview.reduce((s, r) => s + (r.amount ?? 0), 0);
  const blocked = !batchId || !preview.length || parsed.bad.length > 0 || preview.some((r) => r.unknown || r.price == null);

  const sell = useMutation({
    mutationFn: () => apiFetch<SalesResult>(`/api/v1/feedlot/sale-batches/${batchId}/sales`, { method: "POST", body: JSON.stringify({
      entries: preview.map((r) => ({ animal_number: r.tag, exit_weight_kg: r.weight, price_per_kg: r.price ?? undefined,
        customer_id: customerId || undefined, salesperson: salesperson || undefined })) }) }),
    onSuccess: (d) => {
      setResult(d); setError(null); setLines("");
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
        {batch && <p className="text-xs text-muted">{batchPrice ? `Default price KES ${batchPrice}/kg for this batch (a third column on a line overrides it).` : "This batch has no price: give a price on every line."}</p>}
        <label className="block text-sm font-medium text-ink" htmlFor="saleLines">One animal per line: tag, sale weight (kg), optional price per kg</label>
        <textarea id="saleLines" rows={9} value={lines} onChange={(e) => { setLines(e.target.value); setResult(null); }} placeholder={"A01 324\nA02 331 335\nA03 318"} className={`${FIELD} font-mono`} />
        {error && <ErrorState message={error} />}
        {preview.length > 0 && (
          <div className="max-h-64 overflow-y-auto rounded border border-hairline">
            <table className="w-full text-sm"><tbody>{preview.map((r) => (
              <tr key={r.tag} className="border-b border-hairline/60">
                <td className="px-2 py-1 font-mono">{r.tag}</td><td className="text-right">{r.weight} kg</td>
                <td className="text-right">{r.price ?? "-"}</td><td className="px-2 text-right">{r.amount != null ? kes(r.amount) : "-"}</td>
                <td className="px-2 text-xs text-clay">{r.unknown ? "not an active animal" : r.price == null ? "no price" : ""}</td>
              </tr>))}</tbody></table>
          </div>
        )}
        {parsed.bad.length > 0 && <p className="text-xs text-clay">Cannot use: {parsed.bad.slice(0, 3).join(" | ")}</p>}
        <div className="flex items-center justify-between">
          <p className="text-sm">{preview.length} animal(s) · <b>KES {kes(total)}</b>{customerId ? " on the customer's account (unpaid)" : " as cash income"}</p>
          <Button disabled={blocked || sell.isPending} onClick={() => sell.mutate()}>{sell.isPending ? "Saving…" : "Record sales"}</Button>
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

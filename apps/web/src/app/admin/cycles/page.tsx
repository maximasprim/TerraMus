"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Button, Card, EmptyState, ErrorState, Input, Modal, Select, StatCard, Textarea } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import { useCycle } from "@/lib/cycle-context";
import { useCan } from "@/lib/use-auth";
import { ENTERPRISES, type AssignReport, type CompareRow, type CyclePreferences, type CycleSummary, type ProductionCycle } from "@/lib/cycle-types";

const money = (n: number | null | undefined) => (n === null || n === undefined ? "-" : new Intl.NumberFormat("en-KE", { maximumFractionDigits: 0 }).format(n));
const num = (n: number | null | undefined, d = 2) => (n === null || n === undefined ? "-" : n.toFixed(d));
const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);
const today = () => new Date().toISOString().slice(0, 10);
const STATUS_STYLE: Record<string, string> = {
  planned: "border-muted/30 bg-muted/10 text-muted",
  running: "border-moss/30 bg-moss/10 text-moss",
  closed: "border-forest/30 bg-forest/10 text-forest",
};
const Pill = ({ status }: { status: string }) => (
  <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[status] ?? ""}`}>{status}</span>
);
// every call on this page must see ALL data, whatever cycle is selected in the header
const raw = { cycleScope: false } as const;

export default function CyclesPage() {
  const qc = useQueryClient();
  const { cycleId, setCycleId } = useCycle();
  const [newOpen, setNewOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [closeFor, setCloseFor] = useState<ProductionCycle | null>(null);
  const [closeForce, setCloseForce] = useState(false);
  const [closeEnd, setCloseEnd] = useState(today());
  const [f, setF] = useState({ name: "", enterprise: "feedlot", start_date: "", notes: "" });

  const list = useQuery<ProductionCycle[]>({ queryKey: ["production-cycles"], queryFn: () => apiFetch<ProductionCycle[]>("/api/v1/production-cycles", raw) });
  const refresh = () => qc.invalidateQueries({ queryKey: ["production-cycles"] });

  const create = useMutation({
    mutationFn: () => apiFetch<ProductionCycle>("/api/v1/production-cycles", { ...raw, method: "POST", body: JSON.stringify({
      name: f.name || undefined, enterprise: f.enterprise, start_date: f.start_date || undefined, notes: f.notes || undefined,
      status: f.start_date && f.start_date <= today() ? "running" : "planned" }) }),
    onSuccess: (c) => { refresh(); setNewOpen(false); setError(null); setF({ name: "", enterprise: "feedlot", start_date: "", notes: "" }); setOpenId(c.id); },
    onError: (e) => setError(errMsg(e, "Could not create the cycle")),
  });
  const act = useMutation({
    mutationFn: ({ id, verb, body }: { id: string; verb: "start" | "close" | "reopen"; body?: object }) =>
      apiFetch<ProductionCycle>(`/api/v1/production-cycles/${id}/${verb}`, { ...raw, method: "POST", body: body ? JSON.stringify(body) : undefined }),
    onSuccess: () => { refresh(); qc.invalidateQueries({ queryKey: ["cycle-summary"] }); setCloseFor(null); setCloseForce(false); setError(null); },
    onError: (e) => setError(errMsg(e, "That did not work")),
  });
  const cycles = list.data ?? [];
  const open = cycles.find((c) => c.id === openId);

  return (
    <AdminShell>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl text-forest">Production cycles</h1>
          <p className="max-w-2xl text-sm text-muted">
            A cycle (&ldquo;Cycle 1&rdquo;, &ldquo;Cycle 2&rdquo;&hellip;) groups the bulls, money, customer balances, fuel, fodder and everything else that belongs to one run.
            Pick one in the sidebar and every list, total and report is narrowed to it.
          </p>
        </div>
        <Button onClick={() => { setError(null); setNewOpen(true); }}>+ New cycle</Button>
      </div>
      {error && !newOpen && !closeFor && <div className="mb-3"><ErrorState message={error} /></div>}
      {list.error && <ErrorState message={errMsg(list.error, "Failed to load production cycles")} />}
      {list.data && cycles.length === 0 && (
        <EmptyState title="No production cycles yet" body="Create Cycle 1, then use “Adopt existing records” to move your current batches and books into it. Nothing changes until you do." />
      )}

      {cycles.length > 0 && (
        <Card className="mb-6 overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-hairline text-left text-xs uppercase text-muted">
              <th className="w-8 px-3 py-2" /><th className="px-3">Cycle</th><th>Type</th><th>Status</th><th>Dates</th><th className="text-right">Bulls</th><th className="text-right">On feed</th><th className="px-3 text-right">Actions</th></tr></thead>
            <tbody>{cycles.map((c) => (
              <tr key={c.id} className={`border-b border-hairline/60 ${openId === c.id ? "bg-brass/5" : ""}`}>
                <td className="px-3 py-2"><input type="checkbox" aria-label={`Compare ${c.name}`} checked={picked.includes(c.id)}
                  onChange={(e) => setPicked(e.target.checked ? [...picked, c.id].slice(-6) : picked.filter((x) => x !== c.id))} /></td>
                <td className="px-3 font-medium">{c.name}{cycleId === c.id && <span className="ml-2 text-xs text-brass-dark">(selected)</span>}</td>
                <td className="capitalize">{c.enterprise}</td><td><Pill status={c.status} /></td>
                <td className="whitespace-nowrap text-xs text-muted">{c.start_date ?? "-"} → {c.end_date ?? (c.status === "closed" ? "-" : "open")}</td>
                <td className="text-right">{c.head_registered}</td><td className="text-right">{c.head_active}</td>
                <td className="whitespace-nowrap px-3 py-1.5 text-right">
                  <button className="mr-3 text-xs text-forest underline" onClick={() => setOpenId(openId === c.id ? null : c.id)}>{openId === c.id ? "Hide" : "Summary"}</button>
                  <button className="mr-3 text-xs text-forest underline" onClick={() => setCycleId(cycleId === c.id ? null : c.id)}>{cycleId === c.id ? "Unselect" : "Select"}</button>
                  {c.status === "planned" && <button className="mr-3 text-xs text-moss underline" onClick={() => act.mutate({ id: c.id, verb: "start" })}>Start</button>}
                  {c.status === "running" && <button className="text-xs text-clay underline" onClick={() => { setError(null); setCloseEnd(today()); setCloseFor(c); }}>Close</button>}
                  {c.status === "closed" && <button className="text-xs text-moss underline" onClick={() => act.mutate({ id: c.id, verb: "reopen" })}>Reopen</button>}
                </td></tr>))}</tbody>
          </table>
        </Card>
      )}

      <DefaultView />
      {picked.length >= 2 && <Compare ids={picked} />}
      {open && <CycleDetail cycle={open} onChanged={refresh} />}

      <Modal open={newOpen} onClose={() => setNewOpen(false)} title="New production cycle">
        <div className="space-y-3">
          {error && <ErrorState message={error} />}
          <Input label="Name (optional)" placeholder="Cycle 2" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          <div className="grid grid-cols-2 gap-3">
            <Select label="Type" value={f.enterprise} onChange={(e) => setF({ ...f, enterprise: e.target.value })}>
              {ENTERPRISES.map((x) => <option key={x} value={x}>{x}</option>)}</Select>
            <Input label="Start date" type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} />
          </div>
          <Textarea label="Notes" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />
          <p className="text-xs text-muted">Cycles can overlap: a new intake can arrive while the last bulls of the previous cycle are still being sold. Membership is chosen explicitly, never guessed from dates.</p>
          <Button disabled={create.isPending} onClick={() => create.mutate()}>Create cycle</Button>
        </div>
      </Modal>

      <Modal open={!!closeFor} onClose={() => setCloseFor(null)} title={`Close ${closeFor?.name ?? "cycle"}`}>
        <div className="space-y-3">
          {error && <ErrorState message={error} />}
          <p className="text-sm text-muted">Closing freezes this cycle&rsquo;s books: new weights, sales, culls and records can no longer be added to it until it is reopened. Late customer payments for its sales are still accepted. A snapshot of today&rsquo;s numbers is saved.</p>
          <Input label="End date" type="date" value={closeEnd} onChange={(e) => setCloseEnd(e.target.value)} />
          {closeFor && closeFor.head_active > 0 && (
            <label className="flex items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={closeForce} onChange={(e) => setCloseForce(e.target.checked)} />
              <span>{closeFor.head_active} animal(s) are still on feed in this cycle. Close anyway (they stay in the cycle).</span></label>)}
          <Button disabled={act.isPending || (!!closeFor && closeFor.head_active > 0 && !closeForce)}
            onClick={() => closeFor && act.mutate({ id: closeFor.id, verb: "close", body: { end_date: closeEnd, force: closeForce } })}>Close cycle</Button>
        </div>
      </Modal>
    </AdminShell>
  );
}

// ------------------------------------------------------------------ optional: open on the running cycle
function DefaultView() {
  const qc = useQueryClient();
  const can = useCan();
  const [err, setErr] = useState<string | null>(null);
  const q = useQuery<CyclePreferences>({ queryKey: ["production-cycles", "preferences", "page"], queryFn: () => apiFetch<CyclePreferences>("/api/v1/production-cycles/preferences", raw) });
  const save = useMutation({
    mutationFn: (view: "all" | "running") => apiFetch<CyclePreferences>("/api/v1/production-cycles/preferences", { ...raw, method: "PATCH", body: JSON.stringify({ default_view: view }) }),
    onSuccess: () => { setErr(null); qc.invalidateQueries({ queryKey: ["production-cycles", "preferences"] }); },
    onError: (e) => setErr(errMsg(e, "Could not save that setting")),
  });
  if (!q.data) return null;
  const on = q.data.default_view === "running";
  return (
    <Card className="mb-6">
      <label className="flex items-start gap-2 text-sm">
        <input className="mt-1" type="checkbox" checked={on} disabled={!can("cycles.manage") || save.isPending} onChange={(e) => save.mutate(e.target.checked ? "running" : "all")} />
        <span>
          <strong>Open on the running cycle by default</strong>
          <span className="block text-muted">
            For people who haven&rsquo;t picked a cycle themselves, the console opens already filtered to the running cycle instead of all cycles. Anyone can still switch to another cycle or to &ldquo;All cycles&rdquo;, and their choice is remembered.
            {on && (q.data.default_cycle_id ? " Right now that is the one running cycle." : q.data.running_cycles === 0 ? " No cycle is running, so everyone sees all cycles." : ` ${q.data.running_cycles} cycles are running, so the console stays on all cycles (it won't guess).`)}
            {!can("cycles.manage") && " Only people who can manage cycles can change this."}
          </span>
        </span>
      </label>
      {err && <div className="mt-2"><ErrorState message={err} /></div>}
    </Card>
  );
}

// ------------------------------------------------------------------ summary + adoption for one cycle
function CycleDetail({ cycle, onChanged }: { cycle: ProductionCycle; onChanged: () => void }) {
  const [shared, setShared] = useState(false);
  const s = useQuery<CycleSummary>({
    queryKey: ["cycle-summary", cycle.id, shared],
    queryFn: () => apiFetch<CycleSummary>(`/api/v1/production-cycles/${cycle.id}/summary?include_shared=${shared}`, raw),
  });
  const d = s.data;
  return (
    <div className="mb-6 space-y-4">
      <h2 className="font-display text-xl text-forest">{cycle.name} <span className="ml-1 align-middle"><Pill status={cycle.status} /></span></h2>
      {s.error && <ErrorState message={errMsg(s.error, "Could not load the summary")} />}
      {d && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="Bulls" value={String(d.feedlot.head)} hint={`${d.feedlot.active} on feed · ${d.feedlot.sold} sold · ${d.feedlot.culled + d.feedlot.died} lost (${d.feedlot.loss_rate_pct}%)`} />
            <StatCard label="Profit (KES)" value={money(d.feedlot.profit)} hint={`${money(d.feedlot.profit_per_head)} per head sold`} />
            <StatCard label="Avg daily gain" value={`${num(d.feedlot.avg_adg, 3)} kg`} hint={`cost per kg gained: ${num(d.feedlot.cost_per_kg_gain)}`} />
            <StatCard label="Owed by customers" value={money(d.receivables.outstanding)} hint={`charged ${money(d.receivables.charged)} · collected ${money(d.receivables.collected)}`} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <h3 className="mb-2 font-display text-lg text-forest">Feedlot economics</h3>
              <Rows rows={[["Revenue", d.feedlot.revenue], ["Bulls (landed cost)", d.feedlot.landed_cost], ["Feed", d.feedlot.feed_cost], ["Operations / overhead", d.feedlot.ops_cost],
                ["Total cost", d.feedlot.total_cost], ["Profit", d.feedlot.profit]]} />
              <p className="mt-2 text-xs text-muted">{d.feedlot.head_realised} sold or lost, {d.feedlot.head_open} still open (projected profit on those: KES {money(d.feedlot.unrealised_projected_profit)}).</p>
            </Card>
            <Card>
              <h3 className="mb-2 flex items-center justify-between font-display text-lg text-forest">Money in the books
                <label className="text-xs font-normal text-muted"><input type="checkbox" className="mr-1" checked={shared} onChange={(e) => setShared(e.target.checked)} />estimate shared costs</label></h3>
              <Rows rows={[["Income", d.finance.income], ["Expenses", d.finance.expense], ["Net", d.finance.net]]} />
              {d.finance.shared_in_window && (
                <p className="mt-2 rounded bg-amber-50 p-2 text-xs text-amber-900">
                  Not included above: KES {money(d.finance.shared_in_window.expense)} of expenses dated {d.finance.shared_in_window.from} to {d.finance.shared_in_window.to} that are in no cycle (salaries, lease&hellip;).
                  {d.finance.shared_in_window.estimated_share_of_expense !== undefined && <> Estimated share for this cycle: <strong>KES {money(d.finance.shared_in_window.estimated_share_of_expense)}</strong> ({d.finance.shared_in_window.method}).</>}
                </p>)}
              <TopList title="Expenses by category" data={d.finance.expense_by_category} />
            </Card>
          </div>
          <Card>
            <h3 className="mb-2 font-display text-lg text-forest">Other activity tagged to this cycle</h3>
            <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
              <Chip t="Fuel" v={`${money(d.fuel.litres)} L · KES ${money(d.fuel.cost)}`} />
              <Chip t="Flocks / fish" v={`${d.groups.groups} groups · ${d.groups.current_count} head`} />
              <Chip t="Fodder" v={`${d.fodder.plantings} plantings · ${money(d.fodder.harvested_kg)} kg · KES ${money(d.fodder.total_cost)}`} />
              <Chip t="Crops" v={`${d.crops.plantings} plantings · ${d.crops.area} area`} />
              <Chip t="Training" v={`${d.training.sessions} sessions · ${d.training.participants} people`} />
              <Chip t="Stock consumed" v={`KES ${money(d.inventory.consumption_value)}`} />
              <Chip t="Purchase orders" v={`${d.procurement.purchase_orders} · KES ${money(d.procurement.value)}`} />
            </div>
          </Card>
          {d.feedlot.by_intake_batch.length > 0 && (
            <Card className="overflow-x-auto">
              <h3 className="mb-2 font-display text-lg text-forest">By intake batch</h3>
              <table className="w-full text-sm"><thead><tr className="border-b border-hairline text-left text-xs uppercase text-muted"><th className="py-1">Batch</th><th className="text-right">Bulls</th><th className="text-right">Sold</th><th className="text-right">On feed</th><th className="text-right">Profit</th><th className="text-right">Per head</th><th className="text-right">ADG</th><th className="text-right">Loss %</th></tr></thead>
                <tbody>{d.feedlot.by_intake_batch.map((b) => <tr key={b.intake_batch} className="border-b border-hairline/60"><td className="py-1">{b.intake_batch}</td><td className="text-right">{b.head_total}</td><td className="text-right">{b.head_sold}</td><td className="text-right">{b.head_active}</td><td className="text-right">{money(b.profit)}</td><td className="text-right">{money(b.profit_per_head)}</td><td className="text-right">{num(b.avg_adg, 3)}</td><td className="text-right">{b.loss_rate_pct}</td></tr>)}</tbody></table>
            </Card>)}
        </>
      )}
      {cycle.status !== "closed" && <Adopt cycle={cycle} onDone={() => { onChanged(); s.refetch(); }} />}
    </div>
  );
}

const Rows = ({ rows }: { rows: [string, number][] }) => (
  <table className="w-full text-sm"><tbody>{rows.map(([k, v]) => (
    <tr key={k} className="border-b border-hairline/60"><td className="py-1">{k}</td><td className={`text-right ${v < 0 ? "text-clay" : ""}`}>KES {money(v)}</td></tr>))}</tbody></table>
);
const TopList = ({ title, data }: { title: string; data: Record<string, number> }) => {
  const top = Object.entries(data).slice(0, 5);
  return top.length ? <div className="mt-3"><p className="text-xs font-medium uppercase text-muted">{title}</p>
    <ul className="text-sm">{top.map(([k, v]) => <li key={k} className="flex justify-between"><span className="capitalize">{k.replace(/_/g, " ")}</span><span>KES {money(v)}</span></li>)}</ul></div> : null;
};
const Chip = ({ t, v }: { t: string; v: string }) => <div className="rounded border border-hairline bg-paper px-3 py-2"><p className="text-xs uppercase text-muted">{t}</p><p>{v}</p></div>;

// ------------------------------------------------------------------ compare
function Compare({ ids }: { ids: string[] }) {
  const q = useQuery<{ cycles: CompareRow[] }>({
    queryKey: ["cycle-compare", ids.join(",")],
    queryFn: () => apiFetch(`/api/v1/production-cycles/compare?ids=${ids.join(",")}`, raw),
  });
  const rows = q.data?.cycles ?? [];
  const line = (label: string, get: (r: CompareRow) => string) => (
    <tr className="border-b border-hairline/60"><td className="py-1.5 pr-4 text-muted">{label}</td>{rows.map((r) => <td key={r.id} className="text-right">{get(r)}</td>)}</tr>);
  return (
    <Card className="mb-6 overflow-x-auto">
      <h2 className="mb-2 font-display text-lg text-forest">Cycle comparison</h2>
      {q.error && <ErrorState message={errMsg(q.error, "Could not compare these cycles")} />}
      {rows.length > 0 && (
        <table className="w-full text-sm"><thead><tr className="border-b border-hairline text-xs uppercase text-muted"><th className="py-1 text-left" />{rows.map((r) => <th key={r.id} className="text-right">{r.name}</th>)}</tr></thead>
          <tbody>
            {line("Status", (r) => r.status)}{line("Days", (r) => String(r.days ?? "-"))}{line("Bulls", (r) => String(r.head))}{line("Sold", (r) => String(r.sold))}
            {line("Loss rate %", (r) => String(r.loss_rate_pct))}{line("Avg daily gain (kg)", (r) => num(r.avg_adg, 3))}{line("Avg days on farm", (r) => num(r.avg_days_on_farm, 0))}
            {line("Cost per kg gained", (r) => num(r.cost_per_kg_gain))}{line("Revenue", (r) => money(r.revenue))}{line("Total cost", (r) => money(r.total_cost))}
            {line("Profit", (r) => money(r.profit))}{line("Profit per head", (r) => money(r.profit_per_head))}{line("Margin %", (r) => num(r.margin_pct, 1))}
            {line("Ledger net", (r) => money(r.ledger_net))}{line("Owed by customers", (r) => money(r.outstanding_receivables))}
          </tbody></table>)}
    </Card>
  );
}

// ------------------------------------------------------------------ adopt existing records
interface BatchRow { id: string; batch_number: number; name: string; delivered_on: string; production_cycle_id: string | null; head_registered: number }
const KINDS: [string, string][] = [["finance", "Finance entries"], ["receivables", "Customer account entries"], ["fuel", "Fuel logs"], ["groups", "Flocks / fish"], ["fodder_cycles", "Fodder plantings"],
  ["fodder_movements", "Fodder stock movements"], ["crops", "Crop plantings"], ["training", "Training sessions"], ["inventory", "Inventory movements"], ["purchase_orders", "Purchase orders"]];

function Adopt({ cycle, onDone }: { cycle: ProductionCycle; onDone: () => void }) {
  const qc = useQueryClient();
  const [openPanel, setOpenPanel] = useState(false);
  const [batches, setBatches] = useState<string[]>([]);
  const [useDates, setUseDates] = useState(false);
  const [from, setFrom] = useState(cycle.start_date ?? "");
  const [to, setTo] = useState(cycle.end_date ?? today());
  const [kinds, setKinds] = useState<string[]>(["finance"]);
  const [report, setReport] = useState<AssignReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const all = useQuery<BatchRow[]>({ queryKey: ["cycle-adopt-batches"], enabled: openPanel, queryFn: () => apiFetch<BatchRow[]>("/api/v1/feedlot/intake-batches", raw) });
  const unassigned = useQuery<Record<string, number>>({ queryKey: ["cycle-unassigned"], enabled: openPanel, queryFn: () => apiFetch("/api/v1/production-cycles/unassigned", raw) });
  const candidates = (all.data ?? []).filter((b) => b.production_cycle_id !== cycle.id);

  const run = useMutation({
    mutationFn: (dry: boolean) => apiFetch<AssignReport>(`/api/v1/production-cycles/${cycle.id}/assign`, { ...raw, method: "POST", body: JSON.stringify({
      intake_batch_ids: batches, dry_run: dry,
      by_date: useDates && from && to ? { from_date: from, to_date: to, tables: kinds } : undefined }) }),
    onSuccess: (r) => {
      setReport(r); setError(null);
      if (!r.dry_run) { qc.resetQueries({ predicate: (q) => !["me", "catalog", "production-cycles"].includes(String(q.queryKey[0])) }); setBatches([]); onDone(); }
    },
    onError: (e) => setError(errMsg(e, "Could not assign those records")),
  });
  const nothing = batches.length === 0 && !(useDates && from && to);

  return (
    <Card>
      <button className="font-display text-lg text-forest" onClick={() => setOpenPanel(!openPanel)}>{openPanel ? "▾" : "▸"} Adopt existing records into {cycle.name}</button>
      {openPanel && (
        <div className="mt-3 space-y-4">
          <p className="text-sm text-muted">
            Putting an intake batch into a cycle brings <strong>everything that traces to its bulls</strong> with it - weights, sales, purchase and sale entries in Finance, customer balances, feed and vet costs - instantly, without rewriting any ledger row.
            Other records (manual expenses, fuel, flocks&hellip;) can be tagged by date window; a record that already has a cycle is never moved by that tool. Always preview first.
          </p>
          {all.data && (
            <div>
              <p className="mb-1 text-sm font-medium">Intake batches</p>
              {candidates.length === 0 ? <p className="text-sm text-muted">Every batch is already in this cycle.</p> : (
                <ul className="max-h-48 space-y-1 overflow-y-auto text-sm">{candidates.map((b) => (
                  <li key={b.id}><label className="flex items-center gap-2"><input type="checkbox" checked={batches.includes(b.id)} onChange={(e) => setBatches(e.target.checked ? [...batches, b.id] : batches.filter((x) => x !== b.id))} />
                    {b.name} · {b.head_registered} bulls · delivered {b.delivered_on}{b.production_cycle_id && <span className="text-xs text-brass-dark"> (currently in another cycle)</span>}</label></li>))}</ul>)}
            </div>)}
          <div>
            <label className="flex items-center gap-2 text-sm font-medium"><input type="checkbox" checked={useDates} onChange={(e) => setUseDates(e.target.checked)} /> Also tag untagged records dated within a window</label>
            {useDates && (
              <div className="mt-2 space-y-2">
                <div className="grid grid-cols-2 gap-3"><Input label="From" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /><Input label="To" type="date" value={to} onChange={(e) => setTo(e.target.value)} /></div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">{KINDS.map(([k, label]) => (
                  <label key={k} className="flex items-center gap-1"><input type="checkbox" checked={kinds.includes(k)} onChange={(e) => setKinds(e.target.checked ? [...kinds, k] : kinds.filter((x) => x !== k))} />
                    {label}{unassigned.data ? <span className="text-xs text-muted"> ({unassigned.data[k] ?? 0} untagged)</span> : null}</label>))}</div>
              </div>)}
          </div>
          {error && <ErrorState message={error} />}
          <div className="flex gap-2">
            <Button disabled={nothing || run.isPending} onClick={() => run.mutate(true)}>Preview</Button>
            <Button disabled={nothing || run.isPending || !report?.dry_run} onClick={() => run.mutate(false)}>Apply</Button>
          </div>
          {report && (
            <div className="rounded border border-hairline bg-paper p-3 text-sm">
              <p className="font-medium">{report.dry_run ? "Preview - nothing changed yet" : "Done"}</p>
              <ul className="mt-1 list-disc pl-5">
                {report.intake_batches.length > 0 && <li>{report.intake_batches.length} intake batch(es) {report.dry_run ? "would move" : "moved"} into {report.cycle}</li>}
                {Object.entries(report.tagged).filter(([, v]) => v.records > 0).map(([k, v]) => <li key={k}>{v.records} {v.label.toLowerCase()} {report.dry_run ? "would be tagged" : "tagged"}</li>)}
                {report.skipped.map((s) => <li key={s.id} className="text-muted">Batch {s.batch}: {s.reason}</li>)}
              </ul>
            </div>)}
        </div>)}
    </Card>
  );
}

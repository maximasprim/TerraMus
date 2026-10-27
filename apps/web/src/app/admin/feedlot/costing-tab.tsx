"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, EmptyState, ErrorState, Input, Modal, Select } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { errMsg, FIELD, kes } from "./shared";

type Kind = "settings" | "recipe" | "enterprise_budget" | "ration_plan" | "overhead_pool" | "land_use";
interface Doc { id: string; kind: Kind; name: string; data: Record<string, unknown>; computed: Record<string, number | Record<string, number> | number[]> | null }

const KINDS: { kind: Kind; title: string; blurb: string }[] = [
  { kind: "ration_plan", title: "Ration plans", blurb: "Feed per day by stage, priced from your recipes and budgets. Drives the standard feed cost per animal." },
  { kind: "recipe", title: "Feed recipes", blurb: "Ingredients and quantities for a batch of feed; gives cost per kg." },
  { kind: "enterprise_budget", title: "Fodder budgets", blurb: "Yearly cost of producing hay, silage etc. (with amortised items) and the yield; gives cost per unit and per kg." },
  { kind: "overhead_pool", title: "Overhead pool", blurb: "Operating costs shared by all animals, allocated per bull-day." },
  { kind: "settings", title: "Thresholds", blurb: "Market-ready weight and the ADG colour bands." },
  { kind: "land_use", title: "Land use", blurb: "Acres by activity and site (stored as data)." },
];
const num = (s: string) => (s.trim() === "" ? 0 : Number(s));
const str = (v: unknown) => (v == null ? "" : String(v));
const FEEDS = ["silage", "hay", "concentrate"] as const;

function headline(d: Doc): string {
  const c = d.computed as Record<string, number> | null;
  if (!c) return "";
  if (d.kind === "recipe") return `KES ${c.cost_per_kg?.toFixed(2)} per kg · batch KES ${kes(c.total_cost)}`;
  if (d.kind === "enterprise_budget") return `${c.cost_per_kg != null ? `KES ${c.cost_per_kg.toFixed(2)}/kg · ` : ""}KES ${c.cost_per_unit?.toFixed(2)} per unit · KES ${kes(c.total_cost_per_year)}/yr`;
  if (d.kind === "ration_plan") return `${c.total_days} days · KES ${kes(c.total_cost)} per animal · avg KES ${c.avg_cost_per_day}/day`;
  if (d.kind === "overhead_pool") return `KES ${kes(c.total)} total · KES ${kes(c.per_head)} per head`;
  return "";
}

export function CostingTab() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<{ kind: Kind; doc: Doc | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const docs = useQuery<Doc[]>({ queryKey: ["feedlot", "costing"], queryFn: () => apiFetch<Doc[]>("/api/v1/feedlot/costing") });
  const save = useMutation({
    mutationFn: (v: { kind: Kind; doc: Doc | null; name: string; data: Record<string, unknown> }) =>
      v.doc ? apiFetch(`/api/v1/feedlot/costing/${v.doc.id}`, { method: "PATCH", body: JSON.stringify({ name: v.name, data: v.data }) })
            : apiFetch("/api/v1/feedlot/costing", { method: "POST", body: JSON.stringify({ kind: v.kind, name: v.name, data: v.data }) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["feedlot"] }); setEditing(null); setError(null); },
    onError: (e) => setError(errMsg(e, "Could not save")),
  });
  const remove = useMutation({
    mutationFn: (id: string) => apiFetch(`/api/v1/feedlot/costing/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feedlot"] }),
    onError: (e) => setError(errMsg(e, "Could not delete")),
  });
  const all = docs.data ?? [];
  return (
    <div className="space-y-6">
      <p className="text-sm text-muted">These documents drive feed cost, overhead and profit. Change a price here and every profit figure follows; nothing is typed into formulas by hand.</p>
      {error && !editing && <ErrorState message={error} />}
      {docs.error && <ErrorState message={errMsg(docs.error, "Failed to load")} />}
      {KINDS.map(({ kind, title, blurb }) => {
        const items = all.filter((d) => d.kind === kind);
        const canAdd = !(kind === "settings" && items.length > 0);
        return (
          <Card key={kind}>
            <div className="mb-2 flex items-start justify-between gap-4">
              <div><h2 className="font-display text-lg text-forest">{title}</h2><p className="text-xs text-muted">{blurb}</p></div>
              {canAdd && <Button variant="ghost" onClick={() => { setError(null); setEditing({ kind, doc: null }); }}>+ Add</Button>}
            </div>
            {items.length === 0 && <p className="text-sm text-muted">{kind === "settings" ? "Using the defaults (300 kg market-ready; ADG bands 0.2 / 0.4 / 0.7)." : "None yet."}</p>}
            {items.map((d) => (
              <div key={d.id} className="flex items-center justify-between gap-3 border-t border-hairline/60 py-2 text-sm">
                <div><div className="font-medium">{d.name}</div><div className="text-xs text-muted">{headline(d)}</div></div>
                <div className="flex gap-2">
                  <Button variant="ghost" onClick={() => { setError(null); setEditing({ kind, doc: d }); }}>Edit</Button>
                  <Button variant="ghost" disabled={remove.isPending} onClick={() => { if (window.confirm(`Delete "${d.name}"? Profit figures that use it will change.`)) remove.mutate(d.id); }}>Delete</Button>
                </div>
              </div>))}
          </Card>
        );
      })}
      {editing && (
        <Modal open onClose={() => setEditing(null)} title={`${editing.doc ? "Edit" : "New"} ${KINDS.find((k) => k.kind === editing.kind)?.title.toLowerCase()}`} size="lg">
          {error && <ErrorState message={error} />}
          <Editor kind={editing.kind} doc={editing.doc} all={all} busy={save.isPending}
            onSave={(name, data) => save.mutate({ kind: editing.kind, doc: editing.doc, name, data })} />
        </Modal>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ editors
type Col<T> = { key: keyof T & string; label: string; number?: boolean; options?: string[]; w?: string };
function Rows<T extends Record<string, string>>({ rows, setRows, cols, blank, addLabel }: { rows: T[]; setRows: (r: T[]) => void; cols: Col<T>[]; blank: T; addLabel: string }) {
  const set = (i: number, k: string, v: string) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <div className="space-y-1">
      <div className="flex gap-2 text-xs uppercase text-muted">{cols.map((c) => <div key={c.key} className={c.w ?? "flex-1"}>{c.label}</div>)}<div className="w-6" /></div>
      {rows.map((r, i) => (
        <div key={i} className="flex gap-2">
          {cols.map((c) => c.options
            ? <select key={c.key} className={`${FIELD} ${c.w ?? "flex-1"}`} value={r[c.key]} onChange={(e) => set(i, c.key, e.target.value)}>{c.options.map((o) => <option key={o} value={o}>{o}</option>)}</select>
            : <input key={c.key} aria-label={c.label} className={`${FIELD} ${c.w ?? "flex-1"}`} type={c.number ? "number" : "text"} step="any" value={r[c.key]} onChange={(e) => set(i, c.key, e.target.value)} />)}
          <button type="button" aria-label="Remove row" className="w-6 text-clay" onClick={() => setRows(rows.filter((_, j) => j !== i))}>×</button>
        </div>))}
      <Button variant="ghost" onClick={() => setRows([...rows, blank])}>+ {addLabel}</Button>
    </div>
  );
}

function Editor({ kind, doc, all, busy, onSave }: { kind: Kind; doc: Doc | null; all: Doc[]; busy: boolean; onSave: (name: string, data: Record<string, unknown>) => void }) {
  switch (kind) {
    case "recipe": return <RecipeEditor doc={doc} busy={busy} onSave={onSave} />;
    case "enterprise_budget": return <BudgetEditor doc={doc} busy={busy} onSave={onSave} />;
    case "ration_plan": return <RationEditor doc={doc} all={all} busy={busy} onSave={onSave} />;
    case "overhead_pool": return <OverheadEditor doc={doc} busy={busy} onSave={onSave} />;
    case "settings": return <SettingsEditor doc={doc} busy={busy} onSave={onSave} />;
    default: return <JsonEditor doc={doc} busy={busy} onSave={onSave} />;
  }
}
type EP = { doc: Doc | null; busy: boolean; onSave: (name: string, data: Record<string, unknown>) => void };

function RecipeEditor({ doc, busy, onSave }: EP) {
  const d = (doc?.data ?? {}) as { ingredients?: { name: string; quantity_kg: number; price_per_kg: number }[]; fixed_costs?: { name: string; amount: number }[] };
  const [name, setName] = useState(doc?.name ?? "");
  const [ing, setIng] = useState((d.ingredients ?? []).map((i) => ({ name: i.name, qty: str(i.quantity_kg), price: str(i.price_per_kg) })));
  const [fixed, setFixed] = useState((d.fixed_costs ?? []).map((f) => ({ name: f.name, amount: str(f.amount) })));
  const qty = ing.reduce((s, i) => s + num(i.qty), 0);
  const total = ing.reduce((s, i) => s + num(i.qty) * num(i.price), 0) + fixed.reduce((s, f) => s + num(f.amount), 0);
  return (
    <div className="space-y-4">
      <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Concentrate (1 tonne)" />
      <p className="text-sm font-medium">Ingredients</p>
      <Rows rows={ing} setRows={setIng} blank={{ name: "", qty: "", price: "" }} addLabel="Ingredient"
        cols={[{ key: "name", label: "Ingredient" }, { key: "qty", label: "Quantity (kg)", number: true, w: "w-28" }, { key: "price", label: "Price / kg", number: true, w: "w-28" }]} />
      <p className="text-sm font-medium">Other costs per batch (transport, preparation…)</p>
      <Rows rows={fixed} setRows={setFixed} blank={{ name: "", amount: "" }} addLabel="Cost"
        cols={[{ key: "name", label: "Item" }, { key: "amount", label: "Amount (KES)", number: true, w: "w-32" }]} />
      <p className="text-sm">Batch {qty.toFixed(1)} kg · total KES {kes(total)} · <b className="text-forest">KES {qty ? (total / qty).toFixed(2) : "-"} per kg</b></p>
      <Button disabled={busy || !name.trim() || !ing.length} onClick={() => onSave(name.trim(), {
        ingredients: ing.filter((i) => i.name.trim()).map((i) => ({ name: i.name.trim(), quantity_kg: num(i.qty), price_per_kg: num(i.price) })),
        fixed_costs: fixed.filter((f) => f.name.trim()).map((f) => ({ name: f.name.trim(), amount: num(f.amount) })) })}>Save recipe</Button>
    </div>
  );
}

function BudgetEditor({ doc, busy, onSave }: EP) {
  const d = (doc?.data ?? {}) as { yield_per_year?: number; yield_unit?: string; unit_weight_kg?: number; acres?: number; assumptions?: string[];
    lines?: { item: string; amount: number; multiply_by?: number; divide_by?: number }[] };
  const [name, setName] = useState(doc?.name ?? "");
  const [yld, setYld] = useState(str(d.yield_per_year));
  const [unit, setUnit] = useState(d.yield_unit ?? "kg");
  const [uw, setUw] = useState(str(d.unit_weight_kg));
  const [acres, setAcres] = useState(str(d.acres));
  const [notes, setNotes] = useState((d.assumptions ?? []).join("\n"));
  const [lines, setLines] = useState((d.lines ?? []).map((l) => ({ item: l.item, amount: str(l.amount), mult: str(l.multiply_by ?? 1), div: str(l.divide_by ?? 1) })));
  const perYear = lines.reduce((s, l) => s + num(l.amount) * (num(l.mult) || 1) / (num(l.div) || 1), 0);
  const perUnit = num(yld) ? perYear / num(yld) : null;
  return (
    <div className="space-y-4">
      <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Perennial - Hay (per acre)" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Input label="Yield per year" type="number" min="0" step="any" value={yld} onChange={(e) => setYld(e.target.value)} />
        <Input label="Yield unit" value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="kg or bale" />
        <Input label="Kg per unit (bales)" type="number" min="0" step="any" value={uw} onChange={(e) => setUw(e.target.value)} />
        <Input label="Acres (for silage blend)" type="number" min="0" step="any" value={acres} onChange={(e) => setAcres(e.target.value)} />
      </div>
      <p className="text-sm font-medium">Cost lines <span className="font-normal text-muted">(spread over years with ÷, or repeated per year with ×; e.g. land preparation ÷ 5)</span></p>
      <Rows rows={lines} setRows={setLines} blank={{ item: "", amount: "", mult: "1", div: "1" }} addLabel="Cost line"
        cols={[{ key: "item", label: "Item" }, { key: "amount", label: "Amount", number: true, w: "w-28" }, { key: "mult", label: "× per year", number: true, w: "w-20" }, { key: "div", label: "÷ years", number: true, w: "w-20" }]} />
      <div><label className="mb-1 block text-sm font-medium" htmlFor="notes">Assumptions (one per line, optional)</label><textarea id="notes" rows={3} className={FIELD} value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
      <p className="text-sm">Cost per year KES {kes(perYear)}{perUnit != null && <> · <b className="text-forest">KES {perUnit.toFixed(2)} per {unit || "unit"}</b>{num(uw) ? ` · KES ${(perUnit / num(uw)).toFixed(2)} per kg` : ""}</>}</p>
      <Button disabled={busy || !name.trim() || !(num(yld) > 0) || !lines.length} onClick={() => onSave(name.trim(), {
        yield_per_year: num(yld), yield_unit: unit || "kg", ...(num(uw) ? { unit_weight_kg: num(uw) } : {}), ...(num(acres) ? { acres: num(acres) } : {}),
        assumptions: notes.split("\n").map((s) => s.trim()).filter(Boolean),
        lines: lines.filter((l) => l.item.trim()).map((l) => ({ item: l.item.trim(), amount: num(l.amount), multiply_by: num(l.mult) || 1, divide_by: num(l.div) || 1 })) })}>Save budget</Button>
    </div>
  );
}

type Mode = "manual" | "recipe" | "enterprise_budget" | "blend" | "fodder";
function RationEditor({ doc, all, busy, onSave }: EP & { all: Doc[] }) {
  const d = (doc?.data ?? {}) as { stages?: { label?: string; days: number; feeds?: Record<string, number> }[]; feed_costs?: Record<string, number>;
    cost_links?: Record<string, { kind: Mode; name?: string; names?: string[] }> };
  const budgets = all.filter((x) => x.kind === "enterprise_budget").map((x) => x.name);
  const recipes = all.filter((x) => x.kind === "recipe").map((x) => x.name);
  // Our own fodder stock, priced at its real average cost (needs the Fodder module; absent or forbidden = just no option)
  const fodderQ = useQuery<{ name: string }[]>({ queryKey: ["fodder", "products", "names"], retry: false, queryFn: () => apiFetch<{ name: string }[]>("/api/v1/fodder/products?active_only=true") });
  const fodderNames = fodderQ.data?.map((x) => x.name) ?? [];
  const [name, setName] = useState(doc?.name ?? "");
  const [stages, setStages] = useState((d.stages ?? [{ label: "Stage 1", days: 30, feeds: {} }]).map((s) => ({
    label: s.label ?? "", days: str(s.days), silage: str(s.feeds?.silage ?? 0), hay: str(s.feeds?.hay ?? 0), concentrate: str(s.feeds?.concentrate ?? 0) })));
  const [mode, setMode] = useState<Record<string, Mode>>(Object.fromEntries(FEEDS.map((f) => [f, (d.cost_links?.[f]?.kind as Mode) ?? "manual"])));
  const [manual, setManual] = useState<Record<string, string>>(Object.fromEntries(FEEDS.map((f) => [f, str(d.feed_costs?.[f] ?? "")])));
  const [pick, setPick] = useState<Record<string, string>>(Object.fromEntries(FEEDS.map((f) => [f, d.cost_links?.[f]?.name ?? ""])));
  const [blend, setBlend] = useState<string[]>(d.cost_links?.silage?.names ?? []);
  const days = stages.reduce((s, x) => s + num(x.days), 0);
  const build = () => {
    const links: Record<string, unknown> = {}; const costs: Record<string, number> = {};
    for (const f of FEEDS) {
      if (mode[f] === "manual") costs[f] = num(manual[f]);
      else if (mode[f] === "blend") links[f] = { kind: "blend", names: blend };
      else links[f] = { kind: mode[f], name: pick[f] };
    }
    return { stages: stages.map((s) => ({ label: s.label || undefined, days: Math.round(num(s.days)),
      feeds: { silage: num(s.silage), hay: num(s.hay), concentrate: num(s.concentrate) } })), feed_costs: costs, cost_links: links };
  };
  const linkOk = FEEDS.every((f) => mode[f] === "manual" ? num(manual[f]) > 0 : mode[f] === "blend" ? blend.length > 0 : !!pick[f]);
  return (
    <div className="space-y-4">
      <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Fattening ration" />
      <p className="text-sm font-medium">Stages <span className="font-normal text-muted">(kg of each feed per animal per day)</span></p>
      <Rows rows={stages} setRows={setStages} blank={{ label: "", days: "30", silage: "0", hay: "0", concentrate: "0" }} addLabel="Stage"
        cols={[{ key: "label", label: "Stage" }, { key: "days", label: "Days", number: true, w: "w-16" }, { key: "silage", label: "Silage", number: true, w: "w-20" }, { key: "hay", label: "Hay", number: true, w: "w-20" }, { key: "concentrate", label: "Concentrate", number: true, w: "w-24" }]} />
      <p className="text-xs text-muted">{days} days in total. An animal kept longer keeps eating the last stage.</p>
      <p className="text-sm font-medium">Where each feed's price per kg comes from</p>
      {FEEDS.map((f) => (
        <div key={f} className="grid grid-cols-3 items-end gap-2">
          <span className="pb-2 text-sm capitalize">{f}</span>
          <Select label="Source" value={mode[f]} onChange={(e) => setMode({ ...mode, [f]: e.target.value as Mode })}>
            <option value="manual">A fixed price</option><option value="recipe">A feed recipe</option>
            <option value="enterprise_budget">A fodder budget</option><option value="blend">A blend of fodder budgets</option>
            {(fodderNames.length > 0 || mode[f] === "fodder") && <option value="fodder">Our fodder stock (actual cost)</option>}
          </Select>
          {mode[f] === "manual" && <Input label="KES per kg" type="number" min="0" step="any" value={manual[f]} onChange={(e) => setManual({ ...manual, [f]: e.target.value })} />}
          {(mode[f] === "recipe" || mode[f] === "enterprise_budget" || mode[f] === "fodder") && (
            <Select label="Which" value={pick[f]} onChange={(e) => setPick({ ...pick, [f]: e.target.value })}>
              <option value="">Choose…</option>{(mode[f] === "recipe" ? recipes : mode[f] === "fodder" ? fodderNames : budgets).map((n) => <option key={n} value={n}>{n}</option>)}
            </Select>)}
          {mode[f] === "blend" && (
            <div className="text-xs">{budgets.length === 0 ? "Add fodder budgets first" : budgets.map((n) => (
              <label key={n} className="mr-3 inline-flex items-center gap-1"><input type="checkbox" checked={blend.includes(n)} onChange={(e) => setBlend(e.target.checked ? [...blend, n] : blend.filter((x) => x !== n))} />{n}</label>))}</div>)}
        </div>))}
      <Button disabled={busy || !name.trim() || !stages.length || days <= 0 || !linkOk} onClick={() => onSave(name.trim(), build())}>Save ration plan</Button>
    </div>
  );
}

function OverheadEditor({ doc, busy, onSave }: EP) {
  const d = (doc?.data ?? {}) as { lines?: { item: string; amount: number; behaviour?: string }[]; heads?: number; cycle_days?: number; rate_mode?: string; fixed_rate?: number };
  const [name, setName] = useState(doc?.name ?? "");
  const [lines, setLines] = useState((d.lines ?? []).map((l) => ({ item: l.item, amount: str(l.amount), behaviour: l.behaviour ?? "fixed" })));
  const [heads, setHeads] = useState(str(d.heads));
  const [cycle, setCycle] = useState(str(d.cycle_days));
  const [mode, setMode] = useState(d.rate_mode ?? "bull_days");
  const [fixed, setFixed] = useState(str(d.fixed_rate));
  const total = lines.reduce((s, l) => s + num(l.amount), 0);
  return (
    <div className="space-y-4">
      <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Bull fattening operations" />
      <Rows rows={lines} setRows={setLines} blank={{ item: "", amount: "", behaviour: "fixed" }} addLabel="Cost"
        cols={[{ key: "item", label: "Cost" }, { key: "amount", label: "Amount (KES)", number: true, w: "w-32" }, { key: "behaviour", label: "Behaviour", options: ["fixed", "variable", "step", "semi-variable"], w: "w-36" }]} />
      <p className="text-sm">Total KES {kes(total)}</p>
      <div className="grid grid-cols-2 gap-3">
        <Input label="Head in the cycle (for the planned rate)" type="number" min="0" value={heads} onChange={(e) => setHeads(e.target.value)} />
        <Input label="Cycle length (days)" type="number" min="0" value={cycle} onChange={(e) => setCycle(e.target.value)} />
      </div>
      <Select label="How it is shared" value={mode} onChange={(e) => setMode(e.target.value)}>
        <option value="bull_days">Total ÷ actual bull-days (recommended: fully allocated, never over or under charged)</option>
        <option value="fixed">A fixed rate per bull per day</option>
      </Select>
      {mode === "fixed" && <Input label="KES per bull per day" type="number" min="0" step="any" value={fixed} onChange={(e) => setFixed(e.target.value)} />}
      <Button disabled={busy || !name.trim() || !lines.length || (mode === "fixed" && !(num(fixed) > 0))} onClick={() => onSave(name.trim(), {
        lines: lines.filter((l) => l.item.trim()).map((l) => ({ item: l.item.trim(), amount: num(l.amount), behaviour: l.behaviour })),
        heads: num(heads), cycle_days: num(cycle), rate_mode: mode, ...(mode === "fixed" ? { fixed_rate: num(fixed) } : {}) })}>Save overhead pool</Button>
    </div>
  );
}

const SETTING_FIELDS: { key: string; label: string; hint: string }[] = [
  { key: "market_ready_kg", label: "Market-ready weight (kg)", hint: "weights at or above this turn green" },
  { key: "adg_poor_max", label: "Poor ADG at or below", hint: "red" },
  { key: "adg_target_min", label: "On-target ADG from", hint: "green" },
  { key: "adg_target_max", label: "On-target ADG up to", hint: "above this is excellent (cyan)" },
  { key: "interval_gain_good", label: "Good interval gain over (kg)", hint: "cyan" },
  { key: "day_offset", label: "Days-on-farm adjustment", hint: "days on farm = date difference minus this (your worksheet uses 1)" },
  { key: "reference_price_per_kg", label: "Reference price per kg (KES)", hint: "projects the value of animals not yet sold" },
  { key: "implausible_gain_kg_per_day", label: "Flag gains above (kg/day)", hint: "catches mistyped weights" },
];
function SettingsEditor({ doc, busy, onSave }: EP) {
  const d = (doc?.data ?? {}) as Record<string, number>;
  const [v, setV] = useState<Record<string, string>>(Object.fromEntries(SETTING_FIELDS.map((f) => [f.key, str(d[f.key] ?? "")])));
  return (
    <div className="space-y-3">
      {SETTING_FIELDS.map((f) => <Input key={f.key} label={f.label} type="number" step="any" value={v[f.key]} onChange={(e) => setV({ ...v, [f.key]: e.target.value })} />)}
      <p className="text-xs text-muted">Leave a box empty to keep the default. {SETTING_FIELDS.map((f) => `${f.label}: ${f.hint}`).join(" · ")}</p>
      <Button disabled={busy} onClick={() => onSave("default", Object.fromEntries(SETTING_FIELDS.filter((f) => v[f.key] !== "").map((f) => [f.key, num(v[f.key])])))}>Save thresholds</Button>
    </div>
  );
}

function JsonEditor({ doc, busy, onSave }: EP) {
  const [name, setName] = useState(doc?.name ?? "Land use (acres)");
  const [text, setText] = useState(JSON.stringify(doc?.data ?? { unit: "acres", sites: [], rows: [] }, null, 2));
  let parsed: Record<string, unknown> | null = null;
  try { const p: unknown = JSON.parse(text); parsed = p && typeof p === "object" && !Array.isArray(p) ? (p as Record<string, unknown>) : null; } catch { parsed = null; }
  return (
    <div className="space-y-3">
      <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} />
      <textarea aria-label="Data (JSON)" rows={12} className={`${FIELD} font-mono`} value={text} onChange={(e) => setText(e.target.value)} />
      {!parsed && <p className="text-xs text-clay">This is not valid JSON yet.</p>}
      <Button disabled={busy || !parsed || !name.trim()} onClick={() => parsed && onSave(name.trim(), parsed)}>Save</Button>
    </div>
  );
}

"use client";

import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, EmptyState, ErrorState, Input, Modal, Select } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { errMsg, FIELD, kes } from "./shared";

type Kind = "settings" | "recipe" | "enterprise_budget" | "ration_plan" | "overhead_pool" | "land_use";
interface Doc { id: string; kind: Kind; name: string; data: Record<string, unknown>; computed: Record<string, number | Record<string, number> | number[]> | null }

const KINDS: { kind: Kind; title: string; single: string; blurb: string }[] = [
  { kind: "ration_plan", title: "Ration plans", single: "ration plan", blurb: "Feed per day by stage, priced from your recipes and budgets. Drives the standard feed cost per animal." },
  { kind: "recipe", title: "Feed recipes", single: "feed recipe", blurb: "Ingredients and quantities for a batch of feed; gives cost per kg." },
  { kind: "enterprise_budget", title: "Fodder budgets", single: "fodder budget", blurb: "Yearly cost of producing hay, silage etc. (with amortised items) and the yield; gives cost per unit and per kg." },
  { kind: "overhead_pool", title: "Overhead pool", single: "overhead pool", blurb: "Operating costs shared by all animals, allocated per bull-day." },
  { kind: "settings", title: "Thresholds", single: "thresholds", blurb: "Market-ready weight and the ADG colour bands." },
  { kind: "land_use", title: "Land use", single: "land use", blurb: "Acres by activity and site (stored as data)." },
];
const num = (s: string) => (s.trim() === "" ? 0 : Number(s));
const str = (v: unknown) => (v == null ? "" : String(v));
const FEEDS = ["silage", "hay", "concentrate"] as const;
const FEED_LABEL: Record<string, string> = { silage: "Silage", hay: "Hay", concentrate: "Concentrate" };

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
        <Modal open onClose={() => setEditing(null)} title={`${editing.doc ? "Edit" : "New"} ${KINDS.find((k) => k.kind === editing.kind)?.single}`} size="lg">
          {error && <ErrorState message={error} />}
          <Editor kind={editing.kind} doc={editing.doc} all={all} busy={save.isPending}
            onSave={(name, data) => save.mutate({ kind: editing.kind, doc: editing.doc, name, data })} />
        </Modal>
      )}
    </div>
  );
}

// -------------------------------------------------------- shared form pieces
/** A short plain-language "what is this form for" box at the top of every modal. */
function Intro({ children }: { children: ReactNode }) {
  return <div className="rounded border border-hairline bg-white/60 p-3 text-sm text-ink">{children}</div>;
}
/** A titled block of a form, optionally numbered, with a line of help under the title. */
function Section({ n, title, help, children }: { n?: number; title: string; help?: ReactNode; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <div><h3 className="text-sm font-semibold text-ink">{n ? `${n}. ` : ""}{title}</h3>{help && <p className="text-xs text-muted">{help}</p>}</div>
      {children}
    </section>
  );
}
const Hint = ({ children }: { children: ReactNode }) => <p className="mt-1 text-xs text-muted">{children}</p>;

/** Name box with a plain label and an example that is clearly an example (not a filled-in value). */
function NameField({ label, example, help, value, onChange }: { label: string; example: string; help: string; value: string; onChange: (v: string) => void }) {
  return (<div><Input label={label} value={value} onChange={(e) => onChange(e.target.value)} placeholder={`e.g. ${example}`} /><Hint>{help}</Hint></div>);
}

/** Save button that says, in words, what is still missing while it is greyed out. */
function SaveBar({ busy, missing, label, notes, onClick }: { busy: boolean; missing: string[]; label: string; notes?: string[]; onClick: () => void }) {
  return (
    <div className="space-y-2 border-t border-hairline pt-3">
      {missing.length > 0 && <p className="text-xs text-clay">Before you can save: {missing.join("; ")}.</p>}
      {(notes ?? []).map((n) => <p key={n} className="text-xs text-muted">{n}</p>)}
      <Button disabled={busy || missing.length > 0} onClick={onClick}>{busy ? "Saving…" : label}</Button>
    </div>
  );
}

// A table of repeatable lines. Headings and boxes share ONE grid, so each heading always sits exactly over its box.
type Opt = string | { value: string; label: string };
type Col<T> = { key: keyof T & string; label: string; number?: boolean; options?: Opt[]; fr?: number; placeholder?: string };
type Calc<T> = { label: string; fr?: number; calc: (r: T) => string };
function Rows<T extends Record<string, string>>({ rows, setRows, cols, calc, blank, addLabel, empty }: {
  rows: T[]; setRows: (r: T[]) => void; cols: Col<T>[]; calc?: Calc<T>; blank: T; addLabel: string; empty?: string;
}) {
  const set = (i: number, k: string, v: string) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const widths = [...cols.map((c) => c.fr ?? 1), ...(calc ? [calc.fr ?? 1] : [])];
  const template = `${widths.map((w) => `minmax(0, ${w}fr)`).join(" ")} 1.5rem`;
  const minWidth = `${Math.max(widths.reduce((a, b) => a + b, 0) * 4.5, 20)}rem`;
  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <div className="space-y-1" style={{ minWidth }}>
          {rows.length > 0 && (
            <div className="grid items-end gap-2 text-xs font-medium text-muted" style={{ gridTemplateColumns: template }}>
              {cols.map((c) => <div key={c.key}>{c.label}</div>)}
              {calc && <div className="text-right">{calc.label}</div>}
              <div />
            </div>)}
          {rows.map((r, i) => (
            <div key={i} className="grid items-center gap-2" style={{ gridTemplateColumns: template }}>
              {cols.map((c) => c.options
                ? <select key={c.key} aria-label={c.label} className={FIELD} value={r[c.key]} onChange={(e) => set(i, c.key, e.target.value)}>
                    {c.options.map((o) => typeof o === "string" ? <option key={o} value={o}>{o}</option> : <option key={o.value} value={o.value}>{o.label}</option>)}</select>
                : <input key={c.key} aria-label={c.label} placeholder={c.placeholder} className={FIELD} type={c.number ? "number" : "text"} step="any" value={r[c.key]} onChange={(e) => set(i, c.key, e.target.value)} />)}
              {calc && <div className="text-right text-sm tabular-nums text-muted">{calc.calc(r)}</div>}
              <button type="button" aria-label="Remove this line" title="Remove this line" className="text-clay" onClick={() => setRows(rows.filter((_, j) => j !== i))}>×</button>
            </div>))}
        </div>
      </div>
      {rows.length === 0 && empty && <p className="text-xs text-muted">{empty}</p>}
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
    case "land_use": return <LandUseEditor doc={doc} busy={busy} onSave={onSave} />;
    default: return <JsonEditor doc={doc} busy={busy} onSave={onSave} />;
  }
}
type EP = { doc: Doc | null; busy: boolean; onSave: (name: string, data: Record<string, unknown>) => void };

// -------------------------------------------------------------- feed recipe
function RecipeEditor({ doc, busy, onSave }: EP) {
  const d = (doc?.data ?? {}) as { ingredients?: { name: string; quantity_kg: number; price_per_kg: number }[]; fixed_costs?: { name: string; amount: number }[] };
  const [name, setName] = useState(doc?.name ?? "");
  const [ing, setIng] = useState((d.ingredients ?? []).map((i) => ({ name: i.name, qty: str(i.quantity_kg), price: str(i.price_per_kg) })));
  const [fixed, setFixed] = useState((d.fixed_costs ?? []).map((f) => ({ name: f.name, amount: str(f.amount) })));
  const qty = ing.reduce((s, i) => s + num(i.qty), 0);
  const total = ing.reduce((s, i) => s + num(i.qty) * num(i.price), 0) + fixed.reduce((s, f) => s + num(f.amount), 0);
  const missing = [...(!name.trim() ? ["give the recipe a name"] : []), ...(!ing.length ? ["add at least one ingredient"] : [])];
  const unnamed = ing.filter((i) => !i.name.trim()).length + fixed.filter((f) => !f.name.trim()).length;
  return (
    <div className="space-y-5">
      <Intro>A recipe works out what a feed costs <b>per kg</b> from what goes into it, for example your concentrate mix. Describe <b>one batch</b> (say 1 tonne) and the system divides the total cost by the total kg.</Intro>
      <NameField label="Recipe name" example="Concentrate (1 tonne)" help="You will pick this name later when a ration plan needs a price for a feed." value={name} onChange={setName} />
      <Section n={1} title="What goes into the batch?" help="One line per ingredient: how many kg are in the batch and what you pay per kg.">
        <Rows rows={ing} setRows={setIng} blank={{ name: "", qty: "", price: "" }} addLabel="Ingredient" empty="No ingredients yet. Click + Ingredient to add the first one."
          cols={[{ key: "name", label: "Ingredient", placeholder: "e.g. Maize germ", fr: 2 }, { key: "qty", label: "Quantity in batch (kg)", number: true, placeholder: "e.g. 400" }, { key: "price", label: "Price per kg (KES)", number: true, placeholder: "e.g. 32" }]}
          calc={{ label: "Line cost (KES)", calc: (r) => (num(r.qty) && num(r.price) ? kes(num(r.qty) * num(r.price)) : "-") }} />
      </Section>
      <Section n={2} title="Other costs for the whole batch" help="Optional. Money spent on the batch that is not an ingredient, such as transport, milling or labour. Enter the amount for the whole batch, not per kg.">
        <Rows rows={fixed} setRows={setFixed} blank={{ name: "", amount: "" }} addLabel="Cost" empty="None added. Skip this if the ingredients are the only cost."
          cols={[{ key: "name", label: "What is it for?", placeholder: "e.g. Transport", fr: 2 }, { key: "amount", label: "Amount (KES)", number: true, placeholder: "e.g. 1500" }]} />
      </Section>
      <div className="rounded border border-hairline p-3 text-sm">
        <div>This batch: <b>{qty.toFixed(1)} kg</b> costing <b>KES {kes(total)}</b></div>
        <div className="text-forest">Cost per kg: <b>KES {qty ? (total / qty).toFixed(2) : "-"}</b> <span className="text-xs text-muted">(total cost ÷ total kg)</span></div>
      </div>
      <SaveBar busy={busy} missing={missing} label="Save recipe" notes={unnamed ? [`${unnamed} line(s) have no name and will be left out when you save.`] : []}
        onClick={() => onSave(name.trim(), {
          ingredients: ing.filter((i) => i.name.trim()).map((i) => ({ name: i.name.trim(), quantity_kg: num(i.qty), price_per_kg: num(i.price) })),
          fixed_costs: fixed.filter((f) => f.name.trim()).map((f) => ({ name: f.name.trim(), amount: num(f.amount) })) })} />
    </div>
  );
}

// -------------------------------------------------------------- fodder budget
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
  const lineYear = (l: { amount: string; mult: string; div: string }) => num(l.amount) * (num(l.mult) || 1) / (num(l.div) || 1);
  const perYear = lines.reduce((s, l) => s + lineYear(l), 0);
  const perUnit = num(yld) ? perYear / num(yld) : null;
  const missing = [...(!name.trim() ? ["give the budget a name"] : []), ...(!(num(yld) > 0) ? ["enter the yield per year (more than 0)"] : []), ...(!lines.length ? ["add at least one cost line"] : [])];
  return (
    <div className="space-y-5">
      <Intro>A fodder budget works out what it costs <b>you</b> to grow a feed (hay, silage, nappier) on <b>one acre for one year</b>, and so what each bale or kg costs. One-off costs such as land preparation are spread over the years they last.</Intro>
      <NameField label="Budget name" example="Perennial - Hay (per acre)" help="Describe the crop and say it is per acre. Ration plans pick this name later." value={name} onChange={setName} />
      <Section n={1} title="What does one acre produce?" help="Count the yield in whatever unit you sell or store it in.">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><Input label="Yield per acre per year" type="number" min="0" step="any" value={yld} onChange={(e) => setYld(e.target.value)} placeholder="e.g. 300" /><Hint>How much one acre gives in a year, counted in the unit on the right.</Hint></div>
          <div><Input label="Counted in (unit)" value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="kg, bale or tonne" /><Hint>Type kg if you count in kilograms.</Hint></div>
          <div><Input label="Weight of one unit (kg)" type="number" min="0" step="any" value={uw} onChange={(e) => setUw(e.target.value)} placeholder="e.g. 14 for a 14 kg bale" /><Hint>Only when counting in bales or tonnes. It lets the system show the cost per kg. Leave empty if the unit is kg.</Hint></div>
          <div><Input label="Acres (only for blending)" type="number" min="0" step="any" value={acres} onChange={(e) => setAcres(e.target.value)} placeholder="e.g. 10" /><Hint>Only needed if this budget is mixed with others into a silage blend. The blend is weighted by acres.</Hint></div>
        </div>
      </Section>
      <Section n={2} title="What does it cost to grow?" help={<>One line per cost, for <b>one acre</b>. <b>Times per year</b> is for costs repeated within a year (fertiliser applied twice a year = 2). <b>Spread over (years)</b> is for one-off costs that last several years (land preparation lasting 5 years = 5). Leave both at 1 for an ordinary yearly cost.</>}>
        <Rows rows={lines} setRows={setLines} blank={{ item: "", amount: "", mult: "1", div: "1" }} addLabel="Cost line" empty="No cost lines yet. Click + Cost line to add the first one."
          cols={[{ key: "item", label: "Cost", placeholder: "e.g. Fertiliser", fr: 2 }, { key: "amount", label: "Amount (KES)", number: true, placeholder: "e.g. 20000" },
            { key: "mult", label: "Times per year", number: true, placeholder: "1", fr: 0.8 }, { key: "div", label: "Spread over (years)", number: true, placeholder: "1", fr: 0.9 }]}
          calc={{ label: "Per year (KES)", calc: (r) => (num(r.amount) ? kes(lineYear(r)) : "-") }} />
      </Section>
      <Section title="Assumptions (optional)" help="Notes for yourself or your accountant, one per line, for example 'Yield is an average of 3 seasons'.">
        <textarea aria-label="Assumptions" rows={3} className={FIELD} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Section>
      <div className="rounded border border-hairline p-3 text-sm">
        <div>Cost of growing one acre for a year: <b>KES {kes(perYear)}</b></div>
        <div className="text-forest">{perUnit != null ? <>Per {unit || "unit"}: <b>KES {perUnit.toFixed(2)}</b>{num(uw) ? <> · Per kg: <b>KES {(perUnit / num(uw)).toFixed(2)}</b></> : null}</> : "Enter the yield to see the cost per unit and per kg."} <span className="text-xs text-muted">(cost per year ÷ yield)</span></div>
      </div>
      <SaveBar busy={busy} missing={missing} label="Save budget" onClick={() => onSave(name.trim(), {
        yield_per_year: num(yld), yield_unit: unit || "kg", ...(num(uw) ? { unit_weight_kg: num(uw) } : {}), ...(num(acres) ? { acres: num(acres) } : {}),
        assumptions: notes.split("\n").map((s) => s.trim()).filter(Boolean),
        lines: lines.filter((l) => l.item.trim()).map((l) => ({ item: l.item.trim(), amount: num(l.amount), multiply_by: num(l.mult) || 1, divide_by: num(l.div) || 1 })) })} />
    </div>
  );
}

// -------------------------------------------------------------- ration plan
type Mode = "manual" | "recipe" | "enterprise_budget" | "blend" | "fodder";
const MODE_LABEL: Record<Mode, string> = { manual: "I will type a price", recipe: "A feed recipe", enterprise_budget: "A fodder budget", blend: "A mix of fodder budgets", fodder: "My own fodder stock (actual cost)" };
const MODE_HELP: Record<Mode, string> = {
  manual: "You type the price per kg yourself.",
  recipe: "Uses the cost per kg of a feed recipe, so the plan follows the recipe if its prices change.",
  enterprise_budget: "Uses the cost per kg from one fodder budget (what it costs you to grow it).",
  blend: "Averages the fodder budgets you tick, weighted by their acres.",
  fodder: "Uses the real average cost per kg of your own fodder in store (from the Fodder module).",
};
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
  const feedOk = (f: string) => (mode[f] === "manual" ? num(manual[f]) > 0 : mode[f] === "blend" ? blend.length > 0 : !!pick[f]);
  const missing = [
    ...(!name.trim() ? ["give the plan a name"] : []),
    ...(!stages.length ? ["add at least one stage"] : days <= 0 ? ["enter the number of days for at least one stage"] : []),
    ...FEEDS.filter((f) => !feedOk(f)).map((f) => (mode[f] === "manual" ? `type a price per kg for ${FEED_LABEL[f].toLowerCase()}` : `choose where the ${FEED_LABEL[f].toLowerCase()} price comes from`)),
  ];
  const pickList = (m: Mode) => (m === "recipe" ? recipes : m === "fodder" ? fodderNames : budgets);
  const pickLabel = (m: Mode) => (m === "recipe" ? "Which recipe?" : m === "fodder" ? "Which fodder product?" : "Which fodder budget?");
  const emptyHint = (m: Mode) => (m === "recipe" ? "No feed recipes yet. Save this plan later, or close this window and add a recipe first." : m === "fodder" ? "No fodder products yet. Add them in the Fodder section first." : "No fodder budgets yet. Close this window and add one under Fodder budgets first.");
  return (
    <div className="space-y-5">
      <Intro>A ration plan says <b>what one animal eats each day</b> and <b>what each feed costs per kg</b>. From it we work out the standard feed cost of every animal, which feeds the profit figures.</Intro>
      <NameField label="Ration plan name" example="Fattening ration" help="For example the name of the diet you feed bulls from arrival to sale." value={name} onChange={setName} />
      <Section n={1} title="What does one animal eat each day?" help="Split the feeding period into stages (for example Starter, Growing, Finishing). For each stage enter how many days it lasts and the kg of each feed that ONE animal eats per day. Use one stage if the diet never changes.">
        <Rows rows={stages} setRows={setStages} blank={{ label: "", days: "30", silage: "0", hay: "0", concentrate: "0" }} addLabel="Stage" empty="No stages yet. Click + Stage to add the first one."
          cols={[{ key: "label", label: "Stage name", placeholder: "e.g. Starter", fr: 1.6 }, { key: "days", label: "Days", number: true, placeholder: "30", fr: 0.9 },
            { key: "silage", label: "Silage (kg/day)", number: true, placeholder: "0", fr: 1.2 }, { key: "hay", label: "Hay (kg/day)", number: true, placeholder: "0", fr: 1.2 },
            { key: "concentrate", label: "Concentrate (kg/day)", number: true, placeholder: "0", fr: 1.4 }]}
          calc={{ label: "Total kg/day", fr: 0.9, calc: (r) => (num(r.silage) + num(r.hay) + num(r.concentrate)).toFixed(1) }} />
        <p className="text-xs text-muted">Plan length: <b>{days} days</b>. An animal kept longer than the plan keeps eating the <b>last stage</b> every extra day, so its feed cost keeps growing.</p>
      </Section>
      <Section n={2} title="What does each feed cost per kg?" help="For each feed, say where its price comes from. You can type a price, or let the system take it from a recipe or a fodder budget so it updates by itself when those change.">
        <div className="space-y-3">
          {FEEDS.map((f) => (
            <div key={f} className="rounded border border-hairline p-3">
              <div className="mb-2 text-sm font-medium">{FEED_LABEL[f]} <span className="font-normal text-muted">price per kg</span></div>
              <div className="grid grid-cols-1 items-end gap-3 sm:grid-cols-2">
                <Select label="Where does the price come from?" value={mode[f]} onChange={(e) => setMode({ ...mode, [f]: e.target.value as Mode })}>
                  {(["manual", "recipe", "enterprise_budget", "blend"] as Mode[]).map((m) => <option key={m} value={m}>{MODE_LABEL[m]}</option>)}
                  {(fodderNames.length > 0 || mode[f] === "fodder") && <option value="fodder">{MODE_LABEL.fodder}</option>}
                </Select>
                {mode[f] === "manual" && <Input label="Price (KES per kg)" type="number" min="0" step="any" placeholder="e.g. 25" value={manual[f]} onChange={(e) => setManual({ ...manual, [f]: e.target.value })} />}
                {(mode[f] === "recipe" || mode[f] === "enterprise_budget" || mode[f] === "fodder") && (
                  <Select label={pickLabel(mode[f])} value={pick[f]} onChange={(e) => setPick({ ...pick, [f]: e.target.value })}>
                    <option value="">Choose…</option>{pickList(mode[f]).map((n) => <option key={n} value={n}>{n}</option>)}
                  </Select>)}
              </div>
              {mode[f] === "blend" && (
                <div className="mt-2 text-sm">{budgets.length === 0 ? <span className="text-xs text-muted">{emptyHint("blend")}</span> : <>
                  <div className="mb-1 text-xs text-muted">Tick the fodder budgets to mix:</div>
                  {budgets.map((n) => (
                    <label key={n} className="mr-4 inline-flex items-center gap-1"><input type="checkbox" checked={blend.includes(n)} onChange={(e) => setBlend(e.target.checked ? [...blend, n] : blend.filter((x) => x !== n))} />{n}</label>))}</>}
                </div>)}
              {(mode[f] === "recipe" || mode[f] === "enterprise_budget" || mode[f] === "fodder") && pickList(mode[f]).length === 0 && <p className="mt-2 text-xs text-clay">{emptyHint(mode[f])}</p>}
              <Hint>{MODE_HELP[mode[f]]}</Hint>
            </div>))}
        </div>
      </Section>
      <SaveBar busy={busy} missing={missing} label="Save ration plan" onClick={() => onSave(name.trim(), build())} />
    </div>
  );
}

// ------------------------------------------------------------ overhead pool
const BEHAVIOURS = [
  { value: "fixed", label: "Fixed (same whatever the numbers)" },
  { value: "variable", label: "Variable (rises with each animal)" },
  { value: "step", label: "Step (jumps at a threshold)" },
  { value: "semi-variable", label: "Semi-variable (part fixed, part variable)" },
];
function OverheadEditor({ doc, busy, onSave }: EP) {
  const d = (doc?.data ?? {}) as { lines?: { item: string; amount: number; behaviour?: string }[]; heads?: number; cycle_days?: number; rate_mode?: string; fixed_rate?: number };
  const [name, setName] = useState(doc?.name ?? "");
  const [lines, setLines] = useState((d.lines ?? []).map((l) => ({ item: l.item, amount: str(l.amount), behaviour: l.behaviour ?? "fixed" })));
  const [heads, setHeads] = useState(str(d.heads));
  const [cycle, setCycle] = useState(str(d.cycle_days));
  const [mode, setMode] = useState(d.rate_mode ?? "bull_days");
  const [fixed, setFixed] = useState(str(d.fixed_rate));
  const total = lines.reduce((s, l) => s + num(l.amount), 0);
  const planned = num(heads) > 0 && num(cycle) > 0 && total > 0 ? total / num(heads) / num(cycle) : null;
  const missing = [...(!name.trim() ? ["give the pool a name"] : []), ...(!lines.length ? ["add at least one cost"] : []),
    ...(mode === "fixed" && !(num(fixed) > 0) ? ["enter the fixed rate per bull per day"] : [])];
  return (
    <div className="space-y-5">
      <Intro>The overhead pool holds the running costs of the bull enterprise that are <b>not feed</b> (labour, vet, water, power, transport and so on). The total is shared across the animals according to <b>how many days each one spends on the farm</b>, so animals kept longer carry more.</Intro>
      <NameField label="Pool name" example="Bull fattening operations (excl. feed production)" help="A name for this group of shared costs." value={name} onChange={setName} />
      <Section n={1} title="What are the shared costs?" help="One line per cost, with the amount for the whole cycle (from first arrival to last sale).">
        <Rows rows={lines} setRows={setLines} blank={{ item: "", amount: "", behaviour: "fixed" }} addLabel="Cost" empty="No costs yet. Click + Cost to add the first one."
          cols={[{ key: "item", label: "Cost", placeholder: "e.g. Labour", fr: 1.6 }, { key: "amount", label: "Amount for the cycle (KES)", number: true, placeholder: "e.g. 350000", fr: 1.3 },
            { key: "behaviour", label: "How it behaves", options: BEHAVIOURS, fr: 2 }]} />
        <Hint>"How it behaves" is a label used to group the costs on the exported worksheet. It does not change how the money is shared.</Hint>
        <p className="text-sm">Total shared costs: <b>KES {kes(total)}</b></p>
      </Section>
      <Section n={2} title="The planned size of the cycle" help="Optional. Used only to show a planned cost per bull per day to compare against the real figure.">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><Input label="Number of bulls planned" type="number" min="0" placeholder="e.g. 130" value={heads} onChange={(e) => setHeads(e.target.value)} /></div>
          <div><Input label="Cycle length (days)" type="number" min="0" placeholder="e.g. 221" value={cycle} onChange={(e) => setCycle(e.target.value)} /></div>
        </div>
        {planned != null && <p className="text-xs text-muted">Planned: KES {kes(total / num(heads))} per bull, or <b>KES {planned.toFixed(2)} per bull per day</b> (total ÷ bulls ÷ days).</p>}
      </Section>
      <Section n={3} title="How is the pool shared out?" help={<>A <b>bull-day</b> is one bull on the farm for one day. Example: 10 bulls for 30 days = 300 bull-days. If the pool is KES 30,000, each bull-day is charged KES 100.</>}>
        <Select label="Sharing method" value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="bull_days">Divide the total by the actual bull-days (recommended)</option>
          <option value="fixed">Use a fixed rate per bull per day that I type</option>
        </Select>
        <Hint>{mode === "fixed" ? "You choose the daily rate. The pool may then be over or under charged compared with the real total." : "The whole pool is always shared out, never more and never less. The rate moves automatically as animals arrive, stay and leave."}</Hint>
        {mode === "fixed" && <Input label="Rate (KES per bull per day)" type="number" min="0" step="any" placeholder="e.g. 67" value={fixed} onChange={(e) => setFixed(e.target.value)} />}
      </Section>
      <SaveBar busy={busy} missing={missing} label="Save overhead pool" onClick={() => onSave(name.trim(), {
        lines: lines.filter((l) => l.item.trim()).map((l) => ({ item: l.item.trim(), amount: num(l.amount), behaviour: l.behaviour })),
        heads: num(heads), cycle_days: num(cycle), rate_mode: mode, ...(mode === "fixed" ? { fixed_rate: num(fixed) } : {}) })} />
    </div>
  );
}

// --------------------------------------------------------------- thresholds
const SETTING_GROUPS: { title: string; help: string; fields: { key: string; label: string; def: number; hint: string }[] }[] = [
  { title: "When is an animal ready to sell?", help: "", fields: [
    { key: "market_ready_kg", label: "Market-ready weight (kg)", def: 300, hint: "An animal at or above this weight is shown green and counted as ready to sell." }] },
  { title: "How good is the growth rate (ADG)?", help: "ADG is average daily gain: kg gained per day. These four numbers set the colours.", fields: [
    { key: "adg_poor_max", label: "Poor: ADG at or below", def: 0.2, hint: "At or below this the growth is shown red (poor)." },
    { key: "adg_target_min", label: "On target: ADG from", def: 0.4, hint: "From here up to the next box is on target (green). Between 'poor' and this number is 'below target'." },
    { key: "adg_target_max", label: "On target: ADG up to", def: 0.7, hint: "Above this the growth is excellent (cyan)." },
    { key: "interval_gain_good", label: "Good gain between weigh-ins: over (kg)", def: 20, hint: "A gain bigger than this since the previous weighing is highlighted cyan." }] },
  { title: "Money and data checks", help: "", fields: [
    { key: "reference_price_per_kg", label: "Reference price per kg (KES)", def: 320, hint: "Used to estimate the value of animals that are not sold yet." },
    { key: "implausible_gain_kg_per_day", label: "Flag gains above (kg per day)", def: 3, hint: "A daily gain above this is flagged as probably a typing error, for example 3240 instead of 324." },
    { key: "day_offset", label: "Days-on-farm adjustment (days)", def: 1, hint: "Days on farm = date difference minus this number. Your worksheet uses 1. Use 0 for a plain date difference." }] },
];
const SETTING_FIELDS = SETTING_GROUPS.flatMap((g) => g.fields);
function SettingsEditor({ doc, busy, onSave }: EP) {
  const d = (doc?.data ?? {}) as Record<string, number>;
  const [v, setV] = useState<Record<string, string>>(Object.fromEntries(SETTING_FIELDS.map((f) => [f.key, str(d[f.key] ?? "")])));
  return (
    <div className="space-y-5">
      <Intro>Thresholds decide the <b>colours and warnings</b> you see on weights and growth rates. They do not change any cost. The grey number in each box is the standard value; <b>leave a box empty to use it</b>.</Intro>
      {SETTING_GROUPS.map((g) => (
        <Section key={g.title} title={g.title} help={g.help}>
          <div className="space-y-3">
            {g.fields.map((f) => (
              <div key={f.key}>
                <Input label={f.label} type="number" step="any" placeholder={`Standard: ${f.def}`} value={v[f.key]} onChange={(e) => setV({ ...v, [f.key]: e.target.value })} />
                <Hint>{f.hint}</Hint>
              </div>))}
          </div>
        </Section>))}
      <SaveBar busy={busy} missing={[]} label="Save thresholds" onClick={() => onSave("default", Object.fromEntries(SETTING_FIELDS.filter((f) => v[f.key] !== "").map((f) => [f.key, num(v[f.key])])))} />
    </div>
  );
}

// ----------------------------------------------------------------- land use
interface LandRow { item: string; irrigated: boolean; acres: Record<string, string>; raw: Record<string, unknown> }
function LandUseEditor({ doc, busy, onSave }: EP) {
  const d = (doc?.data ?? {}) as { unit?: string; sites?: string[]; rows?: Record<string, unknown>[] };
  const [name, setName] = useState(doc?.name ?? "Land use (acres)");
  const [sitesText, setSitesText] = useState((d.sites ?? []).join(", "));
  const [rows, setRows] = useState<LandRow[]>((d.rows ?? []).map((r) => ({
    item: str(r.item), irrigated: Boolean(r.irrigated), raw: r,
    acres: Object.fromEntries(Object.entries(r).filter(([k]) => k !== "item" && k !== "irrigated").map(([k, val]) => [k, str(val)])) })));
  const [advanced, setAdvanced] = useState(false);
  const sites = Array.from(new Set(sitesText.split(",").map((s) => s.trim()).filter((s) => s && s !== "item" && s !== "irrigated")));
  const setRow = (i: number, patch: Partial<LandRow>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const build = (): Record<string, unknown> => ({
    ...(doc?.data ?? {}), unit: "acres", sites,
    rows: rows.filter((r) => r.item.trim()).map((r) => ({ ...r.raw, item: r.item.trim(), ...Object.fromEntries(sites.map((s) => [s, num(r.acres[s] ?? "")])), irrigated: r.irrigated })),
  });
  if (advanced) return <JsonEditor doc={{ id: doc?.id ?? "", kind: "land_use", name, computed: null, data: build() }} busy={busy} onSave={onSave} />;
  const template = `minmax(0, 2fr) ${sites.map(() => "minmax(0, 1fr)").join(" ")} minmax(0, 0.9fr) 1.5rem`;
  const minWidth = `${Math.max((2 + sites.length + 0.9) * 4.5, 22)}rem`;
  return (
    <div className="space-y-5">
      <Intro>Land use is a record of <b>how many acres</b> each activity uses on each of your sites. It only fills the &ldquo;LAND USE IN ACRES&rdquo; sheet of the exported worksheet. It does <b>not</b> change any cost or profit figure.</Intro>
      <div><Input label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Land use (acres)" /></div>
      <Section n={1} title="Your sites" help="Type the name of each site or sub-farm, separated by commas. Each one becomes a column below.">
        <Input label="Sites" value={sitesText} onChange={(e) => setSitesText(e.target.value)} placeholder="e.g. Nairutia, Segera, Gatumbiro" />
        <Hint>If you rename a site, type its acres again under the new name.</Hint>
      </Section>
      <Section n={2} title="Acres per activity" help="One line per activity (for example Maize silage, Napier, Bull sheds). Enter the acres on each site, and tick Irrigated if it is irrigated.">
        {sites.length === 0 ? <p className="text-xs text-clay">Enter at least one site above to start filling in acres.</p> : (
          <div className="space-y-2">
            <div className="overflow-x-auto">
              <div className="space-y-1" style={{ minWidth }}>
                {rows.length > 0 && (
                  <div className="grid items-end gap-2 text-xs font-medium text-muted" style={{ gridTemplateColumns: template }}>
                    <div>Activity</div>{sites.map((s) => <div key={s}>{s} (acres)</div>)}<div>Irrigated?</div><div /></div>)}
                {rows.map((r, i) => (
                  <div key={i} className="grid items-center gap-2" style={{ gridTemplateColumns: template }}>
                    <input aria-label="Activity" placeholder="e.g. Maize silage" className={FIELD} value={r.item} onChange={(e) => setRow(i, { item: e.target.value })} />
                    {sites.map((s) => <input key={s} aria-label={`${s} acres`} placeholder="0" type="number" step="any" className={FIELD} value={r.acres[s] ?? ""} onChange={(e) => setRow(i, { acres: { ...r.acres, [s]: e.target.value } })} />)}
                    <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={r.irrigated} onChange={(e) => setRow(i, { irrigated: e.target.checked })} />Yes</label>
                    <button type="button" aria-label="Remove this line" title="Remove this line" className="text-clay" onClick={() => setRows(rows.filter((_, j) => j !== i))}>×</button>
                  </div>))}
                {rows.length > 0 && (
                  <div className="grid items-center gap-2 border-t border-hairline pt-1 text-sm font-medium" style={{ gridTemplateColumns: template }}>
                    <div>Total</div>{sites.map((s) => <div key={s} className="tabular-nums">{rows.reduce((a, r) => a + num(r.acres[s] ?? ""), 0)}</div>)}<div /><div /></div>)}
              </div>
            </div>
            {rows.length === 0 && <p className="text-xs text-muted">No activities yet. Click + Activity to add the first one.</p>}
            <Button variant="ghost" onClick={() => setRows([...rows, { item: "", irrigated: false, acres: {}, raw: {} }])}>+ Activity</Button>
          </div>)}
      </Section>
      <SaveBar busy={busy} missing={!name.trim() ? ["give it a name"] : []} label="Save land use" onClick={() => onSave(name.trim(), build())} />
      <button type="button" className="text-xs text-muted underline" onClick={() => setAdvanced(true)}>Advanced: edit the raw data (JSON) instead</button>
    </div>
  );
}

// Raw-data fallback (also reachable from the land-use form's "Advanced" link)
function JsonEditor({ doc, busy, onSave }: EP) {
  const [name, setName] = useState(doc?.name ?? "Land use (acres)");
  const [text, setText] = useState(JSON.stringify(doc?.data ?? { unit: "acres", sites: [], rows: [] }, null, 2));
  let parsed: Record<string, unknown> | null = null;
  try { const p: unknown = JSON.parse(text); parsed = p && typeof p === "object" && !Array.isArray(p) ? (p as Record<string, unknown>) : null; } catch { parsed = null; }
  return (
    <div className="space-y-3">
      <Intro>Raw data view. Each line must stay valid JSON (matching quotes and commas). If it turns red below, undo your last change.</Intro>
      <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} />
      <textarea aria-label="Data (JSON)" rows={12} className={`${FIELD} font-mono`} value={text} onChange={(e) => setText(e.target.value)} />
      {!parsed && <p className="text-xs text-clay">This is not valid JSON yet.</p>}
      <SaveBar busy={busy} missing={[...(!parsed ? ["fix the data so it is valid JSON"] : []), ...(!name.trim() ? ["give it a name"] : [])]} label="Save" onClick={() => parsed && onSave(name.trim(), parsed)} />
    </div>
  );
}
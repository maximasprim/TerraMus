"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, EmptyState, ErrorState, StatCard } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { CyclesTab } from "./cycles-tab";
import { SetupTab } from "./setup-tab";
import { errMsg, money, StockRow, Summary, todayIso } from "./shared";
import { StockTab } from "./stock-tab";

type Tab = "overview" | "cycles" | "stock" | "setup";
const TABS: [Tab, string][] = [["overview", "Overview"], ["cycles", "Plots & cycles"], ["stock", "Stock"], ["setup", "Products, prices & investments"]];

export default function FodderPage() {
  const [tab, setTab] = useState<Tab>("overview");
  useEffect(() => { const h = window.location.hash.slice(1) as Tab; if (TABS.some(([k]) => k === h)) setTab(h); }, []);
  const choose = (k: Tab) => { setTab(k); window.history.replaceState(null, "", `#${k}`); };
  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl text-forest">Fodder production</h1>
        <p className="text-sm text-muted">Grow it, store it, feed it: what it really costs per kg and per bale (with establishment costs amortised), what is in stock, and what you saved against buying it.</p>
      </div>
      <div className="mb-6 flex flex-wrap gap-2 border-b border-hairline">
        {TABS.map(([k, label]) => (
          <button key={k} onClick={() => choose(k)} className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${tab === k ? "border-forest text-forest" : "border-transparent text-muted hover:text-ink"}`}>{label}</button>))}
      </div>
      {tab === "overview" && <Overview />}
      {tab === "cycles" && <CyclesTab />}
      {tab === "stock" && <StockTab />}
      {tab === "setup" && <SetupTab />}
    </AdminShell>
  );
}

function Overview() {
  const start = `${new Date().getFullYear()}-01-01`;
  const stock = useQuery<StockRow[]>({ queryKey: ["fodder", "stock"], queryFn: () => apiFetch<StockRow[]>("/api/v1/fodder/stock") });
  const sum = useQuery<Summary>({ queryKey: ["fodder", "summary", start], queryFn: () => apiFetch<Summary>(`/api/v1/fodder/summary?start_date=${start}&end_date=${todayIso()}`) });
  const err = stock.error ?? sum.error;
  if (err) return <ErrorState message={errMsg(err, "Failed to load fodder data")} />;
  if (stock.isLoading) return <p className="text-sm text-muted">Loading…</p>;
  if (!stock.data?.length) return <EmptyState title="No fodder set up yet" body="Start on the Products tab: add what you grow or buy (hay, silage…), then plots and a production cycle." />;
  const p = sum.data?.production;
  const low = stock.data.filter((s) => s.low_cover && s.is_active);
  return (
    <div className="space-y-6">
      {low.length > 0 && <Card><p className="text-sm text-clay">{low.map((s) => `${s.name}: about ${s.days_of_cover?.toFixed(0)} days left`).join(" · ")}. Time to harvest, buy or cut back.</p></Card>}
      {p && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Cost of production (this year)" value={`KES ${money(p.total_cost)}`} hint="direct costs + amortisation" />
          <StatCard label="Worth at market price" value={`KES ${money(p.replacement_value)}`} hint="what buying it would have cost" />
          <StatCard label="Saved vs buying" value={`KES ${money(p.saving_vs_buying)}`} hint={p.saving_vs_buying < 0 ? "growing cost more than buying" : "growing was cheaper"} />
          <StatCard label="Stock on hand" value={`KES ${money(stock.data.reduce((s, r) => s + (r.stock_value ?? 0), 0))}`} hint="at average cost" />
        </div>
      )}
      <Card>
        <h2 className="mb-3 font-display text-lg text-forest">Stock</h2>
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead><tr className="border-b border-hairline text-left text-xs uppercase text-muted"><th className="py-2">Product</th><th className="text-right">In stock</th><th className="text-right">Avg cost / kg</th>
            <th className="text-right">Value</th><th className="text-right">Market / kg</th><th className="text-right">Days of cover</th></tr></thead>
          <tbody>{stock.data.map((s) => (
            <tr key={s.product_id} className="border-b border-hairline/60">
              <td className="py-2 font-medium">{s.name}</td><td className="text-right">{money(s.balance_units, 1)} {s.unit_label}s<div className="text-xs text-muted">{money(s.balance_kg)} kg</div></td>
              <td className="text-right">{s.avg_cost_per_kg?.toFixed(2) ?? "-"}</td><td className="text-right">{money(s.stock_value)}</td><td className="text-right">{s.market_price_per_kg ?? "-"}</td>
              <td className={`text-right ${s.low_cover ? "font-medium text-clay" : ""}`}>{s.days_of_cover != null ? s.days_of_cover.toFixed(0) : "-"}</td>
            </tr>))}</tbody>
        </table></div>
      </Card>
      {sum.data && sum.data.products.length > 0 && (
        <Card>
          <h2 className="mb-1 font-display text-lg text-forest">This year by product</h2>
          <p className="mb-3 text-xs text-muted">Self-sufficiency is the share of what came in that you grew yourself rather than bought.</p>
          <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-hairline text-left text-xs uppercase text-muted">
            <th className="py-2">Product</th><th className="text-right">Grown (kg)</th><th className="text-right">Bought (kg)</th><th className="text-right">Fed (kg)</th><th className="text-right">Lost (kg)</th><th className="text-right">Self-sufficient</th></tr></thead>
            <tbody>{sum.data.products.map((x) => (
              <tr key={x.product} className="border-b border-hairline/60"><td className="py-2 font-medium">{x.product}</td><td className="text-right">{money(x.harvested_kg)}</td><td className="text-right">{money(x.purchased_kg)}</td>
                <td className="text-right">{money(x.issued_kg)}</td><td className="text-right">{money(x.lost_kg)}{x.loss_pct_of_inflow != null ? ` (${x.loss_pct_of_inflow}%)` : ""}</td>
                <td className="text-right">{x.self_sufficiency_pct != null ? `${x.self_sufficiency_pct}%` : "-"}</td></tr>))}</tbody></table></div>
        </Card>
      )}
    </div>
  );
}

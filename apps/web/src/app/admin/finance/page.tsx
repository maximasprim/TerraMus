"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Can } from "@/components/can";
import { Card, StatCard, Button, Input, Select, Modal, ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { FinanceTransaction, FinanceSummary, ProfitabilityReport } from "@/lib/types";
import { clsx } from "clsx";

const TABS = ["Summary", "Transactions", "Profitability"] as const;
type Tab = (typeof TABS)[number];

const CATEGORIES = [
  "livestock_sale", "milk_sale", "other_revenue", "livestock_acquisition", "feed",
  "veterinary", "labour", "transport", "utilities", "maintenance", "equipment",
  "marketing", "payment_processing_fee", "other_expense",
] as const;

function firstOfMonth() {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10);
}
function today() {
  return new Date().toISOString().slice(0, 10);
}

export default function FinancePage() {
  const [tab, setTab] = useState<Tab>("Summary");
  const [startDate, setStartDate] = useState(firstOfMonth());
  const [endDate, setEndDate] = useState(today());
  const [modalOpen, setModalOpen] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const summaryQuery = useQuery<FinanceSummary>({
    queryKey: ["finance-summary", startDate, endDate],
    queryFn: () => apiFetch<FinanceSummary>(`/api/v1/finance/summary?start_date=${startDate}&end_date=${endDate}`),
    enabled: tab === "Summary",
  });
  const transactionsQuery = useQuery<FinanceTransaction[]>({
    queryKey: ["finance-transactions"],
    queryFn: () => apiFetch<FinanceTransaction[]>("/api/v1/finance/transactions"),
    enabled: tab === "Transactions",
  });
  const profitabilityQuery = useQuery<ProfitabilityReport>({
    queryKey: ["profitability"],
    queryFn: () => apiFetch<ProfitabilityReport>("/api/v1/reports/profitability"),
    enabled: tab === "Profitability",
  });

  const createTransaction = useMutation({
    mutationFn: (body: { transaction_type: string; category: string; amount: string; transaction_date: string; description?: string }) =>
      apiFetch("/api/v1/finance/transactions", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["finance-transactions"] });
      queryClient.invalidateQueries({ queryKey: ["finance-summary"] });
      setModalOpen(false);
      setFormError(null);
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : "Failed to record transaction"),
  });

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Finance</h1>
          <p className="text-sm text-muted">Income, expenses, and per-animal profitability.</p>
        </div>
        <Can permission="finance.create"><Button onClick={() => { setFormError(null); setModalOpen(true); }}>+ Record transaction</Button></Can>
      </div>

      <div className="mb-6 flex gap-1 border-b border-hairline">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              "border-b-2 px-4 py-2 text-sm font-medium transition-colors",
              tab === t ? "border-brass text-forest" : "border-transparent text-muted hover:text-ink",
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Summary" && (
        <div>
          <div className="mb-4 flex items-end gap-3">
            <Input id="start-date" label="From" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            <Input id="end-date" label="To" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </div>

          {summaryQuery.error && (
            <ErrorState message={summaryQuery.error instanceof ApiError ? summaryQuery.error.message : "Failed to load summary"} />
          )}
          {summaryQuery.data && (
            <>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <StatCard label="Income" value={`KES ${Number(summaryQuery.data.total_income).toLocaleString()}`} />
                <StatCard label="Expenses" value={`KES ${Number(summaryQuery.data.total_expense).toLocaleString()}`} />
                <StatCard label="Net" value={`KES ${Number(summaryQuery.data.net_income).toLocaleString()}`} />
              </div>
              <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
                <Card>
                  <h2 className="mb-3 font-display text-lg text-forest">Income by category</h2>
                  {Object.keys(summaryQuery.data.income_by_category).length === 0 ? (
                    <p className="text-sm text-muted">No income in this range.</p>
                  ) : (
                    <dl className="space-y-2 text-sm">
                      {Object.entries(summaryQuery.data.income_by_category).map(([cat, amount]) => (
                        <div key={cat} className="flex justify-between border-b border-hairline/60 pb-2 capitalize">
                          <dt className="text-muted">{cat.replace(/_/g, " ")}</dt>
                          <dd className="font-medium text-ink">KES {Number(amount).toLocaleString()}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </Card>
                <Card>
                  <h2 className="mb-3 font-display text-lg text-forest">Expenses by category</h2>
                  {Object.keys(summaryQuery.data.expense_by_category).length === 0 ? (
                    <p className="text-sm text-muted">No expenses in this range.</p>
                  ) : (
                    <dl className="space-y-2 text-sm">
                      {Object.entries(summaryQuery.data.expense_by_category).map(([cat, amount]) => (
                        <div key={cat} className="flex justify-between border-b border-hairline/60 pb-2 capitalize">
                          <dt className="text-muted">{cat.replace(/_/g, " ")}</dt>
                          <dd className="font-medium text-ink">KES {Number(amount).toLocaleString()}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </Card>
              </div>
            </>
          )}
        </div>
      )}

      {tab === "Transactions" && (
        <Card>
          {transactionsQuery.isLoading && <p className="text-sm text-muted">Loading…</p>}
          {transactionsQuery.data && transactionsQuery.data.length === 0 && (
            <EmptyState title="No transactions yet" body="Transactions from sales, acquisitions, and manual entries appear here." />
          )}
          {transactionsQuery.data && transactionsQuery.data.length > 0 && (
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-hairline text-xs uppercase tracking-wider text-muted">
                  <th className="pb-2 font-medium">Date</th>
                  <th className="pb-2 font-medium">Type</th>
                  <th className="pb-2 font-medium">Category</th>
                  <th className="pb-2 font-medium">Amount</th>
                  <th className="pb-2 font-medium">Description</th>
                </tr>
              </thead>
              <tbody>
                {transactionsQuery.data.map((t) => (
                  <tr key={t.id} className="border-b border-hairline/60 last:border-0">
                    <td className="py-2">{t.transaction_date}</td>
                    <td className={clsx("py-2 font-medium capitalize", t.transaction_type === "income" ? "text-moss" : "text-clay")}>
                      {t.transaction_type}
                    </td>
                    <td className="py-2 capitalize text-muted">{t.category.replace(/_/g, " ")}</td>
                    <td className="py-2 font-medium text-ink">KES {Number(t.amount).toLocaleString()}</td>
                    <td className="py-2 text-muted">{t.description ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}

      {tab === "Profitability" && (
        <div>
          {profitabilityQuery.data && (
            <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-2">
              <Card>
                <h2 className="mb-3 font-display text-lg text-forest">Most profitable</h2>
                {profitabilityQuery.data.most_profitable.length === 0 ? (
                  <p className="text-sm text-muted">No sold or priced animals yet.</p>
                ) : (
                  <ul className="space-y-2 text-sm">
                    {profitabilityQuery.data.most_profitable.map((a) => (
                      <li key={a.animal_id} className="flex justify-between border-b border-hairline/60 pb-2">
                        <span className="font-mono text-xs text-ink">{a.animal_number}</span>
                        <span className="font-medium text-moss">
                          KES {Number(a.profit).toLocaleString()} {!a.is_actual && <span className="text-muted">(est.)</span>}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
              <Card>
                <h2 className="mb-3 font-display text-lg text-forest">Least profitable</h2>
                {profitabilityQuery.data.least_profitable.length === 0 ? (
                  <p className="text-sm text-muted">No sold or priced animals yet.</p>
                ) : (
                  <ul className="space-y-2 text-sm">
                    {profitabilityQuery.data.least_profitable.map((a) => (
                      <li key={a.animal_id} className="flex justify-between border-b border-hairline/60 pb-2">
                        <span className="font-mono text-xs text-ink">{a.animal_number}</span>
                        <span className={clsx("font-medium", Number(a.profit) < 0 ? "text-clay" : "text-ink")}>
                          KES {Number(a.profit).toLocaleString()} {!a.is_actual && <span className="text-muted">(est.)</span>}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </div>
          )}

          <Card>
            <h2 className="mb-3 font-display text-lg text-forest">All animals</h2>
            {profitabilityQuery.data && profitabilityQuery.data.animals.length === 0 && (
              <p className="text-sm text-muted">No animals yet.</p>
            )}
            {profitabilityQuery.data && profitabilityQuery.data.animals.length > 0 && (
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-hairline text-xs uppercase tracking-wider text-muted">
                    <th className="pb-2 font-medium">Animal</th>
                    <th className="pb-2 font-medium">Investment</th>
                    <th className="pb-2 font-medium">Sale / Expected</th>
                    <th className="pb-2 font-medium">Profit</th>
                  </tr>
                </thead>
                <tbody>
                  {profitabilityQuery.data.animals.map((a) => (
                    <tr key={a.animal_id} className="border-b border-hairline/60 last:border-0">
                      <td className="py-2 font-mono text-xs">{a.animal_number}</td>
                      <td className="py-2 text-muted">KES {Number(a.total_investment).toLocaleString()}</td>
                      <td className="py-2 text-muted">
                        {a.sale_price
                          ? `KES ${Number(a.sale_price).toLocaleString()}`
                          : a.expected_sale_price
                            ? `~KES ${Number(a.expected_sale_price).toLocaleString()}`
                            : "-"}
                      </td>
                      <td className={clsx("py-2 font-medium", a.profit && Number(a.profit) < 0 ? "text-clay" : "text-ink")}>
                        {a.profit ? `KES ${Number(a.profit).toLocaleString()}` : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      )}

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Record transaction">
        <TransactionForm error={formError} pending={createTransaction.isPending} onSubmit={(body) => createTransaction.mutate(body)} />
      </Modal>
    </AdminShell>
  );
}

function TransactionForm({
  onSubmit,
  error,
  pending,
}: {
  onSubmit: (body: { transaction_type: string; category: string; amount: string; transaction_date: string; description?: string }) => void;
  error: string | null;
  pending: boolean;
}) {
  const [type, setType] = useState<"income" | "expense">("expense");
  const [category, setCategory] = useState<string>(CATEGORIES[0]);
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(today());
  const [description, setDescription] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ transaction_type: type, category, amount, transaction_date: date, description: description || undefined });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Select id="txn-type" label="Type" value={type} onChange={(e) => setType(e.target.value as "income" | "expense")}>
        <option value="income">Income</option>
        <option value="expense">Expense</option>
      </Select>
      <Select id="txn-category" label="Category" value={category} onChange={(e) => setCategory(e.target.value)}>
        {CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {c.replace(/_/g, " ")}
          </option>
        ))}
      </Select>
      <div className="grid grid-cols-2 gap-4">
        <Input id="txn-amount" label="Amount (KES)" type="number" min="0" step="0.01" required value={amount} onChange={(e) => setAmount(e.target.value)} />
        <Input id="txn-date" label="Date" type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
      </div>
      <Input id="txn-description" label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Recording…" : "Record transaction"}
      </Button>
    </form>
  );
}

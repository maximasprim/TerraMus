"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Button, Card, EmptyState, ErrorState, Input, Modal, Select, StatCard } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";

interface Ageing { "0-30": number; "31-60": number; "61-90": number; "90+": number }
interface Balances {
  as_of: string; total_outstanding: number; customers_owing: number; ageing: Ageing;
  customers: { customer_id: string; customer_name: string | null; phone: string | null; balance: number; ageing: Ageing; days_outstanding: number }[];
}
interface Statement {
  customer_name: string | null; balance: number; charged: number; paid: number; written_off: number;
  open_items: { charge_id: string; date: string; description: string | null; outstanding: number }[];
}

const kes = (n: number) => new Intl.NumberFormat("en-KE", { maximumFractionDigits: 0 }).format(n);
const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);

export default function ReceivablesPage() {
  const queryClient = useQueryClient();
  const [payFor, setPayFor] = useState<{ id: string; name: string } | null>(null);
  const [viewId, setViewId] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [method, setMethod] = useState("mpesa");
  const [ref, setRef] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, error: loadErr } = useQuery<Balances>({ queryKey: ["receivables"], queryFn: () => apiFetch<Balances>("/api/v1/receivables/balances") });
  const stmt = useQuery<Statement>({
    queryKey: ["receivables", "statement", viewId], enabled: !!viewId,
    queryFn: () => apiFetch<Statement>(`/api/v1/receivables/customers/${viewId}/statement`),
  });
  const pay = useMutation({
    mutationFn: () => apiFetch("/api/v1/receivables/payments", {
      method: "POST",
      body: JSON.stringify({ customer_id: payFor?.id, amount: Number(amount), entry_date: date, method, receipt_ref: ref || undefined }),
    }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["receivables"] }); queryClient.invalidateQueries({ queryKey: ["finance"] }); setPayFor(null); setAmount(""); setRef(""); setError(null); },
    onError: (e) => setError(errMsg(e, "Could not record payment")),
  });

  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl text-forest">Receivables</h1>
        <p className="text-sm text-muted">Who owes the farm money, how old the debt is, and payments received. Income reaches the ledger when cash is received.</p>
      </div>
      {loadErr && <ErrorState message={errMsg(loadErr, "Failed to load balances")} />}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {data && data.customers.length === 0 && <EmptyState title="Nobody owes you anything" body="Credit sales (feedlot, training, flocks) appear here until they are paid." />}
      {data && data.customers.length > 0 && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
            <StatCard label="Outstanding (KES)" value={kes(data.total_outstanding)} hint={`${data.customers_owing} customer(s)`} />
            {(Object.keys(data.ageing) as (keyof Ageing)[]).map((k) => <StatCard key={k} label={`${k} days`} value={kes(data.ageing[k])} />)}
          </div>
          <Card>
            <div className="overflow-x-auto"><table className="w-full text-sm">
              <thead><tr className="border-b border-hairline text-left text-xs uppercase text-muted">
                <th className="py-2">Customer</th><th>Phone</th><th className="text-right">Balance</th><th className="text-right">Oldest (days)</th><th className="text-right">90+ days</th><th /></tr></thead>
              <tbody>{data.customers.map((c) => (
                <tr key={c.customer_id} className="border-b border-hairline/60">
                  <td className="py-2"><button className="font-medium text-forest underline-offset-2 hover:underline" onClick={() => setViewId(c.customer_id)}>{c.customer_name ?? "Customer"}</button></td>
                  <td>{c.phone ?? "-"}</td><td className="text-right font-medium">{kes(c.balance)}</td>
                  <td className={`text-right ${c.days_outstanding > 90 ? "text-clay" : ""}`}>{c.days_outstanding}</td>
                  <td className="text-right">{kes(c.ageing["90+"])}</td>
                  <td className="text-right"><Button variant="ghost" onClick={() => { setError(null); setPayFor({ id: c.customer_id, name: c.customer_name ?? "Customer" }); }}>Record payment</Button></td>
                </tr>))}</tbody>
            </table></div>
          </Card>
        </div>
      )}
      <Modal open={!!payFor} onClose={() => setPayFor(null)} title={`Payment from ${payFor?.name ?? ""}`}>
        <div className="space-y-3">
          {error && <ErrorState message={error} />}
          <Input label="Amount (KES)" type="number" min="1" value={amount} onChange={(e) => setAmount(e.target.value)} />
          <Input label="Date received" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          <Select label="Method" value={method} onChange={(e) => setMethod(e.target.value)}>
            {["mpesa", "cash", "bank", "cheque", "other"].map((m) => <option key={m} value={m}>{m}</option>)}
          </Select>
          <Input label="Receipt / M-Pesa code (optional)" value={ref} onChange={(e) => setRef(e.target.value)} />
          <Button disabled={!(Number(amount) > 0) || pay.isPending} onClick={() => pay.mutate()}>Save payment</Button>
        </div>
      </Modal>
      <Modal open={!!viewId} onClose={() => setViewId(null)} title={`Statement: ${stmt.data?.customer_name ?? ""}`}>
        {stmt.isLoading && <p className="text-sm text-muted">Loading…</p>}
        {stmt.data && (
          <div className="space-y-3 text-sm">
            <p>Charged {kes(stmt.data.charged)} · Paid {kes(stmt.data.paid)} · Written off {kes(stmt.data.written_off)} · <b>Balance {kes(stmt.data.balance)}</b></p>
            <table className="w-full"><tbody>{stmt.data.open_items.map((i) => (
              <tr key={i.charge_id} className="border-b border-hairline/60"><td className="py-1">{i.date}</td><td>{i.description}</td><td className="text-right">{kes(i.outstanding)}</td></tr>))}</tbody></table>
          </div>
        )}
      </Modal>
    </AdminShell>
  );
}

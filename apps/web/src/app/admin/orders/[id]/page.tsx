"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, StatusBadge, ErrorState, Button, Input } from "@/components/ui";
import { apiFetch, apiDownload, ApiError } from "@/lib/api";
import type { Order, Customer, Animal, Invoice } from "@/lib/types";

// Mirrors apps/api/app/modules/commerce/service.py's _ORDER_TRANSITIONS -
// see the same disclaimer on the livestock detail page: this is a
// hand-copied mirror, not derived from a shared source, and could drift
// from the backend if that table changes without this one being updated.
// The backend is still the actual enforcement point regardless.
const ORDER_TRANSITIONS: Record<string, string[]> = {
  pending: ["payment_pending", "cancelled"],
  payment_pending: ["paid", "cancelled", "failed"],
  paid: ["processing", "refunded", "partially_refunded"],
  processing: ["ready_for_fulfillment", "refunded"],
  ready_for_fulfillment: ["dispatched"],
  dispatched: ["delivered"],
  delivered: ["completed", "partially_refunded"],
  completed: [],
  cancelled: [],
  refunded: [],
  partially_refunded: [],
  failed: [],
};

export default function OrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [statusError, setStatusError] = useState<string | null>(null);

  const orderQuery = useQuery<Order>({
    queryKey: ["order", id],
    queryFn: () => apiFetch<Order>(`/api/v1/orders/${id}`),
  });
  const customersQuery = useQuery<Customer[]>({
    queryKey: ["customers"],
    queryFn: () => apiFetch<Customer[]>("/api/v1/customers"),
  });

  const changeStatus = useMutation({
    mutationFn: (status: string) =>
      apiFetch(`/api/v1/orders/${id}/status`, { method: "POST", body: JSON.stringify({ status }) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["order", id] });
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      setStatusError(null);
    },
    onError: (err) => setStatusError(err instanceof ApiError ? err.message : "Failed to change status"),
  });

  if (orderQuery.error) {
    return (
      <AdminShell>
        <ErrorState message={orderQuery.error instanceof ApiError ? orderQuery.error.message : "Failed to load order"} />
      </AdminShell>
    );
  }
  if (!orderQuery.data) {
    return (
      <AdminShell>
        <p className="text-sm text-muted">Loading…</p>
      </AdminShell>
    );
  }

  const order = orderQuery.data;
  const customer = customersQuery.data?.find((c) => c.id === order.customer_id);
  const nextStatuses = ORDER_TRANSITIONS[order.status] ?? [];

  return (
    <AdminShell>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="mb-2">
            <StatusBadge status={order.status} />
          </div>
          <h1 className="font-display text-2xl text-forest">{customer?.name ?? "Order"}</h1>
          <p className="text-sm text-muted">
            {customer?.email ?? customer?.phone ?? ""} · Placed {new Date(order.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs uppercase tracking-wider text-muted">Total</p>
          <p className="font-display text-2xl text-forest">KES {Number(order.total_amount).toLocaleString()}</p>
        </div>
      </div>

      {nextStatuses.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-wider text-muted">Advance order:</span>
          {nextStatuses.map((next) => (
            <Button
              key={next}
              variant="ghost"
              className="px-3 py-1 text-xs capitalize"
              disabled={changeStatus.isPending}
              onClick={() => changeStatus.mutate(next)}
            >
              → {next.replace(/_/g, " ")}
            </Button>
          ))}
        </div>
      )}
      {statusError && <div className="mb-4"><ErrorState message={statusError} /></div>}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <h2 className="mb-3 font-display text-lg text-forest">Items</h2>
          <div className="space-y-2 text-sm">
            {order.items.map((item) => (
              <div key={item.id} className="flex justify-between border-b border-hairline/60 pb-2">
                <span className="font-mono text-xs text-muted">
                  {item.animal_id
                    ? `Animal ${item.animal_id.slice(0, 8)}…`
                    : `Crop planting ${item.crop_planting_id?.slice(0, 8)}… × ${item.quantity}`}
                </span>
                <span className="font-medium text-ink">KES {(Number(item.price) * Number(item.quantity)).toLocaleString()}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 border-t border-hairline pt-3 text-sm text-muted">
            Delivery: <span className="capitalize text-ink">{order.delivery_option}</span>
            {order.delivery_address && ` - ${order.delivery_address}`}
          </div>
        </Card>

        <Card>
          <h2 className="mb-3 font-display text-lg text-forest">Status history</h2>
          {order.status_events.length === 0 ? (
            <p className="text-sm text-muted">No status changes yet.</p>
          ) : (
            <ol className="relative space-y-4 border-l border-hairline pl-6">
              {order.status_events.map((event) => (
                <li key={event.id} className="relative">
                  <span className="absolute -left-[27px] top-1 h-2.5 w-2.5 rounded-full bg-brass" />
                  <p className="text-sm font-medium capitalize text-ink">
                    {event.from_status ? `${event.from_status.replace(/_/g, " ")} → ` : ""}
                    {event.to_status.replace(/_/g, " ")}
                  </p>
                  <p className="text-xs text-muted">{new Date(event.changed_at).toLocaleString()}</p>
                  {event.reason && <p className="text-xs text-muted">{event.reason}</p>}
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>

      <InvoiceSection orderId={order.id} orderStatus={order.status} />
      {order.status === "payment_pending" && (
        <RecordPaymentSection orderId={order.id} />
      )}
    </AdminShell>
  );
}

function RecordPaymentSection({ orderId }: { orderId: string }) {
  const queryClient = useQueryClient();
  const [provider, setProvider] = useState<"mock" | "mpesa" | "stripe">("mock");
  const [phoneOrToken, setPhoneOrToken] = useState("");
  const [error, setError] = useState<string | null>(null);

  const initiate = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/payments/${provider}`, {
        method: "POST", body: JSON.stringify({ order_id: orderId, phone_or_token: phoneOrToken }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["order", orderId] });
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to initiate payment"),
  });

  return (
    <Card className="mt-4">
      <h2 className="mb-3 font-display text-lg text-forest">Record payment</h2>
      <p className="mb-3 text-xs text-muted">
        Initiates a payment with the selected provider. The order only moves to "paid" once the
        provider confirms - never immediately on this click (spec §20: never trust client-reported
        payment status).
      </p>
      {error && <div className="mb-3"><ErrorState message={error} /></div>}
      {initiate.isSuccess && (
        <p className="mb-3 text-sm text-moss">
          Payment initiated - waiting for provider confirmation. Refresh to check status.
        </p>
      )}
      <form
        onSubmit={(e) => { e.preventDefault(); initiate.mutate(); }}
        className="flex items-end gap-2"
      >
        <div className="flex-1">
          <label className="mb-1 block text-sm font-medium text-ink">Provider</label>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value as typeof provider)}
            className="w-full rounded-md border border-hairline bg-white px-3 py-2 text-sm"
          >
            <option value="mock">Mock (testing)</option>
            <option value="mpesa">M-Pesa</option>
            <option value="stripe">Stripe</option>
          </select>
        </div>
        <div className="flex-1">
          <Input
            label={provider === "mpesa" ? "Phone number" : "Phone / payment token"}
            required value={phoneOrToken} onChange={(e) => setPhoneOrToken(e.target.value)}
          />
        </div>
        <Button type="submit" disabled={initiate.isPending}>
          {initiate.isPending ? "Initiating…" : "Initiate payment"}
        </Button>
      </form>
    </Card>
  );
}

function InvoiceSection({ orderId, orderStatus }: { orderId: string; orderStatus: string }) {
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  const invoiceQuery = useQuery<Invoice>({
    queryKey: ["invoice", orderId],
    queryFn: () => apiFetch<Invoice>(`/api/v1/finance/orders/${orderId}/invoice`),
    // An invoice only exists once a payment has actually succeeded - no
    // point querying (and logging a 404) for orders that never got that far.
    enabled: !["pending", "payment_pending", "cancelled", "failed"].includes(orderStatus),
    retry: false,
  });

  if (!invoiceQuery.data) return null;
  const invoice = invoiceQuery.data;

  return (
    <Card className="mt-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-lg text-forest">Invoice {invoice.invoice_number}</h2>
          <p className="text-sm text-muted">
            Subtotal KES {Number(invoice.subtotal).toLocaleString()}
            {Number(invoice.tax_amount) > 0 && ` + tax KES ${Number(invoice.tax_amount).toLocaleString()}`}
            {" "}= <span className="font-medium text-ink">KES {Number(invoice.total).toLocaleString()}</span>
          </p>
        </div>
        <Button
          variant="ghost"
          disabled={downloading}
          onClick={async () => {
            setDownloading(true);
            setDownloadError(null);
            try {
              await apiDownload(`/api/v1/finance/orders/${orderId}/invoice.pdf`, `${invoice.invoice_number}.pdf`);
            } catch (err) {
              setDownloadError(err instanceof ApiError ? err.message : "Failed to download invoice");
            } finally {
              setDownloading(false);
            }
          }}
        >
          {downloading ? "Downloading…" : "Download PDF"}
        </Button>
      </div>
      {downloadError && <div className="mt-2"><ErrorState message={downloadError} /></div>}
    </Card>
  );
}

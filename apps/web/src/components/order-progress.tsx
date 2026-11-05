"use client";

import { Check } from "lucide-react";
import clsx from "clsx";

/** Where an order is on its way to the customer, for the account pages. Purely a readout of the order's existing
 * status: it changes nothing and an unknown status simply shows no tracker. */
export const ORDER_STEPS = ["Placed", "Paid", "Preparing", "On the way", "Delivered"] as const;

const STEP_OF: Record<string, number> = {
  pending: 0, payment_pending: 0, paid: 1, processing: 2, ready_for_fulfillment: 2, dispatched: 3, delivered: 4, completed: 4,
};
const STOPPED: Record<string, string> = {
  cancelled: "This order was cancelled.", failed: "This order could not be completed.",
  refunded: "This order was refunded.", partially_refunded: "This order was partly refunded.",
};

export const IN_PROGRESS = new Set(["pending", "payment_pending", "paid", "processing", "ready_for_fulfillment", "dispatched"]);
export const PAID_OR_BEYOND = new Set(["paid", "processing", "ready_for_fulfillment", "dispatched", "delivered", "completed"]);

export function OrderProgress({ status, compact = false }: { status: string; compact?: boolean }) {
  if (STOPPED[status]) return <p className="text-xs text-muted">{STOPPED[status]}</p>;
  const current = STEP_OF[status];
  if (current === undefined) return null;
  return (
    <ol className="grid grid-cols-5" aria-label="Order progress">
      {ORDER_STEPS.map((label, i) => {
        const done = i < current || current === ORDER_STEPS.length - 1;
        const active = i === current && !done;
        return (
          <li key={label} className="relative flex flex-col items-center gap-1">
            {i < ORDER_STEPS.length - 1 && (
              <span className={clsx("absolute left-1/2 top-2.5 h-px w-full", i < current ? "bg-moss" : "bg-hairline")} aria-hidden />
            )}
            <span
              className={clsx(
                "relative z-10 flex h-5 w-5 items-center justify-center rounded-full border text-[10px]",
                done && "border-moss bg-moss text-white",
                active && "border-brass bg-[#F6EBD3] text-brass-dark",
                !done && !active && "border-hairline bg-white text-muted",
              )}
            >
              {done ? <Check className="h-3 w-3" aria-hidden /> : i + 1}
            </span>
            {!compact && <span className={clsx("text-center text-[11px] leading-tight", active ? "font-medium text-ink" : "text-muted")}>{label}</span>}
          </li>
        );
      })}
    </ol>
  );
}

import { clsx } from "clsx";
import type { ReactNode } from "react";

/**
 * Small hand-rolled design system rather than a component library - see
 * docs/design-notes.md. Every primitive here derives from the token palette
 * in tailwind.config.ts.
 */

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={clsx("rounded-lg border border-hairline bg-white/60 p-6", className)}>
      {children}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <Card className="flex flex-col gap-1">
      <span className="text-xs font-medium uppercase tracking-wider text-muted">{label}</span>
      <span className="font-display text-3xl text-forest">{value}</span>
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </Card>
  );
}

/** The signature motif: every animal_number renders as a stamped ear-tag
 * chip - a small hole-punch dot plus monospaced ID, evoking the literal
 * physical tag every animal in this system wears. */
export function TagChip({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-tag border border-hairline bg-paper px-2 py-1 font-mono text-xs text-ink">
      <span className="h-1.5 w-1.5 rounded-full bg-brass" aria-hidden />
      {children}
    </span>
  );
}

const statusStyles: Record<string, string> = {
  // Livestock statuses
  active: "bg-moss/10 text-moss border-moss/30",
  for_sale: "bg-brass/10 text-brass-dark border-brass/30",
  reserved: "bg-amber-100 text-amber-800 border-amber-300",
  sold: "bg-forest/10 text-forest border-forest/30",
  deceased: "bg-clay/10 text-clay border-clay/30",
  quarantined: "bg-clay/10 text-clay border-clay/30",
  culled: "bg-clay/10 text-clay border-clay/30",
  transferred: "bg-muted/10 text-muted border-muted/30",
  missing: "bg-clay/10 text-clay border-clay/30",
  archived: "bg-muted/10 text-muted border-muted/30",
  // Crop planting statuses
  growing: "bg-moss/10 text-moss border-moss/30",
  ready_for_harvest: "bg-brass/10 text-brass-dark border-brass/30",
  harvesting: "bg-amber-100 text-amber-800 border-amber-300",
  harvested: "bg-forest/10 text-forest border-forest/30",
  fallow: "bg-muted/10 text-muted border-muted/30",
  // Order statuses
  pending: "bg-amber-100 text-amber-800 border-amber-300",
  payment_pending: "bg-brass/10 text-brass-dark border-brass/30",
  paid: "bg-moss/10 text-moss border-moss/30",
  processing: "bg-brass/10 text-brass-dark border-brass/30",
  ready_for_fulfillment: "bg-brass/10 text-brass-dark border-brass/30",
  dispatched: "bg-forest/10 text-forest border-forest/30",
  delivered: "bg-forest/10 text-forest border-forest/30",
  completed: "bg-moss/10 text-moss border-moss/30",
  cancelled: "bg-clay/10 text-clay border-clay/30",
  refunded: "bg-clay/10 text-clay border-clay/30",
  partially_refunded: "bg-clay/10 text-clay border-clay/30",
  failed: "bg-clay/10 text-clay border-clay/30",
};

export function StatusBadge({ status }: { status: string }) {
  const style = statusStyles[status] ?? "bg-muted/10 text-muted border-muted/30";
  return (
    <span className={clsx("inline-block rounded-full border px-2 py-0.5 text-xs font-medium capitalize", style)}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function Button({
  children,
  variant = "primary",
  className,
  ...props
}: {
  children: ReactNode;
  variant?: "primary" | "ghost";
  className?: string;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={clsx(
        "rounded-md px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-forest text-paper hover:bg-forest-dark",
        variant === "ghost" && "border border-hairline text-ink hover:bg-hairline/40",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function Input({
  label,
  error,
  className,
  ...props
}: { label?: string; error?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div>
      {label && (
        <label className="mb-1 block text-sm font-medium text-ink" htmlFor={props.id}>
          {label}
        </label>
      )}
      <input
        className={clsx(
          "w-full rounded-md border border-hairline bg-white px-3 py-2 text-sm focus:border-brass focus:outline-none",
          error && "border-clay",
          className,
        )}
        {...props}
      />
      {error && <p className="mt-1 text-xs text-clay">{error}</p>}
    </div>
  );
}

export function Select({
  label,
  error,
  className,
  children,
  ...props
}: {
  label?: string;
  error?: string;
  children: ReactNode;
} & React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div>
      {label && (
        <label className="mb-1 block text-sm font-medium text-ink" htmlFor={props.id}>
          {label}
        </label>
      )}
      <select
        className={clsx(
          "w-full rounded-md border border-hairline bg-white px-3 py-2 text-sm focus:border-brass focus:outline-none",
          error && "border-clay",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      {error && <p className="mt-1 text-xs text-clay">{error}</p>}
    </div>
  );
}

export function Textarea({
  label,
  error,
  className,
  ...props
}: { label?: string; error?: string } & React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <div>
      {label && (
        <label className="mb-1 block text-sm font-medium text-ink" htmlFor={props.id}>
          {label}
        </label>
      )}
      <textarea
        className={clsx(
          "w-full rounded-md border border-hairline bg-white px-3 py-2 text-sm focus:border-brass focus:outline-none",
          error && "border-clay",
          className,
        )}
        {...props}
      />
      {error && <p className="mt-1 text-xs text-clay">{error}</p>}
    </div>
  );
}

export function Modal({
  open,
  onClose,
  title,
  children,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Width: "md" (default, unchanged) suits short forms; "lg" gives roomier forms such as multi-line orders. */
  size?: "md" | "lg";
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 px-4">
      <div className={clsx("max-h-[90vh] w-full overflow-y-auto rounded-lg border border-hairline bg-paper p-6 shadow-xl", size === "lg" ? "max-w-2xl" : "max-w-lg")}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-lg text-forest">{title}</h2>
          <button onClick={onClose} className="text-muted hover:text-ink" aria-label="Close">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-hairline py-16 text-center">
      <p className="font-display text-lg text-forest">{title}</p>
      <p className="max-w-sm text-sm text-muted">{body}</p>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-clay/30 bg-clay/5 px-4 py-3 text-sm text-clay">
      {message}
    </div>
  );
}

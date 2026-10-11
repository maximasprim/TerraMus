"use client";

import { clsx } from "clsx";

/** Segmented "last N months" control. Plain buttons with aria-pressed - no extra dependency. */
export function RangePicker({
  value, options, onChange, label = "Time range",
}: { value: number; options: number[]; onChange: (months: number) => void; label?: string }) {
  return (
    <div role="group" aria-label={label} className="inline-flex overflow-hidden rounded-md border border-hairline bg-white/60 text-sm">
      {options.map((months) => (
        <button
          key={months}
          type="button"
          aria-pressed={value === months}
          onClick={() => onChange(months)}
          className={clsx(
            "px-3 py-1.5 transition-colors",
            value === months ? "bg-forest text-paper" : "text-ink hover:bg-hairline/50",
          )}
        >
          {months}M
        </button>
      ))}
    </div>
  );
}

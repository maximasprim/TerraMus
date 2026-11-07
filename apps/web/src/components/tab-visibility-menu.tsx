"use client";

import { useEffect, useRef, useState } from "react";
import { ALWAYS_SHOWN_TABS } from "@/lib/use-hidden-tabs";

/** A small "Tabs" menu: tick the tabs you want to see. `tabs` are the ones that apply to this page. */
export function TabVisibilityMenu({
  tabs,
  hidden,
  onToggle,
  onReset,
}: {
  tabs: readonly string[];
  hidden: readonly string[];
  onToggle: (tab: string) => void;
  onReset: () => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const hiddenHere = tabs.filter((t) => hidden.includes(t)).length;

  useEffect(() => {
    if (!open) return;
    const away = (e: Event) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("touchstart", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("touchstart", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  return (
    <div ref={box} className="relative shrink-0 pb-1">
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="rounded border border-hairline px-2 py-1 text-xs text-forest hover:bg-forest/5"
      >
        Tabs{hiddenHere > 0 ? ` (${hiddenHere} hidden)` : ""}
      </button>
      {open && (
        <div className="absolute right-0 top-full z-20 mt-1 w-60 rounded-md border border-hairline bg-paper p-3 shadow-lg">
          <p className="mb-2 text-xs uppercase tracking-wider text-muted">Show these tabs</p>
          {tabs.map((t) => {
            const locked = ALWAYS_SHOWN_TABS.includes(t);
            return (
              <label key={t} className="flex cursor-pointer items-center gap-2 py-1 text-sm text-ink">
                <input type="checkbox" checked={!hidden.includes(t)} disabled={locked} onChange={() => onToggle(t)} />
                {t}
                {locked && <span className="text-xs text-muted">always shown</span>}
              </label>
            );
          })}
          <div className="mt-2 flex items-center justify-between border-t border-hairline pt-2">
            <button type="button" disabled={hiddenHere === 0} onClick={onReset} className="text-xs text-forest underline disabled:opacity-40 disabled:no-underline">
              Show all tabs
            </button>
            <button type="button" onClick={() => setOpen(false)} className="text-xs text-muted hover:text-ink">Done</button>
          </div>
          <p className="mt-2 text-xs text-muted">Only changes what you see here, on this device. Nothing is deleted.</p>
        </div>
      )}
    </div>
  );
}

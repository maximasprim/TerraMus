"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui";
import {
  isBlankTagRow, parseTagList, withTrailingBlankTag,
  type TagEntry, type TagRow, type TagRowsAnalysis,
} from "@/lib/tag-rows";

// The same "one row per animal, a Tag box and a separate Weight box" entry as the weigh-day form, for Feedlot
// Sales (with a price column) and for adding animals to an intake batch. It only edits the rows: the page that
// uses it owns the rows, runs analyseTagRows() and decides what saving does.

const CELL = "w-full rounded-md border bg-white px-3 py-2.5 text-base focus:border-brass focus:outline-none sm:py-2 sm:text-sm";

export interface RowNote { text: string; error?: boolean }

export function TagRowsEditor({
  idPrefix, rows, setRows, analysis, allowPrice = false,
  weightLabel = "Weight (kg)", weightPlaceholder = "e.g. 349", priceLabel = "Price per kg", pricePlaceholder = "optional",
  tagPlaceholder = "e.g. B0130", pasteHelp, showAllProblems = false, rowNote, onEdit,
}: {
  idPrefix: string;
  rows: TagRow[];
  setRows: (updater: (prev: TagRow[]) => TagRow[]) => void;
  analysis: TagRowsAnalysis;
  allowPrice?: boolean;
  weightLabel?: string; weightPlaceholder?: string; priceLabel?: string; pricePlaceholder?: string; tagPlaceholder?: string;
  pasteHelp?: string;
  /** Show every row's problems now (after a failed save attempt) instead of only rows already left. */
  showAllProblems?: boolean;
  /** Extra per-row remark from the page, e.g. "not an active animal" (error) or an amount (information). */
  rowNote?: (entry: TagEntry) => RowNote | null;
  /** Called whenever the person changes anything (the page can clear an earlier result). */
  onEdit?: () => void;
}) {
  const [touched, setTouched] = useState<Set<number>>(new Set());
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [pasteBad, setPasteBad] = useState<string[]>([]);
  const inputs = useRef(new Map<string, HTMLInputElement>());
  const cols = allowPrice ? "grid-cols-[1.75rem_1fr_1fr_1fr_2.25rem]" : "grid-cols-[1.75rem_1fr_1fr_2.25rem]";
  const entryByRow = new Map<number, TagEntry>();
  {
    let k = 0;
    for (const r of rows) {
      if (isBlankTagRow(r) || analysis.problems.has(r.id)) continue;
      entryByRow.set(r.id, analysis.entries[k++]);
    }
  }

  const setCell = (id: number, field: "tag" | "weight" | "price", value: string) => {
    setRows((prev) => withTrailingBlankTag(prev.map((r) => (r.id === id ? { ...r, [field]: value } : r))));
    onEdit?.();
  };
  const removeRow = (id: number) => { setRows((prev) => withTrailingBlankTag(prev.filter((r) => r.id !== id))); onEdit?.(); };
  const touch = (id: number) => setTouched((prev) => (prev.has(id) ? prev : new Set(prev).add(id)));
  const focusCell = (id: number, field: "tag" | "weight" | "price") => inputs.current.get(`${id}:${field}`)?.focus();
  const reg = (id: number, field: string) => (el: HTMLInputElement | null) => {
    if (el) inputs.current.set(`${id}:${field}`, el); else inputs.current.delete(`${id}:${field}`);
  };

  const addPasted = () => {
    const { rows: added, bad } = parseTagList(pasteText, allowPrice);
    setRows((prev) => withTrailingBlankTag([...prev.filter((r) => !isBlankTagRow(r)), ...added]));
    setPasteBad(bad);
    setPasteText(bad.join("\n"));            // leave only the lines that were not understood, ready to fix
    if (bad.length === 0) setPasteOpen(false);
    onEdit?.();
  };

  return (
    <div>
      <div className={`mb-1 grid ${cols} gap-2 text-sm font-medium text-ink`}>
        <span /><span>Tag</span><span>{weightLabel}</span>{allowPrice && <span>{priceLabel}</span>}<span />
      </div>
      <div className="space-y-2">
        {rows.map((r, i) => {
          const p = analysis.problems.get(r.id);
          const shown = showAllProblems || touched.has(r.id);
          const entry = entryByRow.get(r.id);
          const note = entry && rowNote ? rowNote(entry) : null;
          const problemText = shown && p ? [p.tag, p.weight, p.price].filter(Boolean).join(" · ") : "";
          const next = (field: "tag" | "weight" | "price") => {
            if (field === "tag") focusCell(r.id, "weight");
            else if (field === "weight" && allowPrice) focusCell(r.id, "price");
            else { const n = rows[i + 1]; if (n) focusCell(n.id, "tag"); }
          };
          const enter = (field: "tag" | "weight" | "price") => (e: React.KeyboardEvent) => {
            if (e.key === "Enter") { e.preventDefault(); next(field); }
          };
          return (
            <div key={r.id} onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) touch(r.id); }}>
              <div className={`grid ${cols} items-center gap-2`}>
                <span className="text-right text-xs text-muted">{i + 1}</span>
                <input ref={reg(r.id, "tag")} aria-label={`Tag, row ${i + 1}`} value={r.tag} placeholder={tagPlaceholder}
                  autoCapitalize="characters" autoCorrect="off" autoComplete="off" spellCheck={false} enterKeyHint="next"
                  onChange={(e) => setCell(r.id, "tag", e.target.value)} onKeyDown={enter("tag")}
                  className={`${CELL} font-mono ${shown && p?.tag ? "border-clay" : "border-hairline"}`} />
                <input ref={reg(r.id, "weight")} aria-label={`${weightLabel}, row ${i + 1}`} value={r.weight} placeholder={weightPlaceholder}
                  inputMode="decimal" autoComplete="off" enterKeyHint="next"
                  onChange={(e) => setCell(r.id, "weight", e.target.value)} onKeyDown={enter("weight")}
                  className={`${CELL} ${shown && p?.weight ? "border-clay" : "border-hairline"}`} />
                {allowPrice && (
                  <input ref={reg(r.id, "price")} aria-label={`${priceLabel}, row ${i + 1}`} value={r.price} placeholder={pricePlaceholder}
                    inputMode="decimal" autoComplete="off" enterKeyHint="next"
                    onChange={(e) => setCell(r.id, "price", e.target.value)} onKeyDown={enter("price")}
                    className={`${CELL} ${shown && p?.price ? "border-clay" : "border-hairline"}`} />
                )}
                <button type="button" aria-label={`Remove row ${i + 1}`} disabled={isBlankTagRow(r)} onClick={() => removeRow(r.id)}
                  className="h-9 rounded text-muted hover:text-clay disabled:opacity-20">✕</button>
              </div>
              {problemText && <p className="ml-8 mt-0.5 text-xs text-clay">{problemText}</p>}
              {!problemText && note && <p className={`ml-8 mt-0.5 text-xs ${note.error ? "text-clay" : "text-muted"}`}>{note.text}</p>}
            </div>
          );
        })}
      </div>

      <div className="mt-3">
        <button type="button" onClick={() => setPasteOpen((o) => !o)} className="text-xs text-forest underline">
          {pasteOpen ? "Hide pasted list" : "Paste a list instead"}
        </button>
        {pasteOpen && (
          <div className="mt-2 space-y-2">
            <label htmlFor={`${idPrefix}-paste`} className="block text-xs text-muted">
              {pasteHelp ?? "One animal per line: tag, then weight in kg (for example A01 349). Use a dot for decimals."}
            </label>
            <textarea id={`${idPrefix}-paste`} rows={6} value={pasteText} onChange={(e) => setPasteText(e.target.value)}
              placeholder={allowPrice ? "A01 324\nA02 331 335\nA03, 318" : "A01 210\nA02 200\nA03, 190"}
              className="w-full rounded-md border border-hairline bg-white px-3 py-2 font-mono text-sm focus:border-brass focus:outline-none" />
            <Button type="button" variant="ghost" disabled={!pasteText.trim()} onClick={addPasted}>Add to the list</Button>
            {pasteBad.length > 0 && <p className="text-xs text-clay">{pasteBad.length} line(s) not understood and left above for you to fix: {pasteBad.slice(0, 3).join(" | ")}</p>}
          </div>
        )}
      </div>
    </div>
  );
}

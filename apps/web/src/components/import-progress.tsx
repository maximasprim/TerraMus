"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Progress for a file import / preview, so nobody is left wondering whether it is working.
 *
 * Two honest phases:
 *   1. Uploading - a REAL percentage (bytes sent / file size), taking the first 30% of the bar.
 *   2. Checking  - the server reads the workbook in one go and cannot report its own progress, so this phase is an
 *      ESTIMATE that eases from 30% towards 95% (never claiming "done") and is shown with a "≈". It jumps to 100%
 *      only when the server actually answers. A running timer shows the page has not stalled.
 */
export type ImportPhase = "idle" | "uploading" | "checking" | "done";

export interface ImportProgressState { phase: ImportPhase; percent: number; elapsed: number }

const UPLOAD_SHARE = 30;      // % of the bar given to the (real) upload
const CHECK_CEILING = 95;     // the estimate never passes this until the server replies

export function useImportProgress() {
  const [state, setState] = useState<ImportProgressState>({ phase: "idle", percent: 0, elapsed: 0 });
  const startedAt = useRef(0);
  const sizeMb = useRef(0);
  const phase = useRef<ImportPhase>("idle");
  const uploaded = useRef(0);
  const checkStart = useRef(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stop = () => { if (timer.current) { clearInterval(timer.current); timer.current = null; } };

  const tick = useCallback(() => {
    const now = Date.now();
    // Some networks/proxies never report upload progress. Rather than sit at 0%, fall back to the estimate.
    if (phase.current === "uploading" && uploaded.current === 0 && now - startedAt.current > 2500) {
      phase.current = "checking";
      checkStart.current = now;
    }
    let percent: number;
    if (phase.current === "uploading") {
      percent = uploaded.current * UPLOAD_SHARE;
    } else {
      // time constant grows with file size: bigger workbooks take longer to read
      const tau = 6 + sizeMb.current * 4;
      const t = (now - checkStart.current) / 1000;
      percent = UPLOAD_SHARE + (CHECK_CEILING - UPLOAD_SHARE) * (1 - Math.exp(-t / tau));
    }
    setState((prev) => ({
      phase: phase.current,
      percent: Math.min(CHECK_CEILING, Math.max(prev.percent, Math.round(percent))),   // never moves backwards
      elapsed: Math.floor((now - startedAt.current) / 1000),
    }));
  }, []);

  /** Call just before the request is sent. */
  const begin = useCallback((fileBytes: number) => {
    stop();
    if (hideTimer.current) clearTimeout(hideTimer.current);
    startedAt.current = Date.now();
    sizeMb.current = fileBytes / (1024 * 1024);
    uploaded.current = 0;
    phase.current = "uploading";
    setState({ phase: "uploading", percent: 0, elapsed: 0 });
    timer.current = setInterval(tick, 200);
  }, [tick]);

  /** Pass to apiUpload's onProgress. */
  const onUpload = useCallback((fraction: number) => {
    uploaded.current = Math.min(1, Math.max(0, fraction));
    if (fraction >= 1 && phase.current === "uploading") {
      phase.current = "checking";
      checkStart.current = Date.now();
    }
  }, []);

  /** Call when the request finishes, whether it worked or not. */
  const end = useCallback((ok: boolean) => {
    stop();
    phase.current = "idle";
    if (!ok) { setState({ phase: "idle", percent: 0, elapsed: 0 }); return; }
    setState((prev) => ({ phase: "done", percent: 100, elapsed: Math.floor((Date.now() - startedAt.current) / 1000) || prev.elapsed }));
    hideTimer.current = setTimeout(() => setState({ phase: "idle", percent: 0, elapsed: 0 }), 1500);
  }, []);

  useEffect(() => () => { stop(); if (hideTimer.current) clearTimeout(hideTimer.current); }, []);

  return { state, begin, onUpload, end };
}

export function ImportProgressBar({ state, action = "Checking your file" }: { state: ImportProgressState; action?: string }) {
  if (state.phase === "idle") return null;
  const estimating = state.phase === "checking";
  const label = state.phase === "uploading" ? "Uploading file…" : state.phase === "checking" ? `${action}…` : "Finished";
  return (
    <div className="space-y-1.5 rounded-md border border-hairline bg-paper p-3" aria-live="polite">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="font-medium text-ink">{label}</span>
        <span className="tabular-nums text-ink">{estimating ? "≈ " : ""}{state.percent}%</span>
      </div>
      <div
        role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={state.percent}
        className="h-2 w-full overflow-hidden rounded-full bg-hairline"
      >
        <div className="h-full rounded-full bg-forest transition-[width] duration-300 ease-out" style={{ width: `${state.percent}%` }} />
      </div>
      <p className="text-xs text-muted">
        {state.phase === "done" ? "Done." : `${state.elapsed}s elapsed. ${state.elapsed >= 15 ? "Large files can take a minute. Please keep this page open." : "Nothing is saved until you confirm the import."}`}
      </p>
    </div>
  );
}

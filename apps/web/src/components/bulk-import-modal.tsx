"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Modal, ErrorState } from "@/components/ui";
import { apiUpload, ApiError } from "@/lib/api";
import type { BulkImportResult } from "@/lib/types";

/** Preview (dry_run=true) then confirm (dry_run=false) - mirrors spec
 * §73's Upload -> Validate -> Preview -> Show errors -> Confirm -> Import
 * flow exactly, reused across every bulk-import endpoint the backend
 * exposes (customers/suppliers/inventory items/livestock) rather than
 * writing this logic four times. */
export function BulkImportModal({
  open,
  onClose,
  endpoint,
  invalidateKeys,
  extraParams,
}: {
  open: boolean;
  onClose: () => void;
  endpoint: string;
  invalidateKeys: string[][];
  /** Extra query params the endpoint needs beyond dry_run, e.g. livestock's farm_id. */
  extraParams?: Record<string, string>;
}) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<BulkImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useMutation({
    mutationFn: (dryRun: boolean) => {
      if (!file) throw new Error("Choose a CSV file first");
      const params = new URLSearchParams({ dry_run: String(dryRun), ...(extraParams ?? {}) });
      const formData = new FormData();
      formData.append("file", file);
      return apiUpload<BulkImportResult>(`${endpoint}?${params.toString()}`, formData);
    },
    onSuccess: (data, dryRun) => {
      setResult(data);
      setError(null);
      if (!dryRun) {
        invalidateKeys.forEach((key) => queryClient.invalidateQueries({ queryKey: key }));
      }
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Import failed"),
  });

  const reset = () => {
    setFile(null);
    setResult(null);
    setError(null);
  };

  return (
    <Modal open={open} onClose={() => { reset(); onClose(); }} title="Bulk import from CSV">
      <div className="space-y-3">
        {error && <ErrorState message={error} />}
        <input
          type="file"
          accept=".csv"
          onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); }}
          className="w-full rounded-md border border-hairline bg-white px-3 py-2 text-sm"
        />

        {result && (
          <div className="rounded-md border border-hairline bg-paper p-3 text-sm">
            <p className="font-medium text-ink">
              {result.dry_run ? "Preview" : "Import complete"}: {result.valid_rows} of {result.total_rows} rows valid
              {!result.dry_run && `, ${result.imported} imported`}.
            </p>
            {result.errors.length > 0 && (
              <ul className="mt-2 space-y-1 text-xs text-clay">
                {result.errors.map((e, i) => (
                  <li key={i}>Row {e.row}: {e.error}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="flex gap-2">
          <Button
            variant="ghost"
            className="flex-1"
            disabled={!file || run.isPending}
            onClick={() => run.mutate(true)}
          >
            {run.isPending ? "Checking…" : "Preview"}
          </Button>
          <Button
            className="flex-1"
            disabled={!file || !result || run.isPending}
            onClick={() => run.mutate(false)}
          >
            {run.isPending ? "Importing…" : "Confirm import"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

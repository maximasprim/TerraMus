"use client";

import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ImageIcon, Trash2, Upload } from "lucide-react";
import { Input } from "@/components/ui";
import { apiFetch, ApiError, API_BASE } from "@/lib/api";
import type { SiteImageUpload } from "@/lib/types";

// Mirrors the server limits (apps/api commerce/images.py) for instant feedback; the server re-validates everything.
const MAX_MB = 5;
const ACCEPT = "image/jpeg,image/png,image/webp";

/** Image input for the site content screens: paste a URL (as before) OR upload a file from the device.
 * Either way the value handed to `onChange` is a plain URL, so whatever stores/renders it is unchanged. */
export function ImageUploadField({
  label, kind, value, onChange, required, hint,
}: {
  label: string;
  kind: "logo" | "banner";
  value: string;
  onChange: (url: string) => void;
  required?: boolean;
  hint?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [previewFailed, setPreviewFailed] = useState(false);

  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return apiFetch<SiteImageUpload>(`/api/v1/cms/images?kind=${kind}`, { method: "POST", body: form });
    },
    onSuccess: (res) => {
      setError(null);
      setPreviewFailed(false);
      // Always the API's own image URL (it redirects to the CDN when the farm uses bucket storage): that form carries the
      // image id, which is how deleting a banner / replacing a logo also removes the uploaded file.
      onChange(`${API_BASE}/api/v1/media/site-images/${res.id}`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Upload failed"),
  });

  const pick = (list: FileList | null) => {
    const file = list?.[0];
    if (inputRef.current) inputRef.current.value = ""; // allow re-picking the same file after an error
    if (!file) return;
    if (!ACCEPT.split(",").includes(file.type)) return setError(`"${file.name}" isn't a JPEG, PNG or WebP image.`);
    if (file.size > MAX_MB * 1024 * 1024) return setError(`"${file.name}" is larger than ${MAX_MB} MB.`);
    setError(null);
    upload.mutate(file);
  };

  return (
    <div className="space-y-2">
      <Input
        label={`${label} URL`}
        required={required}
        placeholder="https://… or upload below"
        value={value}
        onChange={(e) => { setPreviewFailed(false); onChange(e.target.value); }}
      />

      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); if (!upload.isPending) pick(e.dataTransfer.files); }}
        className={`flex items-center gap-3 rounded-md border border-dashed p-3 ${dragging ? "border-brass bg-brass/10" : "border-hairline"}`}
      >
        <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded bg-hairline/30 text-muted">
          {value && !previewFailed ? (
            // eslint-disable-next-line @next/next/no-img-element -- admin preview of the org-supplied image
            <img src={value} alt="" onError={() => setPreviewFailed(true)} className="h-full w-full object-cover" />
          ) : (
            <ImageIcon className="h-6 w-6" aria-hidden />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted">
            {hint ?? "No URL? Upload a photo from your device"} - JPEG, PNG or WebP, up to {MAX_MB} MB. Drag a file here or:
          </p>
          <div className="mt-1.5 flex flex-wrap gap-2">
            <input ref={inputRef} type="file" accept={ACCEPT} className="hidden" onChange={(e) => pick(e.target.files)} />
            <button
              type="button"
              disabled={upload.isPending}
              onClick={() => inputRef.current?.click()}
              className="inline-flex items-center gap-1.5 rounded-md border border-hairline bg-white px-3 py-1.5 text-xs font-medium text-forest hover:bg-forest/5 disabled:opacity-50"
            >
              <Upload className="h-3.5 w-3.5" aria-hidden />
              {upload.isPending ? "Uploading…" : value ? "Replace image" : "Upload image"}
            </button>
            {value && (
              <button
                type="button"
                disabled={upload.isPending}
                onClick={() => { setError(null); onChange(""); }}
                className="inline-flex items-center gap-1.5 rounded-md border border-clay/30 px-3 py-1.5 text-xs text-clay hover:bg-clay/5 disabled:opacity-50"
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden /> Clear
              </button>
            )}
          </div>
        </div>
      </div>
      {error && <p className="text-xs text-clay">{error}</p>}
    </div>
  );
}

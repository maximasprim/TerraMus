"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera } from "lucide-react";
import { Button, Card, ErrorState } from "@/components/ui";
import { apiBlob, apiFetch, apiUpload, ApiError } from "@/lib/api";

/** Phone cameras produce 3-10 MB photos; the server accepts up to 5 MB and stores at most 900 px. Shrinking
 * here keeps uploads fast on a weak connection and means a normal phone photo is never rejected. */
async function shrink(file: File, maxEdge = 1600): Promise<Blob> {
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, maxEdge / Math.max(bmp.width, bmp.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * scale);
    canvas.height = Math.round(bmp.height * scale);
    canvas.getContext("2d")?.drawImage(bmp, 0, 0, canvas.width, canvas.height);
    const blob: Blob | null = await new Promise((res) => canvas.toBlob(res, "image/jpeg", 0.85));
    return blob ?? file;
  } catch {
    return file;   // unsupported format in this browser: let the server judge the original
  }
}

export function AnimalPhotoCard({ animalId, canEdit }: { animalId: string; canEdit: boolean }) {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let alive = true;
    let made: string | null = null;
    setLoading(true);
    apiBlob(`/api/v1/livestock/${animalId}/photo`)
      .then((b) => { if (alive) { made = b ? URL.createObjectURL(b) : null; setUrl(made); } })
      .catch(() => { if (alive) setUrl(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; if (made) URL.revokeObjectURL(made); };
  }, [animalId, version]);

  const upload = useCallback(async (file: File) => {
    setBusy(true); setError(null);
    try {
      const fd = new FormData();
      fd.append("file", await shrink(file), "animal.jpg");
      await apiUpload(`/api/v1/livestock/${animalId}/photo`, fd, { method: "PUT" });
      setVersion((v) => v + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not upload the photo. Check your connection and try again.");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }, [animalId]);

  const remove = async () => {
    if (!window.confirm("Remove this photo?")) return;
    setBusy(true); setError(null);
    try { await apiFetch(`/api/v1/livestock/${animalId}/photo`, { method: "DELETE" }); setVersion((v) => v + 1); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not remove the photo"); }
    finally { setBusy(false); }
  };

  return (
    <Card className="space-y-3 md:col-span-2">
      <h2 className="font-display text-lg text-forest">Photo</h2>
      {loading ? <p className="text-sm text-muted">Loading…</p> : url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="Animal" className="max-h-80 w-full rounded-md object-contain bg-paper" />
      ) : (
        <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-hairline text-sm text-muted">
          <Camera className="mr-2 h-5 w-5" aria-hidden /> No photo yet
        </div>
      )}
      {error && <ErrorState message={error} />}
      {canEdit && (
        <div className="flex gap-2">
          <input ref={input} type="file" accept="image/*" capture="environment" className="hidden" aria-label="Choose animal photo"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); }} />
          <Button variant="ghost" disabled={busy} onClick={() => input.current?.click()}>{busy ? "Working…" : url ? "Replace photo" : "Take or choose photo"}</Button>
          {url && <Button variant="ghost" disabled={busy} onClick={() => void remove()}>Remove</Button>}
        </div>
      )}
    </Card>
  );
}

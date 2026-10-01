"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Star, Trash2, Upload } from "lucide-react";
import { Button, ErrorState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import { imageSrc } from "@/lib/shop-utils";
import type { ListingImage } from "@/lib/types";

// Mirrors the server limits (apps/api commerce/images.py) so people get instant
// feedback; the server remains the authority and re-validates everything.
const MAX_PHOTOS = 8;
const MAX_MB = 5;
const ACCEPT = "image/jpeg,image/png,image/webp";

/** Admin photo manager for one listing. The first photo is the cover: the only
 * one shoppers see on the home page and store grid. All photos appear on the
 * listing's product page. */
export function ListingPhotos({ listingId }: { listingId: string }) {
  const queryClient = useQueryClient();
  const key = ["listing-images", listingId];
  const base = `/api/v1/listings/${listingId}/images`;
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);

  const photosQuery = useQuery<ListingImage[]>({ queryKey: key, queryFn: () => apiFetch<ListingImage[]>(base) });
  const photos = photosQuery.data ?? [];

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: key });
    queryClient.invalidateQueries({ queryKey: ["listings"] }); // the grid's cover thumbnail + photo count
  };
  const fail = (fallback: string) => (err: unknown) => setError(err instanceof ApiError ? err.message : fallback);

  const upload = useMutation({
    mutationFn: (files: File[]) => {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      return apiFetch<ListingImage[]>(base, { method: "POST", body: form });
    },
    onSuccess: () => { setError(null); refresh(); },
    onError: fail("Upload failed"),
  });
  const remove = useMutation({
    mutationFn: (imageId: string) => apiFetch(`${base}/${imageId}`, { method: "DELETE" }),
    onSuccess: () => { setError(null); refresh(); },
    onError: fail("Could not delete the photo"),
  });
  const reorder = useMutation({
    mutationFn: (ids: string[]) => apiFetch<ListingImage[]>(`${base}/order`, { method: "PUT", body: JSON.stringify({ image_ids: ids }) }),
    onSuccess: () => { setError(null); refresh(); },
    onError: fail("Could not reorder the photos"),
  });

  const busy = upload.isPending || remove.isPending || reorder.isPending;

  const onPick = (list: FileList | null) => {
    const files = Array.from(list ?? []);
    if (inputRef.current) inputRef.current.value = ""; // allow re-picking the same file after an error
    if (files.length === 0) return;
    if (photos.length + files.length > MAX_PHOTOS) {
      setError(`A listing can have at most ${MAX_PHOTOS} photos (${photos.length} already uploaded).`);
      return;
    }
    const tooBig = files.find((f) => f.size > MAX_MB * 1024 * 1024);
    if (tooBig) {
      setError(`"${tooBig.name}" is larger than ${MAX_MB} MB.`);
      return;
    }
    const wrongType = files.find((f) => !ACCEPT.split(",").includes(f.type));
    if (wrongType) {
      setError(`"${wrongType.name}" isn't a JPEG, PNG or WebP image.`);
      return;
    }
    setError(null);
    upload.mutate(files);
  };

  const move = (index: number, delta: number) => {
    const ids = photos.map((p) => p.id);
    const target = index + delta;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    reorder.mutate(ids);
  };
  const makeCover = (index: number) => {
    const ids = photos.map((p) => p.id);
    const [picked] = ids.splice(index, 1);
    reorder.mutate([picked, ...ids]);
  };

  return (
    <div className="space-y-4">
      {error && <ErrorState message={error} />}

      <p className="text-sm text-muted">
        The <strong>cover</strong> photo (first) is the only one shown on the home page and store. Shoppers see all
        photos on the product page. JPEG, PNG or WebP, up to {MAX_MB} MB each, {MAX_PHOTOS} per listing. Location
        data is removed from every photo automatically.
      </p>

      {photosQuery.isLoading && <p className="text-sm text-muted">Loading photos…</p>}
      {photosQuery.error && <ErrorState message="Could not load photos" />}

      {photos.length > 0 && (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {photos.map((photo, i) => (
            <li key={photo.id} className="overflow-hidden rounded-lg border border-hairline bg-white">
              <div className="relative aspect-[4/3] bg-hairline/30">
                {/* eslint-disable-next-line @next/next/no-img-element -- served by the API */}
                <img src={imageSrc(photo, true)} alt={`Photo ${i + 1}`} className="absolute inset-0 h-full w-full object-cover" />
                {i === 0 && (
                  <span className="absolute left-2 top-2 flex items-center gap-1 rounded bg-brass px-2 py-0.5 text-[11px] font-semibold text-ink">
                    <Star className="h-3 w-3" aria-hidden /> Cover
                  </span>
                )}
              </div>
              <div className="flex items-center justify-between gap-1 p-2">
                <div className="flex gap-1">
                  <button type="button" aria-label="Move earlier" disabled={busy || i === 0} onClick={() => move(i, -1)} className="rounded border border-hairline p-1.5 text-muted hover:text-forest disabled:opacity-30">
                    <ArrowLeft className="h-3.5 w-3.5" />
                  </button>
                  <button type="button" aria-label="Move later" disabled={busy || i === photos.length - 1} onClick={() => move(i, 1)} className="rounded border border-hairline p-1.5 text-muted hover:text-forest disabled:opacity-30">
                    <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                </div>
                <div className="flex gap-1">
                  {i !== 0 && (
                    <button type="button" disabled={busy} onClick={() => makeCover(i)} className="rounded border border-hairline px-2 py-1 text-xs text-forest hover:bg-forest/5 disabled:opacity-40">
                      Make cover
                    </button>
                  )}
                  <button
                    type="button"
                    aria-label="Delete photo"
                    disabled={busy}
                    onClick={() => { if (window.confirm("Delete this photo?")) remove.mutate(photo.id); }}
                    className="rounded border border-clay/30 p-1.5 text-clay hover:bg-clay/5 disabled:opacity-40"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {!photosQuery.isLoading && photos.length === 0 && (
        <p className="rounded-md border border-dashed border-hairline py-8 text-center text-sm text-muted">
          No photos yet - listings with photos sell far better.
        </p>
      )}

      <input ref={inputRef} type="file" accept={ACCEPT} multiple className="hidden" onChange={(e) => onPick(e.target.files)} />
      <Button type="button" disabled={busy || photos.length >= MAX_PHOTOS} onClick={() => inputRef.current?.click()} className="w-full">
        <span className="inline-flex items-center justify-center gap-2">
          <Upload className="h-4 w-4" aria-hidden />
          {upload.isPending ? "Uploading…" : photos.length >= MAX_PHOTOS ? "Photo limit reached" : "Upload photos"}
        </span>
      </Button>
    </div>
  );
}

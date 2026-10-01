"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, Button, Input, Select, Textarea, Modal, ErrorState, EmptyState, TagChip } from "@/components/ui";
import { ListingPhotos } from "@/components/listing-photos";
import { apiFetch, ApiError } from "@/lib/api";
import { listingImageUrl } from "@/lib/shop-utils";
import type { Listing, Animal, CropPlanting } from "@/lib/types";

const PRICING_TYPES = ["fixed", "negotiable", "price_on_request"] as const;

export default function ListingsPage() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingListing, setEditingListing] = useState<Listing | null>(null);
  const [photosListing, setPhotosListing] = useState<Listing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);

  const listingsQuery = useQuery<Listing[]>({
    queryKey: ["listings"],
    queryFn: () => apiFetch<Listing[]>("/api/v1/listings"),
  });
  const lowStockQuery = useQuery<{ listing_id: string; available: string; threshold: string; unit: string }[]>({
    queryKey: ["listings", "low-stock"],
    queryFn: () => apiFetch("/api/v1/listings/low-stock"),
  });
  const lowStockByListingId = new Map((lowStockQuery.data ?? []).map((l) => [l.listing_id, l]));
  // Only for_sale animals are eligible for a new listing (backend requirement).
  const forSaleAnimalsQuery = useQuery<Animal[]>({
    queryKey: ["livestock", "for_sale"],
    queryFn: () => apiFetch<Animal[]>("/api/v1/livestock?status=for_sale&page_size=100"),
    enabled: modalOpen,
  });
  // Any planting can be a listing candidate - the backend itself checks for
  // harvested stock > 0 at creation time (a planting still "growing" simply
  // won't have any yet), so this fetches broadly rather than pre-filtering
  // by status here.
  const plantingsQuery = useQuery<CropPlanting[]>({
    queryKey: ["crops"],
    queryFn: () => apiFetch<CropPlanting[]>("/api/v1/crops?page_size=100"),
    enabled: modalOpen,
  });

  const create = useMutation({
    mutationFn: (body: {
      animal_id?: string;
      crop_planting_id?: string;
      title: string;
      description?: string;
      pricing_type: string;
      price?: string;
      unit?: string;
      low_stock_threshold?: string;
      featured: boolean;
    }) => apiFetch("/api/v1/listings", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["listings"] });
      setModalOpen(false);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to create listing"),
  });

  const deactivate = useMutation({
    mutationFn: (id: string) => apiFetch(`/api/v1/listings/${id}/deactivate`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["listings"] }),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { title?: string; description?: string; price?: string; featured?: boolean } }) =>
      apiFetch(`/api/v1/listings/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["listings"] });
      setEditingListing(null);
      setEditError(null);
    },
    onError: (err) => setEditError(err instanceof ApiError ? err.message : "Failed to update listing"),
  });

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Listings</h1>
          <p className="text-sm text-muted">
            Active public listings - what's currently visible to shoppers and guest checkout.
          </p>
        </div>
        <Button onClick={() => { setError(null); setModalOpen(true); }}>+ New listing</Button>
      </div>

      {listingsQuery.error && (
        <ErrorState message={listingsQuery.error instanceof ApiError ? listingsQuery.error.message : "Failed to load listings"} />
      )}
      {listingsQuery.isLoading && <p className="text-sm text-muted">Loading…</p>}
      {listingsQuery.data && listingsQuery.data.length === 0 && (
        <EmptyState
          title="No active listings"
          body="List an animal that's marked for_sale, or a crop planting with harvested stock, to make it visible on the public site and available for guest checkout."
        />
      )}

      {listingsQuery.data && listingsQuery.data.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {listingsQuery.data.map((listing) => (
            <Card key={listing.id} className="flex flex-col gap-2">
              {listing.cover_image_id && (
                // eslint-disable-next-line @next/next/no-img-element -- served by the API
                <img src={listing.cover_thumb_url ?? listingImageUrl(listing.cover_image_id, true)} alt="" className="mb-1 h-36 w-full rounded-md object-cover" />
              )}
              <div className="flex items-start justify-between">
                <h2 className="font-display text-lg text-forest">{listing.title}</h2>
                {listing.featured && (
                  <span className="rounded-full border border-brass/30 bg-brass/10 px-2 py-0.5 text-xs text-brass-dark">
                    Featured
                  </span>
                )}
              </div>
              {listing.description && <p className="text-sm text-muted">{listing.description}</p>}
              <p className="text-sm font-medium text-ink">
                {listing.pricing_type === "fixed" && listing.price
                  ? `KES ${Number(listing.price).toLocaleString()}${listing.unit ? ` / ${listing.unit}` : ""}`
                  : listing.pricing_type.replace(/_/g, " ")}
              </p>
              <span className="text-xs text-muted">{listing.crop_planting_id ? "Crop produce" : "Animal"}</span>
              {lowStockByListingId.has(listing.id) && (
                <span className="rounded-full border border-clay/30 bg-clay/10 px-2 py-0.5 text-xs text-clay">
                  Low stock: {lowStockByListingId.get(listing.id)!.available} {lowStockByListingId.get(listing.id)!.unit} left
                </span>
              )}
              <TagChip>{listing.slug}</TagChip>
              <div className="mt-2 flex gap-2">
                <Button
                  variant="ghost"
                  className="text-xs"
                  onClick={() => { setEditError(null); setEditingListing(listing); }}
                >
                  Edit
                </Button>
                <Button variant="ghost" className="text-xs" onClick={() => setPhotosListing(listing)}>
                  Photos ({listing.image_count ?? 0})
                </Button>
                <Button
                  variant="ghost"
                  className="text-xs"
                  disabled={deactivate.isPending}
                  onClick={() => deactivate.mutate(listing.id)}
                >
                  Deactivate
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="New listing">
        <ListingForm
          error={error}
          pending={create.isPending}
          animals={forSaleAnimalsQuery.data ?? []}
          plantings={plantingsQuery.data ?? []}
          onSubmit={(body) => create.mutate(body)}
        />
      </Modal>

      <Modal open={!!editingListing} onClose={() => setEditingListing(null)} title="Edit listing">
        {editingListing && (
          <EditListingForm
            listing={editingListing}
            error={editError}
            pending={update.isPending}
            onSubmit={(body) => update.mutate({ id: editingListing.id, body })}
          />
        )}
      </Modal>
      <Modal open={!!photosListing} onClose={() => setPhotosListing(null)} title={photosListing ? `Photos - ${photosListing.title}` : "Photos"}>
        {photosListing && <ListingPhotos listingId={photosListing.id} />}
      </Modal>
    </AdminShell>
  );
}

function ListingForm({
  onSubmit,
  error,
  pending,
  animals,
  plantings,
}: {
  onSubmit: (body: {
    animal_id?: string;
    crop_planting_id?: string;
    title: string;
    description?: string;
    pricing_type: string;
    price?: string;
    unit?: string;
    low_stock_threshold?: string;
    featured: boolean;
  }) => void;
  error: string | null;
  pending: boolean;
  animals: Animal[];
  plantings: CropPlanting[];
}) {
  const [productType, setProductType] = useState<"animal" | "crop">("animal");
  const [animalId, setAnimalId] = useState("");
  const [plantingId, setPlantingId] = useState("");
  const [unit, setUnit] = useState("");
  const [lowStockThreshold, setLowStockThreshold] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [pricingType, setPricingType] = useState<string>(PRICING_TYPES[0]);
  const [price, setPrice] = useState("");
  const [featured, setFeatured] = useState(false);

  const canSubmit = productType === "animal" ? !!animalId : !!plantingId && !!unit;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          animal_id: productType === "animal" ? animalId : undefined,
          crop_planting_id: productType === "crop" ? plantingId : undefined,
          unit: productType === "crop" ? unit : undefined,
          low_stock_threshold: productType === "crop" && lowStockThreshold ? lowStockThreshold : undefined,
          title,
          description: description || undefined,
          pricing_type: pricingType,
          price: pricingType === "fixed" ? price : undefined,
          featured,
        });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}

      <div className="flex gap-1 rounded-md border border-hairline p-1 text-sm">
        <button
          type="button"
          onClick={() => setProductType("animal")}
          className={`flex-1 rounded px-3 py-1 ${productType === "animal" ? "bg-forest text-paper" : "text-muted"}`}
        >
          Animal
        </button>
        <button
          type="button"
          onClick={() => setProductType("crop")}
          className={`flex-1 rounded px-3 py-1 ${productType === "crop" ? "bg-forest text-paper" : "text-muted"}`}
        >
          Crop produce
        </button>
      </div>

      {productType === "animal" ? (
        animals.length === 0 ? (
          <p className="rounded-md border border-hairline bg-paper px-3 py-2 text-sm text-muted">
            No animals are currently marked <code>for_sale</code>. Change an animal&apos;s status first.
          </p>
        ) : (
          <Select id="listing-animal" label="Animal" required value={animalId} onChange={(e) => setAnimalId(e.target.value)}>
            <option value="">Select an animal…</option>
            {animals.map((a) => (
              <option key={a.id} value={a.id}>
                {a.animal_number} - {a.species}
                {a.breed ? ` (${a.breed})` : ""}
              </option>
            ))}
          </Select>
        )
      ) : (
        <>
          {plantings.length === 0 ? (
            <p className="rounded-md border border-hairline bg-paper px-3 py-2 text-sm text-muted">
              No crop plantings on record yet. Register one under Crops first.
            </p>
          ) : (
            <Select id="listing-planting" label="Crop planting" required value={plantingId} onChange={(e) => setPlantingId(e.target.value)}>
              <option value="">Select a planting…</option>
              {plantings.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.planting_number} - {p.crop_type.replace(/_/g, " ")}
                  {p.variety ? ` (${p.variety})` : ""}
                </option>
              ))}
            </Select>
          )}
          <Input
            id="listing-unit"
            label="Unit"
            required
            placeholder="kg, bags, crates…"
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
          />
          <Input
            id="listing-low-stock"
            label="Low-stock alert threshold (optional)"
            type="number"
            min="0"
            step="0.01"
            placeholder="e.g. 10"
            value={lowStockThreshold}
            onChange={(e) => setLowStockThreshold(e.target.value)}
          />
          <p className="text-xs text-muted">
            The planting needs at least one recorded harvest before it can be listed - stock available to sell is
            everything harvested so far minus whatever's already in an order.
          </p>
        </>
      )}

      <Input id="listing-title" label="Title" required value={title} onChange={(e) => setTitle(e.target.value)} />
      <Textarea
        id="listing-description"
        label="Description"
        rows={3}
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />

      <Select id="listing-pricing" label="Pricing type" value={pricingType} onChange={(e) => setPricingType(e.target.value)}>
        {PRICING_TYPES.map((t) => (
          <option key={t} value={t}>
            {t.replace(/_/g, " ")}
          </option>
        ))}
      </Select>

      {pricingType === "fixed" && (
        <Input
          id="listing-price"
          label={productType === "crop" ? "Price per unit (KES)" : "Price (KES)"}
          type="number"
          min="0"
          step="0.01"
          required
          value={price}
          onChange={(e) => setPrice(e.target.value)}
        />
      )}

      <label className="flex items-center gap-2 text-sm text-ink">
        <input type="checkbox" checked={featured} onChange={(e) => setFeatured(e.target.checked)} />
        Feature this listing
      </label>

      <Button type="submit" disabled={pending || !canSubmit} className="w-full">
        {pending ? "Creating…" : "Create listing"}
      </Button>
    </form>
  );
}

function EditListingForm({
  listing,
  onSubmit,
  error,
  pending,
}: {
  listing: Listing;
  onSubmit: (body: { title?: string; description?: string; price?: string; featured?: boolean }) => void;
  error: string | null;
  pending: boolean;
}) {
  const [title, setTitle] = useState(listing.title);
  const [description, setDescription] = useState(listing.description ?? "");
  const [price, setPrice] = useState(listing.price ?? "");
  const [featured, setFeatured] = useState(listing.featured);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ title, description: description || undefined, price: price || undefined, featured });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Input id="edit-listing-title" label="Title" required value={title} onChange={(e) => setTitle(e.target.value)} />
      <Textarea id="edit-listing-desc" label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
      {listing.pricing_type === "fixed" && (
        <Input
          id="edit-listing-price" label="Price" type="number" min="0" step="0.01"
          value={price} onChange={(e) => setPrice(e.target.value)}
        />
      )}
      <label className="flex items-center gap-2 text-sm text-ink">
        <input type="checkbox" checked={featured} onChange={(e) => setFeatured(e.target.checked)} />
        Featured
      </label>
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Saving…" : "Save changes"}
      </Button>
    </form>
  );
}

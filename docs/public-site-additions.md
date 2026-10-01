# Public-site additions: photos, inquiries, and hardening

Migrations **0023** (`listing_images`), **0024** (`contact_inquiries`) and **0025**
(optional bucket storage keys for photos). All additive, all with downgrades.

## Listing photos
- Up to **8 photos per listing**, JPEG/PNG/WebP, **5 MB** each (`commerce/images.py`).
- **Storage is pluggable** (`STORAGE_BACKEND`, see below): Postgres (default, zero setup) or a
  **Supabase Storage bucket** (photos served straight from Supabase's CDN, never through the
  API or the database). Rows of both kinds coexist, so switching backends never orphans photos.
- Uploads are validated by content (not filename/Content-Type), size- and pixel-capped, then
  **re-encoded to JPEG**, which strips EXIF/GPS. A thumbnail (480 px) is stored alongside the
  full image (max 1600 px).
- `position` 0 is the **cover**: the only photo shown on the home page and store grid. The
  product page shows all photos.
- Admin API (`listings.manage` to write, `livestock.read` to read):
  `GET|POST /api/v1/listings/{id}/images`, `PUT .../images/order`, `DELETE .../images/{image_id}`.
  Upload is multipart, field name `files` (repeatable).
- Public bytes: `GET /api/v1/media/listing-images/{image_id}` and `.../thumb`
  (unauthenticated, keyed by unguessable UUID). Database photos are returned inline
  (`Cache-Control: immutable`); bucket photos get a 302 to their CDN URL.
- `PublicListingOut.images` = `[{id, url, thumb_url}]`, cover first; `url`/`thumb_url` are direct
  CDN links for bucket photos and `null` for database photos (clients fall back to the media
  endpoint). `ListingOut` gains `cover_image_id`, `cover_thumb_url`, `image_count`.

### Using a Supabase Storage bucket
1. Supabase dashboard -> **Storage** -> create a bucket (default name `listing-images`) and mark it **Public**.
2. Set on the API: `STORAGE_BACKEND=supabase`, `SUPABASE_URL=https://<project-ref>.supabase.co`,
   `SUPABASE_SECRET_KEY=<sb_secret_... key>` (Dashboard -> Settings -> API Keys -> "Publishable and
   secret API keys" tab), `SUPABASE_STORAGE_BUCKET`. (`SUPABASE_SERVICE_ROLE_KEY` is the legacy name and
   still works if `SUPABASE_SECRET_KEY` is empty.) The key is **server-side only** - never put it in a
   `NEXT_PUBLIC_*` variable. New-style `sb_secret_` keys are sent on the `apikey` header only (they are
   not JWTs); legacy `service_role` keys are sent on both headers.
3. Objects are keyed `{org_id}/{listing_id}/{image_id}.jpg` (+ `_thumb.jpg`), uploaded with
   `x-upsert: false` and a long cache lifetime. Uploads go to the bucket *before* the database row is
   written; if anything fails afterwards the objects are deleted again. Deleting a photo removes its
   objects after the database change (best-effort - a leftover object is harmless and logged).
4. A half-configured backend logs a startup warning and uploads fail with a clear 503 (it never
   silently falls back to the database).
5. Verify once against your real project (upload, view, delete) - the client is unit-tested against a
   mock of the documented Storage REST API but has not been run against a live Supabase project.

Existing database photos keep working after you switch; new uploads go to the bucket.

## Contact inbox
- Public: `POST /api/v1/public/{org_slug}/contact` (name, message, and email **or** phone;
  optional `listing_slug`; hidden `website` honeypot). Rate limited.
- Staff (`orders.manage`): `GET /api/v1/inquiries[?status=]`, `GET /inquiries/summary`,
  `PATCH /inquiries/{id}` (`new|read|replied|archived`). Admin page: **Inquiries**.
- Staff with `orders.manage` get an in-app notification (category `orders`, because
  `notifications.category` has a DB CHECK constraint).

## Security hardening
| Risk | Fix | Setting |
|---|---|---|
| Anyone could forge a "paid" order via the public mock webhook (published default secret; mock live in every env) | Mock provider is **404 everywhere it isn't explicitly safe**: on in `development`/`test`, off in any other `ENV` unless `ALLOW_MOCK_PAYMENTS=true` **and** `MOCK_PAYMENT_SECRET` is a strong non-placeholder value | `ALLOW_MOCK_PAYMENTS`, `MOCK_PAYMENT_SECRET` |
| Guest checkout / contact / guest payment had no rate limit | Per-IP limits (12 orders, 6 contact msgs, 20 payment initiations per 10 min) | `RATE_LIMIT_BACKEND` |
| Behind a load balancer every visitor shared one IP (also affected the auth limiter) | Client IP taken from `X-Forwarded-For` **only** for the configured number of trusted proxies | `TRUSTED_PROXY_COUNT` (Terraform sets `1`) |
| Unpaid guest orders reserved animals/stock forever (and deactivated the listing) | Background job cancels stale **guest** orders, frees stock and re-lists the animal | `GUEST_ORDER_TTL_MINUTES` (120), `PAYMENT_PENDING_TTL_HOURS` (24); `0` disables |

Startup logs a warning if a production-like `ENV` still uses a placeholder `JWT_SECRET`.

**Behaviour change to be aware of:** any deployment whose `ENV` is not
`development|dev|local|test|testing` no longer accepts the mock payment provider unless you
opt in as described above.

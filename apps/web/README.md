# Farm Platform - Web (Next.js frontend)

A real, working vertical slice of the admin dashboard described in spec
§41-42 - **not** the complete frontend. See the root `README.md`'s
"Frontend" section for exactly what is and isn't covered.

## What's here
- `/login` - real login form against `POST /api/v1/auth/login`, stores the
  JWT access + refresh token pair, redirects to the dashboard on success.
- `/admin/dashboard` - calls `GET /api/v1/reports/dashboard` and renders the
  top-card set from spec §68 (herd, milk, inventory, monthly finance,
  low-stock/vaccination-due alerts).
- `/admin/farms` - real CRUD: list farms with nested branches/locations,
  create-farm/create-branch/create-location forms (modals), matching the
  Farm → Branch → Location hierarchy from Phase 1.
- `/admin/livestock` - calls `GET /api/v1/livestock`, a real sortable table
  using the ear-tag chip signature element for each `animal_number`, plus a
  "Register animal" link.
- `/admin/livestock/new` - full animal registration form (farm/location
  pickers, species/breed/sex, acquisition details) posting to
  `POST /api/v1/livestock`, redirects to the new animal's detail page.
- `/admin/livestock/[id]` - tabbed (Overview / Timeline / Health / Weights /
  Breeding / Dairy / Movements) per spec §67's profile page structure - a
  slice of that spec section, not the full tab set (Production/Feed/Costs/
  Profitability/Documents/Photos tabs aren't built). The Health tab includes
  a real "add health record" form; the Weights tab shows weight history
  with the ADG the backend computes, plus a "record weight" form. Breeding
  and Dairy tabs are only shown when relevant (Breeding: female animals;
  Dairy: female cattle specifically, matching the backend's own validation)
  and drive the full lifecycle through real forms - breeding → pregnancy
  check → delivery (auto-creates the offspring animal with lineage set),
  and lactation cycle start → milk recording → dry-off. The Movements tab
  shows location history and a form to move the animal to any location
  under any farm (pulled from the same `GET /farms` nested branches/
  locations data the Farms page uses), with the timeline correctly showing
  `from_location_id` populated from wherever the animal was before.
  Verified live end to end: walked one animal through `bred →
  confirmed_pregnant → delivered`, confirmed the offspring appeared with
  `dam_id` set and `category: calf`, walked a full lactation cycle, and
  moved an animal between two paddocks, confirming both the movement
  history and the animal's own current `location_id` updated correctly.
  The header shows status-transition buttons,
  generated from the same allowed-transition table the backend enforces
  (`livestock/service.py`'s `_ALLOWED_TRANSITIONS`) so the UI only ever
  offers valid next states - verified live that the backend still
  independently rejects an invalid transition (409) if attempted directly,
  i.e. the UI's guard is a convenience, not the actual enforcement.
- `/admin/customers` - real CRUD: list customers with a create-customer
  form/modal, matching the `customer_type` enum from spec §16.
- `/admin/listings` - create a listing for any `for_sale` animal, view active
  listings as cards, deactivate one. **Shows active listings only** -
  `GET /api/v1/listings` has no include-inactive filter on the backend, so
  there's currently no way to see a listing's history after deactivation
  from this page (the data exists - `Listing.is_active` - the endpoint just
  doesn't expose it yet).
- `/admin/inventory` - item cards with live-computed `current_stock` and a
  low-stock highlight (matches the backend's own `reorder_level` check, not
  a separate frontend threshold), create-item form; `/admin/inventory/[id]`
  shows the full movement ledger and a record-movement form that correctly
  distinguishes unsigned quantities (purchase/consumption/etc - the backend
  applies the sign) from `adjustment`'s signed delta. Verified live that the
  negative-stock guard (409) fires through the exact request the form sends,
  not just via direct API calls.
- `/admin/orders` - order list (customer, items, total, delivery, status)
  with `/admin/orders/[id]` detail: items, full status-change history, and
  status-transition buttons generated from a hand-mirrored copy of the
  backend's `_ORDER_TRANSITIONS` table (same pattern and same caveat as the
  livestock status buttons above).
- `/admin/finance` - three tabs: Summary (date-range income/expense/net with
  category breakdowns, matching `GET /finance/summary` exactly) and a
  transaction-entry form; Transactions (the full ledger); Profitability
  (most/least profitable animals, full per-animal cost breakdown). Verified
  live end to end: sold an animal for a real profit, confirmed the
  Profitability tab's numbers match the actual sale (not an estimate - the
  `is_actual` flag the backend computes is respected, not re-derived
  client-side).
- `/shop/[orgSlug]` - a real, separate, unauthenticated public storefront
  (spec §69/§7 CMS + Phase 11 guest checkout, previously backend-only):
  browse active listings with customer testimonials (star ratings) shown
  inline (`ShopHeader` pulls the farm name/tagline from
  `GET /public/{slug}/profile`), a listing detail page with a real checkout
  form requiring no account (`/shop/[orgSlug]/listings/[slug]`), an
  order-status lookup gated by the same checkout-email ownership check the
  backend enforces (`/shop/[orgSlug]/orders/[orderId]?email=...`), a blog
  (`/shop/[orgSlug]/blog` list + `/blog/[slug]` detail), and category-grouped
  FAQs (`/shop/[orgSlug]/faqs`) - all pulling from the CMS backend that's
  existed since Phase 7 with zero prior frontend consumption. Uses a
  distinct layout (no `AdminShell`, no sidebar) since this is a genuinely
  different audience from the staff pages above. Verified live end to end:
  browsed a real listing, checked out as a guest with a delivery address,
  got a real order confirmation, looked up that order's status, confirmed
  the backend's "missing email" guard (422) fires when the frontend's own
  required query param is stripped out, and confirmed a published blog
  post/testimonial/FAQ appears publicly while an unpublished draft does not.
- Token refresh on 401 is handled transparently in `lib/api.ts`, using the
  real refresh-token rotation endpoint the backend already implements.

## Verified, and how
- `npm run build` compiles cleanly - TypeScript strict mode, no errors, all
  21 routes statically analyzed and prerendered where possible.
- Every read AND write API call this code makes was checked against the
  *actual* running backend in this session: registered a real org, created
  real farms/branches/locations/animals/health records/weight
  records/customers/orders/listings/inventory items/stock movements/finance
  transactions/breeding records/pregnancy checks/lactation cycles/milk
  records through the exact request bodies each form sends, drove an animal
  through a real status sequence (active → for_sale → sold) and an order
  through a real status sequence (pending → payment_pending → paid) via the
  same buttons the UI renders, confirmed the backend still independently
  rejects an invalid transition attempted directly in both cases, confirmed
  a listing created here produces the same slug format the guest-checkout
  flow (Phase 11) depends on, confirmed the inventory negative-stock guard
  (409) fires through the exact over-consumption request the movement form
  would send, confirmed the Profitability tab's real-sale math (90,000 −
  40,000 acquisition = 50,000 profit, `is_actual: true`) matches the backend
  exactly, walked a full breeding lifecycle (`bred → confirmed_pregnant →
  delivered`) through to a real auto-created offspring animal with lineage
  set, walked a full dairy cycle (start lactation → record milk → dry off),
  and walked the full public storefront flow (browse → detail → guest
  checkout with a delivery address → order confirmation → status lookup) end
  to end with no authentication at any step, including the storefront's
  content pages - testimonials (rendered inline on the browse page with star
  ratings), blog list/detail, and category-grouped FAQs - confirming a
  published item appears publicly and an unpublished draft does not, and
  moved an animal between two paddocks, confirming both the movement
  history and the animal's own current `location_id` updated correctly. The
  frontend's allowed-transition guards are a UX convenience, not the
  enforcement point. Every response JSON shape was confirmed to match the
  TypeScript types in `lib/types.ts` field-for-field.

**Not verified:** actual browser rendering. This sandbox has no headless
browser tool, so nothing here has been visually confirmed to look right, and
no click-through/interaction flow (does the login form actually redirect
correctly after a real POST, does the timeline tab actually lazy-load, does
the checkout form's delivery-address field actually toggle visibility) has
been exercised by anything other than reading the code. The build compiling
and the API contracts matching is real signal, but it is not the same claim
as "this was opened in a browser and it worked."

## What's NOT here
Health follow-up management beyond adding a record (no editing/deleting),
inline profile editing on the customer account page, and a listing-history
view (deactivated listings, not just active ones - the backend endpoint
has no include-inactive filter yet). Payment/invoice viewing in the
customer portal, editing an existing listing, banners, a customer account
system, tenant registration, team/role management, and public-site content
management all *used to* be listed here as gaps - they're now built (see
the Phase 26/28/29 sections below) - this section only lists what's still
genuinely missing.

## Phase 26 additions (this session) - Procurement/Employees/Assets/Search/
## Settings/Valuation/Bulk-import/Edit-listing/QR/Invoice-PDF/Customer-accounts/Banners
- `/admin/procurement` + `/admin/procurement/purchase-orders/[id]` -
  suppliers list, PO creation with line items, PO detail with status-
  transition buttons (mirrors `/admin/orders/[id]`'s pattern exactly).
- `/admin/employees` + `/admin/employees/[id]` - HR profile list/create,
  detail page with employment-status transitions and work-shift scheduling.
- `/admin/assets` + `/admin/assets/[id]` - equipment list/create, detail
  page with a maintenance log (auto-clears "under maintenance" status on a
  completed repair, matching the backend's own behavior).
- `/admin/search` - one page for the backend's cross-entity search; only
  links to entity types that actually have a detail route in this app
  (animals/orders/inventory items/employees/assets) - suppliers/customers/
  invoices show as results but aren't clickable yet, since those don't have
  standalone detail pages here.
- `/admin/settings` - currency/timezone/invoice-PO-employee-asset numbering
  prefixes/tax rate/default units, backed by `GET/PATCH /api/v1/organization
  /settings`.
- `/admin/inventory/valuation` - FIFO-costed per-item value report, linked
  from the main Inventory page.
- Bulk CSV import - a shared `BulkImportModal` component (preview, then
  confirm) reused on Customers/Inventory/Suppliers; Livestock gets its own
  variant with a farm picker, since that endpoint requires a `farm_id`.
- Edit-listing - an edit modal on the existing Listings page
  (title/description/price/featured; never the slug or pricing type).
- QR codes - an inline SVG preview plus download button on the animal
  detail page's Overview tab.
- Invoice PDF - a download button on the order detail page, next to the
  existing invoice summary.
- Customer accounts - `/shop/[orgSlug]/account/register`, `/login`, and
  the account page itself (profile + order history), reusing the exact
  same `apiFetch`/token-storage machinery every staff page already uses -
  no separate customer auth system, matching how the backend itself was
  built.
- Banners - the shop homepage now fetches and renders
  `GET /api/v1/public/{org_slug}/banners` in a horizontally-scrollable
  strip above the listings grid.

**Verification status for everything in this section is materially weaker
than the rest of this file.** No `node_modules` and no network access to
install them existed in the sandbox that wrote it - none of Phase 26 has
been type-checked, linted, or built even once, let alone opened in a
browser. Every file's brace/paren/bracket balance was checked and every
field name used was cross-referenced against the real `src/lib/types.ts`
interfaces by hand, but that is not the same guarantee a real `tsc --noEmit`
run provides. Run `npm install && npx tsc --noEmit && npm run build`
before trusting any of it.

## Running it
```bash
cd apps/web
npm install
cp .env.local.example .env.local   # point NEXT_PUBLIC_API_URL at your backend
npm run dev
```
Requires the backend (`apps/api`) running and migrated - see the root
README's "Run it" section.

## Phase 29 additions (this session) - the actual gaps found by using the app
Prompted by a direct question - "where does a tenant even register? I land
on a login page" - which surfaced that Phase 26 had built UI for every
*internal* feature but missed the front door itself, plus a systematic
audit of every backend router against every existing page turned up several
more real gaps: features with working backend logic and zero UI anywhere.

- **`/register`** - the actual "sign up your farm" page. `POST /api/v1/auth
  /register` has existed since Phase 1; nothing in `apps/web` ever called
  it before this, so every account used for local testing so far was
  created via `curl`. New `useRegisterOrganization` hook mirrors `useLogin`
  exactly.
- **`/admin/users`** - invite staff, assign/revoke roles. This blocked team
  growth entirely: there was no way to add a second staff account through
  the UI. Needed a small backend addition alongside it -
  `GET /api/v1/users/roles` - since nothing exposed the list of an org's
  roles even though they've existed since Phase 1 (`register_organization`
  seeds one row per `DEFAULT_ROLE_GRANTS` entry).
- **`/admin/cms`** - farm profile, testimonials, blog posts, FAQs, and
  banners, in one tabbed page. The public storefront has displayed all of
  this since Phase 7/Phase 26, but there was no way for a farm owner to
  actually *write* any of it - the backend's `cms.manage`-gated endpoints
  existed with no UI at all.
- **`/admin/reservations`** - list + cancel. Needed a small backend
  addition first: `GET /api/v1/reservations` didn't exist (create/get-one/
  cancel/expire-stale all did) - added `service.list_reservations` +
  the router endpoint before building the page, since a list page needs
  something to list.
- **`/admin/notifications`** - in-app notification inbox (mark read/
  read-all) plus per-category preference toggles (health/inventory/
  payments/orders/breeding).
- **`/admin/reports/profitability`** - spec §25's per-animal investment-
  vs-profit report, linked from the dashboard. The backend
  (`GET /api/v1/reports/profitability`) existed with no UI.
- Customer edit - `/admin/customers` rows are now clickable, reusing the
  same form component in edit mode (`PATCH /api/v1/customers/{id}`, which
  existed with no UI).
- Payment recording - `/admin/orders/[id]` gained a "Record payment"
  section (provider selector + phone/token field) for orders in
  `payment_pending`, calling whichever of `/api/v1/payments/{mock,mpesa,
  stripe}` is selected. The order only ever moves to `paid` once the
  provider confirms via webhook - this button never marks anything paid
  itself, matching spec §20's "never trust client-reported payment status."

Same verification caveat as Phases 26/28 - no `node_modules`, nothing
type-checked or built; brace/bracket balance and every `types.ts` field
reference checked by hand across all 49 frontend files as of this phase.

# Architecture - Phase 1 Foundation

## Approach
Modular monorepo (per spec §63/§64): one FastAPI app, internally organized into
domain modules with strict boundaries (own models/schemas/service/router per module,
no cross-module ORM joins - only service-layer calls). Each module can be extracted
into its own deployable service later without rewriting business logic.

## Phase 1 scope (this delivery)
- Multi-tenant core: `Organization` is the root tenant entity (spec §4).
- Identity & Access module: users, permission-based RBAC, JWT access + refresh tokens,
  password hashing (bcrypt via passlib), audit-ready timestamps.
- Farm module: Farm, Branch, Location (paddock/barn/pen/grazing_area) - foundation for
  the Livestock module (Phase 2) to reference.
- Tenant isolation enforced at the query layer via a required `organization_id`
  scope dependency - every Phase 1+ router must use it.
- Postgres via SQLAlchemy 2.x + Alembic migrations.
- Docker Compose for local dev (Postgres, Redis, API).

## Phase 2 scope (this delivery)
- Livestock module (spec §6): `Animal` core model scoped to `organization_id` +
  `farm_id` (+ optional `location_id`), species/breed/category as free-text fields
  (validated to `cattle|sheep` at the schema layer) so species-specific extension
  tables can be layered on later without migrating the core table.
- Immutable lifecycle timeline (spec §7): `AnimalEvent` - append-only (DB trigger,
  same pattern as `audit_logs`), auto-recorded on acquisition, weighing, movement,
  and status changes.
- Weight tracking (spec §8): `WeightRecord` + Average Daily Gain computed at read
  time from chronologically-ordered records (not stored, to avoid staleness if a
  backdated reading is added later).
- Movement tracking (spec §10): `Movement` - append-only, animal's current
  `location_id` updates alongside without erasing history (spec §52.8).
- Status state machine (spec §52.1/§52.2): explicit allowed-transition table;
  `sold`/`transferred`/`deceased`/`archived` are terminal. Selling specifically
  requires `livestock.sell` in addition to `livestock.update` (spec §5).
- Partial profitability endpoint (spec §8/§25): acquisition cost only for now -
  feed/health/transport costs are explicit zero placeholders until Health (Ph2b)
  and Feed/Inventory (Ph3) exist, wired via `AnimalAcquired`/etc. events.
- `app/core/events.py`: minimal in-process pub/sub so Livestock doesn't import
  Notifications/Finance directly; extraction path to RabbitMQ/Kafka is a drop-in
  swap of `publish()`'s body only.

## Phase 2b scope (this delivery)
- Health module (spec §5 Animal Health Service): `HealthRecord` covering
  vaccination/treatment/deworming/examination/injury/lab_result/vet_visit/
  prescription, nested under `/livestock/{animal_id}/health`.
- Follow-up/due tracking (spec Product Vision - "which vaccinations are due"):
  `GET /api/v1/health/due?within_days=N` returns overdue + upcoming items across
  the org; `follow_up_completed` is the one mutable field on an otherwise
  historical-fact table (explicitly not covered by the append-only trigger -
  documented trade-off in migration `0004`).
- Cross-module timeline consistency: `livestock.service.record_external_event` is
  a narrow, documented shared-kernel exception so a health record and its
  timeline entry commit in the same transaction, while side effects that don't
  need that guarantee (health_status side effects excluded - that IS same-tx)
  still go through `core/events.py` (`HealthRecordCreated`, `VaccinationDue`).
- `animal.health_status` auto-flips to `under_treatment` on injury/treatment
  records - a first cut; a real recovery/discharge workflow is a later
  refinement, not in scope here.

## Phase 3 scope (this delivery)
- Breeding & Genetics (spec §7): `BreedingRecord` (mating/AI → pregnancy checks →
  delivery) + `PregnancyCheck` (append-only). Confirmed pregnancy flips the dam's
  `reproductive_status`; delivery can auto-create offspring `Animal` rows with
  `dam_id`/`sire_id` set (family-tree lineage columns added to `animals` in this
  migration), reusing `livestock.service.create_animal` rather than duplicating
  animal-creation logic.
- Dairy Production (spec §8): `LactationCycle` (one active cycle per animal,
  enforced) + `MilkProductionRecord` (one entry per animal/date/session, DB
  unique constraint), plus a herd-wide daily summary (total, average/cow, top
  producers) backing the dashboard cards in §12/§68.
- Feed & Inventory (spec §9-14): `InventoryItem` + `StockMovement` as a strict
  append-only ledger - current stock is always `SUM(quantity)`, never a mutable
  counter. Enforces §52.11 ("negative inventory prevented unless explicitly
  configured") via `allow_negative_stock` per item. Movements can be tagged with
  `animal_id` for per-animal feed cost (§13), feeding into the livestock
  profitability endpoint once wired together.
- All three modules use `record_external_event` (the Phase 2b shared-kernel
  seam) to keep the animal timeline consistent with breeding/health events in
  the same transaction, and `core/events.py` for cross-module notifications
  (`PregnancyConfirmed`, `BirthRecorded`, `MilkProductionRecorded`,
  `InventoryLow`, `InventoryExpiring`).

## Phase 4 scope (this delivery)
- Customer CRM (spec §16): `Customer`, org-scoped, with a `find_or_create_by_contact`
  seam intended for later guest-checkout flows (spec §69) without requiring a
  customer login system - see the scoping note below for why that login system
  itself is deferred.
- Listings (spec §17): `Listing` wraps an animal that's already `for_sale`; a
  partial unique DB index enforces one *active* listing per animal, backed by
  an application-level pre-check for a clean error message (both matter - see
  "bugs found" below for why relying on only one of them is a mistake).
- Reservations (spec §18) and Orders (spec §19-20): the first genuinely
  concurrency-sensitive part of the system. `SELECT ... FOR UPDATE` locks the
  animal row before checking availability, closing the race window between
  "read status" and "write new status" that a plain application-level check
  would leave open. A partial unique index (one active reservation per animal)
  backs this at the DB level too. Order status follows an explicit allowed-
  transition table (same pattern as the Phase 2 animal status machine);
  reaching `paid` transitions the animal to `sold`, reaching `cancelled` (from
  a pre-payment state) releases it back to `for_sale`.
- **Scoping note - customer-facing auth deferred.** Spec §16/§69-70 describe a
  full customer portal (`/dashboard`, self-service login, guest checkout). This
  phase builds the *staff-operated* side only: a Sales Manager or Farm Manager
  creates customers, listings, reservations, and orders through the same
  permission-gated API as everything else. A separate customer identity system
  (distinct from `identity.User`, likely session- or magic-link-based given
  guest checkout shouldn't require a password) is real, non-trivial scope
  that overlaps with the Phase 7 public website - it's called out here as
  explicitly deferred rather than half-built.
  **Correction (Phase 15):** the eventual customer identity system did *not*
  end up distinct from `identity.User` as speculated above - it turned out
  `DEFAULT_ROLE_GRANTS` already had an empty-permission `"Customer"` role
  waiting for exactly this, so Phase 15 reused `identity.User` directly
  (see that phase's entry for why the speculation here didn't hold up).

## Phase 5 scope (this delivery)
- Payment provider abstraction (spec §20): `PaymentProvider` base class with
  `initiate_payment()`/`verify_and_parse_webhook()`, implemented by `MpesaProvider`
  (Daraja STK Push), `StripeProvider` (Payment Intents), and `MockProvider` - the
  mock is fully functional (not a stub) so the entire payment→webhook→paid flow
  is live-testable without real credentials (spec §51).
- Payment status is **never** set from a client call - `POST /payments/{provider}`
  only *initiates*; the order only reaches `paid` via a verified webhook callback
  (spec §20/§65.10 - "never trust payment status from the frontend"). Webhook
  signature verification lives in each provider (HMAC for mock, equivalent
  patterns documented for mpesa/stripe); a bad signature is rejected before
  anything touches the order or payment record.
- Webhook idempotency (spec §20 - "never process the same callback twice") is
  enforced by a DB unique constraint on `(provider, event_id)`, not just an
  application-level check - verified by a test that replays the identical
  signed payload and confirms the finance income transaction isn't duplicated.
- Finance ledger (spec §23): `FinanceTransaction` (income/expense with category
  breakdown) and `Invoice` (sequential per-org numbering via a row-locked
  counter, spec §59). Both are populated automatically via `core/events.py`
  subscriptions in `finance/handlers.py` - `AnimalAcquired` → expense
  transaction (spec §52.6), `PaymentSucceeded` → income transaction + invoice
  (spec §52.4) - rather than the Commerce/Livestock modules calling into
  Finance directly. This is the first real payoff of having built the event
  bus back in Phase 2: three modules stay decoupled while still producing a
  consistent ledger.
- **Not live-tested - `MpesaDarajaProvider`/`StripeProvider`.** This sandbox's
  network egress is restricted to package registries; `safaricom.co.ke` and
  `api.stripe.com` are unreachable here. Both classes follow their provider's
  published API contract (documented in each module's docstring) but that is
  explicitly not the same claim as "verified against the live API" - see
  "Known gaps" below.

## Phase 6 scope (this delivery)
- Reporting (spec §14/§24-25/§44): a new `reporting` module that sits above
  every domain module and only consumes their services - it is never imported
  by anything else, avoiding the import-cycle risk that would come from
  enriching `livestock`'s own profitability endpoint directly (Health and
  Breeding already import `livestock.service`; having `livestock` import back
  into Health/Inventory/Finance would create exactly the cycle the module
  boundaries have avoided since Phase 2).
  - `GET /reports/dashboard` - herd stats, today's milk, inventory value
    (rough valuation: current stock × most recent purchase unit cost per
    item - explicitly not FIFO/weighted-average accounting), monthly finance
    summary, low-stock and vaccination-due counts.
  - `GET /reports/profitability` - now uses *real* feed cost
    (`inventory.service.feed_cost_for_animal`) and health cost
    (`health.service.get_total_health_cost_for_animal`) instead of the
    Phase 2 acquisition-only placeholder, distinguishing actual profit (real
    sale price from a paid order) from expected profit (estimate), with an
    explicit `is_actual` flag rather than conflating the two.
  - `GET /reports/export/livestock.csv` - CSV export is implemented; PDF/Excel
    export is deferred (see below) rather than half-built.
- Notifications (spec §13/§32/§55): `Notification` + `NotificationPreference`,
  in-app only. Recipients are derived from RBAC (`get_users_with_permission`,
  added to `identity/service.py`) rather than a separate subscription list -
  "who gets a vaccination-due alert" is just "who has `health.read`".
  Handlers subscribe to 9 event types already being published since Phase 2-5
  and turn them into actual delivered notifications instead of just log
  lines. `POST /notifications/run-scheduled-checks` stands in for the daily
  cron/Celery-beat job spec §32 describes - there's no task scheduler in this
  build (that's Phase 9 DevOps), so the logic is real and callable, just not
  wired to an actual timer yet.
- **Bug found via live testing, not just written and assumed correct:** the
  profitability report pulled feed/health costs directly from their source
  tables, but the Finance *ledger* only ever recorded acquisition cost -
  `HealthRecordCreated` didn't carry cost, and inventory consumption never
  published anything Finance could subscribe to. A farm owner would have seen
  the profitability report and the finance dashboard disagree on the same
  animal's costs. Fixed by enriching `HealthRecordCreated`'s payload with
  `cost` and adding a new `InventorySpend` event (fired only for outbound
  movements - consumption/wastage/expired - with a known `unit_cost`), plus
  two new Finance handlers. Verified live: ledger and profitability report
  now both show 42,500.00 for the same test animal. Regression-tested in
  `test_reporting.py::test_health_and_feed_costs_flow_into_finance_ledger`.
- **A second bug in that same fix:** the two new Finance handlers used a bare
  `AsyncSessionLocal()` instead of the `db_module.AsyncSessionLocal()`
  module-attribute lookup the rest of `finance/handlers.py` actually uses
  (required for the test suite's per-test event-loop safety - see
  `tests/conftest.py`). This produced a `NameError` that the event bus's
  fire-and-forget error handling silently swallowed (by design - a
  notification/ledger bug must never fail the transaction that triggered
  it), so it only surfaced by reading the server log during live testing, not
  from an HTTP error response. Fixed by matching the existing pattern.

## Phase 7 scope (this delivery)
- CMS (spec §15): `FarmProfile` (public-facing profile, deliberately separate
  from `Organization`'s internal tenant settings - see the model docstring for
  why), `Testimonial`, `BlogPost`, `FAQ`, `Banner`. All staff-managed via
  `cms.manage`, all support a published/unpublished draft state.
- Public site data API (spec §33/§69): a new top-of-graph `public` module,
  same architectural role as `reporting` - it composes reads from `cms`,
  `commerce`, `livestock`, and `farm` without any of them depending back on
  it. Every route is genuinely unauthenticated (spec §69: "do not force
  registration before browsing"), resolving the organization by its existing
  `slug` (from Phase 1) in the URL path - `/api/v1/public/{org_slug}/...`.
- **Security-conscious response schemas.** `public/schemas.py` is a strict
  allowlist - `PublicListingOut` has no `acquisition_cost`, `current_value`,
  `supplier`, `previous_owner`, or internal notes fields, full stop. This is
  the same principle spec §38 states for QR codes ("never expose sensitive
  internal information publicly"); Phase 7 is where it first has to be
  enforced in code rather than just stated, since it's the first genuinely
  public-facing surface in the whole build.
- SEO (spec §45): per-org `sitemap.xml` and `robots.txt`, generated from
  active listings + published blog posts. A real deployment would generate
  these from the Next.js frontend's own routes; this backend version is both
  the data source that generator would call and directly useful on its own
  for any deployment that doesn't have that frontend yet.
- Listings gained a `slug` field for SEO-friendly URLs (spec §45's example:
  `/livestock/dairy-cattle/holstein-cow-001`).
- **A real, pre-existing bug found and fixed via this phase's own live
  testing:** nothing since Phase 4 ever set `Listing.is_active = False` when
  an animal left `for_sale` via reservation or order - the public catalog
  (which didn't exist until this phase) would have shown stale "for sale"
  listings for animals that were actually already reserved or sold. Fixed by
  adding `_deactivate_active_listing_for_animal()`, called from both
  `create_reservation` and `create_order`; covered by two new regression
  tests (`test_listing_deactivates_when_animal_reserved`/`_ordered_directly`).
- **Customer-facing gap partially resolved.** Phases 4/5 deferred all
  customer-facing access ("no login system for buyers"). Phase 7 resolves the
  *browsing* half of that - a customer can view the farm's profile, listings,
  blog, testimonials, and FAQs with zero authentication, matching how a real
  storefront works before checkout. The *checkout* half (an actual customer
  placing an order themselves, vs. staff creating one on their behalf) still
  needs a real customer identity system and remains deferred - seen below.

## Deferred to later phases (per spec §64 roadmap)
Customer-facing checkout/guest-order-placement (browsing is now public as of
Phase 7, but a customer still cannot place their own order - that needs a
session/magic-link identity system distinct from staff `identity.User`, which
is real, non-trivial scope on its own); live verification of the M-Pesa/Stripe
providers against real endpoints (Phase 5 scoping note); PDF/Excel report
export (Phase 6 scoping note - CSV is implemented, the rest needs a
template/spreadsheet dependency not yet justified by a second export
consumer); a real task scheduler to actually trigger `run-scheduled-checks`
daily rather than on manual/admin call (see Phase 8/9 section below); a full
observability stack - Prometheus/Grafana/OpenTelemetry per spec §47 (Phase
8/9 built structured logging + request IDs, which is the foundation, but not
the metrics/tracing stack on top); the actual Next.js frontend that would
consume everything built across all nine phases (nothing in `/apps/web`
exists - this entire build has been backend API only).

## Tenant isolation
Every business row belongs to `organization_id`. `get_current_user` resolves the JWT
to a user + org membership; `require_permission(...)` checks a permission code against
the user's role(s) **within that organization**. No query is allowed to omit the
`organization_id` filter - enforced by a `TenantScopedQuery` helper used by all
Phase 1+ services.

## RBAC model (permission-based, not hard-coded roles - spec §5)
```
Organization 1--* Role 1--* RolePermission *--1 Permission
Organization 1--* User  1--* UserRole *--1 Role
```
Roles are per-organization (so orgs can define custom roles). Seed data creates the
standard roles (Farm Owner, Farm Manager, Livestock Manager, Veterinarian, Farm Worker,
Inventory Manager, Accountant, Sales Manager, Customer, System Administrator) with
sensible default permission grants, but permissions - not role names - are what
endpoints check.

## Auth flow
- `POST /api/v1/auth/register` → creates Organization + first user (Farm Owner role).
- `POST /api/v1/auth/login` → email+password → access token (15 min) + refresh token
  (30 days, stored hashed in DB, rotated on use).
- `POST /api/v1/auth/refresh` → rotates refresh token, issues new access token.
- `POST /api/v1/auth/logout` → revokes refresh token.
- `GET /api/v1/auth/me` → current user + org + permissions.

## Phase 8/9 scope (this delivery) - security, observability, deployment
Unlike Phases 1-7, this wasn't "build a new bounded context" - it's a
hardening pass across everything already built.
- **Request context + structured logging** (`core/middleware.py`,
  spec §47): every request gets a correlation ID (accepts an inbound
  `X-Request-ID` for gateway/frontend propagation, generates one otherwise),
  echoed back in the response header and attached to the request-completion
  log line along with method/path/status/duration. This is the *foundation*
  for observability, not the full stack - an actual Prometheus/Grafana/
  OpenTelemetry deployment (spec §47's explicit ask) is real additional scope
  not built here; see "Deferred" above.
- **Security headers** (spec §29): `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy` on every response. Deliberately
  does *not* set HSTS - this app doesn't terminate TLS itself, and setting a
  header implying it does would be actively misleading; that belongs on
  whatever reverse proxy/load balancer sits in front of it in production.
- **Rate limiting** (spec §29): an in-memory sliding-window limiter, applied
  to `/auth/register` and `/auth/login` specifically (10 requests/60s per
  client IP) as the brute-force-relevant endpoints. Explicitly documented as
  a single-process solution - correct for this build's docker-compose
  topology, but a multi-replica production deployment needs a shared store
  (Redis, already present in docker-compose for exactly this kind of future
  use) instead of the in-memory dict used here.
- **A real bug found via full-suite testing, not just the isolated middleware
  tests:** the rate limiter is module-level state on the shared `app` object,
  which persists across pytest's *entire* session (the app is imported once).
  Adding it without a corresponding test-isolation fix broke 44 unrelated
  tests two-thirds of the way through the suite - later tests' `register()`/
  `login()` calls started getting legitimately 429'd by hit counts
  accumulated from every earlier test's auth calls. The isolated
  `test_middleware.py` run (5 tests) passed cleanly and would never have
  caught this; only running the full 74-test suite surfaced it. Fixed by
  clearing the limiter's state in the `client` fixture itself
  (`tests/conftest.py`), the same place the DB-session and event-loop
  isolation fixes from earlier phases already live.
- **Readiness probe** (`GET /health/ready`, spec §47): actually executes
  `SELECT 1` against the database, distinct from `GET /health` (liveness -
  process is up, no dependency check). The liveness/readiness split matters
  for real orchestration - a load balancer should stop routing traffic on a
  readiness failure even while the process itself is still alive.
- **Multi-stage, non-root Dockerfile** (spec §48): build stage has
  gcc/libpq-dev for compiling deps; runtime stage strips those out, runs as
  a non-root `appuser`, and adds a `HEALTHCHECK`. **Not verified by an actual
  `docker build`** - Docker isn't available in this sandbox. Reviewed
  carefully and internally consistent (correct stage references, correct
  `--user` pip install + `PATH` handling), but this is the same category of
  honesty as the M-Pesa/Stripe providers: correctly-shaped, not proven by
  execution.
- **GitHub Actions CI** (`.github/workflows/ci.yml`, spec §48-49): runs the
  real test suite (Alembic migrations + full pytest run) against a Postgres
  16 service container on every push/PR, then a Docker build-only step. Not
  executed against real GitHub infrastructure in this build (no network
  access to trigger it here) - the individual pieces (migrations working,
  pytest passing, the Dockerfile's shape) were each verified independently
  in this sandbox, which is the strongest verification available without
  actual CI runner access.

## Next phase entry point - none remain in the backend roadmap
Phases 1 through 9 of the spec's own roadmap (§64) are now complete to
varying depths (see "Deferred" and "Known gaps" for exactly what's thin or
missing within each). What's left is not a phase but a different kind of
project: **the entire frontend** - the Next.js admin dashboard and public
e-commerce site that spec §41-46/§66-73 describe - which has not been started
in any form. Everything built across all nine phases is a backend API; there
is no UI anyone could open in a browser today beyond the auto-generated
OpenAPI docs at `/docs`.

## Phase 10 - Frontend (partial: a real vertical slice, not the full route list)
`apps/web` is a genuine Next.js 14 App Router + TypeScript + Tailwind
frontend, not a mockup - see `apps/web/README.md` for exact scope (login,
dashboard, livestock list/detail) and `docs/design-notes.md` for the visual
design system. Verified: clean `npm run build` (TypeScript strict, no
errors), and every API call checked against the live backend with real data
in this session - response shapes confirmed to match the TypeScript types
field-for-field, not assumed. **Not verified:** actual browser rendering -
this sandbox has no headless browser tool, so nothing has been visually
confirmed, only build-correctness and API-contract-correctness. Also
discovered and fixed via `next/font/google` failing at build time: this
sandbox's network egress doesn't include `fonts.googleapis.com` either (same
class of constraint as the M-Pesa/Stripe providers) - system-font fallbacks
are used instead, with the swap-back documented as a one-file change.

## Resolved gaps (previously listed below as open, now fixed)
- **User role management now has an update path.**
  `PATCH /api/v1/users/{user_id}/roles` (tenant-scoped - a role from another
  org is silently dropped, not an error, matching the existing pattern in
  `create_user`) lets an admin change a user's roles after creation. Losing
  all roles immediately revokes access - verified live by round-tripping a
  worker through no-access → granted → access → revoked → no-access again.
- **`AuditLog` has its first real writer.** `update_user_roles` is exactly
  the kind of cross-cutting action (spec §28's own example: "user role
  changed") the domain-specific event trails (`AnimalEvent`,
  `OrderStatusEvent`, etc.) were never meant to cover. A minimal
  `GET /api/v1/audit-logs` (permission: `audit.view`, already existed in the
  catalog but was also unused) lets staff actually see it. Still no generic
  `record_audit_log()` helper wired into other mutation points (price
  changes, etc.) - this closes the specific gap that was previously
  flagged, not the general principle of auditing everything.

## Known gaps carried forward (found during this build, not yet fixed)
- **M-Pesa Daraja and Stripe providers are implemented but genuinely untested
  against the real APIs** - this sandbox has no network access to Safaricom's
  or Stripe's endpoints (see `infrastructure/networking` constraints). The
  `MpesaProvider`/`StripeProvider` classes follow each API's documented
  request/response/webhook-signature shape, but "follows the docs" is not the
  same claim as "verified against the live API," and that distinction is worth
  preserving rather than blurring. The `MockProvider` is fully live-tested and
  exercises the exact same code path in `payments/service.py` (initiate →
  webhook → idempotency → signature rejection), so the *integration logic* is
  proven even though the *provider adapters* aren't.
- **Notifications are in-app only.** Email/SMS/push channels are a documented
  extension point (`notifications/models.py` docstring) but not implemented -
  same honesty stance as the payment providers above, but here there isn't
  even a not-live-tested class to point to; it's just not built yet.
- **No real task scheduler.** `POST /notifications/run-scheduled-checks`
  contains real, tested logic (due follow-ups, low stock, reservation
  expiry), but nothing calls it automatically. A production deployment needs
  Celery beat, a cron job, or equivalent hitting that endpoint (or the
  service function directly) once a day per organization - that's Phase 9
  DevOps scope, not built here.
## Phase 11 - Guest checkout (resolves the "customers can't order" gap)
Spec §69: "Do not force registration before browsing. Allow guest checkout.
Allow account creation after purchase." No customer login/session system was
built (that remains real, deferred scope - see below), but a customer never
needed one to place an order: `POST /public/{org_slug}/orders` accepts
contact details directly, resolves them to a real `Customer` CRM record via
`find_or_create_by_contact` (the seam built for exactly this in Phase 4),
and reuses `commerce.service.create_order` unchanged - same row-locking,
same listing-deactivation fix from Phase 7, same everything, just entered
through a door with no auth dependency instead of `require_permission`.

Order lookup and payment initiation for a guest both require the checkout
email as a lightweight ownership check - an order UUID is hard to guess,
but "hard to guess" isn't "authenticated," so this adds one real check
rather than trusting the URL alone. Verified live: a second guest attempting
to order the now-reserved animal is correctly rejected (404, listing no
longer active), and payment initiation with a mismatched email is rejected
before it can touch the order.

**Still deferred:** an actual customer login/session system (spec §16/§70's
`/dashboard`, `/orders`, `/payments` portal) - a returning customer still
can't view past orders without knowing the checkout email for each one, and
there's no password/magic-link account creation "after purchase" as the spec
suggests. Guest checkout closes the *transactional* gap (customers can now
buy); the *account* gap (customers managing an ongoing relationship with the
farm) is real, separate, non-trivial scope, not built here.

- **Rate limiting is per-process, in-memory (Phase 8).** Correct for this
  build's single-instance docker-compose topology; wrong the moment there's
  more than one API replica behind a load balancer, since each replica would
  track hits independently and the effective limit would multiply by replica
  count. Needs a Redis-backed limiter (Redis is already in docker-compose)
  before horizontal scaling - documented in `core/middleware.py`, not fixed.
- **No metrics/tracing stack (Phase 8).** Structured logging with request IDs
  is the foundation Phase 8 built, not the full observability picture spec
  §47 asks for - no Prometheus metrics endpoint, no distributed tracing, no
  Grafana dashboards. A request's full story is reconstructable from logs via
  its request ID, but there's no aggregated view across requests yet.
- **CI/CD pipeline is not executed against real infrastructure (Phase 9).**
  `.github/workflows/ci.yml` is written to run the actual test suite against
  a real Postgres service container, and its constituent steps were each
  independently verified in this sandbox - but the workflow file itself has
  never been run by GitHub Actions, since this environment has no network
  access to trigger that. Same honesty stance as the Dockerfile and the
  M-Pesa/Stripe providers above.
- **No staging/production environment configuration (Phase 9).** Only local
  dev (`docker-compose.yml`) exists. Spec §49 calls for separated dev/
  staging/production config - `.env.example` documents the variables that
  would differ, but there's no actual staging deployment or infrastructure-
  as-code (Terraform/Kubernetes manifests) for either environment.

## Phase 12 - Procurement (suppliers, purchase orders)
Spec §9/§26: the one core service from the original bounded-context list
(§9's "Procurement Service") that had no module at all - `procurement.manage`
existed in the RBAC permission catalog and in three roles' default grants
(Farm Manager, Inventory Manager) since Phase 1, but nothing checked it,
because nothing existed to protect.

New module `modules/procurement/` follows the established shape exactly:
`models.py` / `schemas.py` / `service.py` / `router.py`, migration `0010`.
- **Suppliers**: plain CRUD (name, contact, tax PIN for spec §57's KRA-related
  fields, payment terms, products supplied), same shape as `customers/`.
- **Purchase orders**: lifecycle `requested -> approved -> ordered -> received
  -> invoiced -> paid`, plus `rejected`/`cancelled` off-ramps - an explicit
  `_PO_TRANSITIONS` table enforced in `service.update_status`, the same
  pattern as `commerce._ORDER_TRANSITIONS` and livestock's status machine.
  Every transition writes an append-only `PurchaseOrderStatusEvent` (same
  `reject_audit_log_mutation()` trigger reused from migration 0002, not a new
  function). PO numbers are per-org, gap-free, and row-locked
  (`PurchaseOrderCounter` + `SELECT ... FOR UPDATE`) - identical mechanism to
  `finance.InvoiceCounter`/`_next_invoice_number`, not a new pattern.
- **The seam that actually matters**: transitioning a PO to `received` calls
  `inventory.service.record_movement` directly, once per PO line that has an
  `inventory_item_id`, with `movement_type="purchase"` and `reference=
  po_number` - the same "reuse the other module's service function inside
  the same transaction" approach breeding.service already uses for
  `livestock.service.create_animal`, not a new integration style. A PO line
  with no `inventory_item_id` (e.g. a one-off service charge) is received
  without creating a movement - deliberately, not an oversight; see
  `test_po_line_without_inventory_link_receives_without_stock_movement`.
  This is what makes "goods received" real rather than cosmetic: stock
  actually lands in the ledger built back in Phase 3, with the PO number as
  the ledger entry's `reference`, so a stock movement can be traced back to
  the PO that caused it.
- `total_amount` is computed at read time from line items and explicitly
  `.quantize(Decimal("0.01"))`-ed before serializing - worth noting because,
  unlike `inventory.current_stock` (a DB `Numeric(12,2)` column with a
  guaranteed scale), this total is a Python-side sum of Decimals with
  whatever exponent their JSON input happened to carry; left unquantized it
  would serialize inconsistently (e.g. `"450"` vs `"450.0000"`) depending on
  the specific quantity/unit_cost strings a client sent.
- No new permission was added - `procurement.manage` covers both suppliers
  and purchase orders, matching how `customers.manage` already covers a
  single CRM bounded context end to end elsewhere in this codebase.

**Honesty note, same as every other module in this document:** written and
statically checked (`python -m py_compile`) in a sandbox with no Postgres and
no installed Python packages - it has **not** been run against a live
database the way Phases 1-9's modules were (see `tests/conftest.py`'s real-
Alembic-migration test harness). `tests/test_procurement.py` is written
against that same harness and should be run for real (`pytest
tests/test_procurement.py`) before this is trusted the way the rest of the
backend currently is. Until that run happens, this phase's claims are
"correctly-shaped, reviewed against the actual call signatures of the
functions it calls" - not "proven by execution," the same distinction this
document draws for the M-Pesa/Stripe providers and the Dockerfile.

**Still not covered by this phase:** procurement approval routing beyond a
single status flag (spec §26 doesn't ask for multi-level approval, so this
wasn't attempted); supplier invoice/payment reconciliation against the
finance ledger (a received PO does not yet auto-create a
`finance.FinanceTransaction` the way `PaymentSucceeded` and inventory
consumption already do - an `expense` transaction on `invoiced`/`paid` would
be the natural next hook, following `finance/handlers.py`'s existing
`InventorySpend` subscriber pattern, but wiring it wasn't done here to keep
this phase reviewable as one unit).

## Phase 13 - Employee management (spec §27)
Another bounded context from the spec's original list (§27) with no module
at all until now - unlike procurement, there wasn't even an unused
permission sitting in the catalog; `employees.manage` is new in this phase.

New module `modules/employees/`, same shape as every other phase:
- **`Employee` is deliberately a separate table from `identity.User`**, linked
  by an optional `user_id`. The reasoning: a Farm Worker who logs in to
  record weights (a `User` with a role) and a casual laborer paid in cash who
  never touches the system are both "employees" in spec §27's sense, but only
  one of them is a system user. Forcing every employee to have a login would
  mean either fabricating accounts for people who don't need one, or leaving
  casual staff untracked entirely; forcing every `User` to be an `Employee`
  would wrongly pull customers and non-staff accounts into HR records. The
  optional FK is the seam, not a compromise - `create_employee` validates
  that a supplied `user_id` actually belongs to the same organization before
  linking it (`test_employee_linked_user_must_belong_to_same_org`).
- **Employment status**: `active -> {on_leave, suspended, terminated}`,
  `on_leave -> {active, terminated}`, `suspended -> {active, terminated}`,
  `terminated` terminal - same explicit transition-table-in-service pattern
  as `commerce._ORDER_TRANSITIONS` and now `procurement._PO_TRANSITIONS`, not
  a new style. Every transition writes an append-only `EmployeeStatusEvent`
  (same `reject_audit_log_mutation()` trigger reused again, not a new
  function - that trigger has now been attached to four different tables
  across four phases without being redefined once).
- **Work shifts** (`WorkShift`): a lightweight rota entry - who's expected
  where, when - explicitly *not* attendance tracking (no clock-in/clock-out)
  and *not* a scheduling optimizer. Spec §27 itself lists "payroll, attendance,
  leave, performance" as *future* modules to design for, not build now; this
  phase built exactly the one item spec §27 puts in its present-tense list
  ("work schedules") and stopped there deliberately, not for lack of time.
- Employee numbering (`EMP-000001`, ...) uses the same row-locked
  per-org-counter mechanism as `finance.InvoiceCounter` and
  `procurement.PurchaseOrderCounter` - third time this exact pattern has been
  copied verbatim rather than reinvented.
- New permission `employees.manage`, granted to Farm Manager (spec §5: manages
  daily operations, which includes staff) and System Administrator (HR
  administration overlaps with technical administration in a small farm
  business); deliberately *not* granted to Veterinarian or Sales Manager,
  matching the spec's role boundaries.

**Not covered by this phase:** payroll, attendance/clock-in, leave requests,
and performance reviews - spec §27's own "future modules" list, unchanged.

## Phase 14 - Farm asset management (spec §15)
The last of the three fully-missing bounded contexts identified in the gap
analysis. New module `modules/assets/`.

- **Depreciation is computed at read time, never stored** - the same
  "derived value, not a column that can drift" decision Phase 12 made for
  `PurchaseOrder.total_amount` and Phase 3 made for `InventoryItem
  .current_stock`. `service.depreciated_value` implements straight-line
  depreciation from `acquisition_cost`, `useful_life_years`, and
  `salvage_value`, clamped so it never depreciates past the asset's useful
  life (floors at `salvage_value`) and never exceeds `acquisition_cost`
  regardless of how the inputs are supplied. An asset with no
  `useful_life_years`/`acquisition_cost` set (e.g. a fence - spec §15 lists
  it alongside tractors and generators, and not every asset needs formal
  depreciation tracking) simply reports `current_value: null` rather than a
  fabricated number; `current_value` falls back to raw `acquisition_cost`
  only when depreciation inputs are genuinely absent, not when they're zero.
- **Maintenance is an immutable log** (`AssetMaintenanceRecord`), not a
  "last serviced" field that gets overwritten - the same "don't just store
  current state, keep the trail" principle spec §7 states explicitly for
  livestock lifecycle events and which this codebase has now applied to
  four different domains (livestock, orders, purchase orders, and now
  assets). `total_maintenance_cost` on the read model is the roll-up of that
  log, not a separately-maintained running total that could drift from it.
- **One real behavior, not just data storage**: logging a `service` or
  `repair` maintenance record against an asset currently `under_maintenance`
  moves its status back to `in_use` automatically - the same "the event is
  the state change" reasoning `commerce`/`livestock` already use (a sale
  event moves an animal to `sold`; here, a completed repair moves an asset
  back into service). An `inspection` record deliberately does *not* trigger
  this - an inspection finding a fault doesn't imply the fault was fixed
  (`test_maintenance_records_roll_up_and_clear_under_maintenance_status`
  checks exactly this distinction, not just that the roll-up total is
  correct).
- Optional `supplier_id` FK ties an asset back to Phase 12's `Supplier` when
  it was bought through a tracked one - same optional-link pattern as
  `Employee.user_id`, not a required relationship.
- New permission `assets.manage`, granted to Farm Manager and Inventory
  Manager (equipment tracking overlaps with the inventory role's existing
  remit more than any other role's) - a judgment call, since the spec's role
  list (§5) doesn't name an "Asset Manager" role explicitly.

**Not covered by this phase:** declining-balance or units-of-production
depreciation methods (straight-line only, which is what spec §15 implies by
just saying "depreciation" without specifying a method); asset disposal
creating a financial transaction or livestock-sale-style event trail (an
asset's `status` can be set to `disposed` via the generic update endpoint,
but unlike a PO's `received` transition or a livestock `sold` transition,
this doesn't yet trigger any side effect in Finance).

## Honesty note applying to Phases 12-14 collectively
All three were written and statically checked (`python -m py_compile`,
manual cross-reference against the actual signatures of every function they
call) in a sandbox with no network access and no Postgres or Python packages
installed - meaning, unlike Phases 1-11, **none of the three has been run
against a live database yet**. `tests/test_procurement.py`,
`tests/test_employees.py`, and `tests/test_assets.py` are written against the
same real-Alembic-migration test harness (`tests/conftest.py`) the rest of
the suite uses and should be run for real - `pytest tests/test_procurement.py
tests/test_employees.py tests/test_assets.py` - before any of the three is
trusted the way Phases 1-11 currently are. This is the same "correctly-shaped,
not proven by execution" distinction this document has drawn from the start
for the M-Pesa/Stripe providers and the Dockerfile; it now also applies to
these three modules until someone runs them against Postgres.

## Phase 15 - Customer self-service accounts (resolves the last part of the Phase 11 gap)
Phase 11 (guest checkout) explicitly deferred this: "an actual customer
login/session system (spec §16/§70's `/dashboard`, `/orders`, `/payments`
portal) ... is real, separate, non-trivial scope, not built here." This
phase is that scope.

**The load-bearing discovery, not a new design decision:** `identity
/permissions.py`'s `DEFAULT_ROLE_GRANTS` has included a `"Customer": []`
entry since Phase 1 - every organization has had an empty-permission
"Customer" role sitting unused since the very first migration, with the
comment "customers access their own data via ownership checks, not RBAC
perms" already explaining exactly the design this phase implements. This
was clearly the intended seam for customer accounts from the start; Phase 15
connects it rather than inventing a parallel auth system.

- **One new column, not a new auth system**: `identity.User.customer_id`
  (nullable FK to `customers.Customer.id`, migration `0013`). A customer
  account is an ordinary `User` - same password hashing, same JWT
  access/refresh tokens, same `/api/v1/auth/login` every staff member uses
  - whose role is "Customer" (zero permissions) and whose `customer_id`
  links it to a CRM record. No second login endpoint, no second token
  format, no second session mechanism.
- **Registration reuses `find_or_create_by_contact`** (Phase 4's function,
  already reused once by Phase 11's guest checkout) - so a customer who
  checked out as a guest and later registers with the same email gets their
  existing order history attached to the new account instead of a
  disconnected duplicate CRM record
  (`test_registering_with_email_already_used_for_guest_checkout_links_history`
  verifies this explicitly, not just that registration succeeds).
- **New module `modules/accounts/`**, split into two routers on purpose:
  `public_account_router` (`POST /api/v1/public/{org_slug}/account/register`
  - org-scoped like the rest of `modules/public`, rate-limited the same way
  as `/auth/register`) and `account_router` (`GET /api/v1/account/me`,
  `/orders`, `/orders/{id}` - genuinely authenticated). They're kept out of
  `public/router.py` itself specifically so that file's own comment ("No
  auth dependency anywhere in this router") stays true; register is the one
  operation in the customer-facing flow that both needs no token to call
  and produces one.
- **`get_current_customer`** (`accounts/deps.py`) rejects any `User` whose
  `customer_id` is `None` with 403 - closing the direction the "Customer"
  role's zero-permissions design doesn't automatically close by itself: a
  Customer-role login already can't reach staff endpoints (no permissions to
  grant), but nothing stopped a *staff* login from hitting `/account/*`
  before this explicit check existed
  (`test_staff_account_cannot_use_customer_portal`).
- **Order ownership uses the same 404-not-403 convention** Phase 11's guest
  order lookup already established (`public.service.get_guest_order`) - an
  order that exists but isn't the caller's own reads as "not found," never
  confirming to an authenticated stranger that a given order id is real.

**What this closes vs. what's still open:** a returning customer can now
register, log in, see their own profile and order history without emailing
the farm or remembering a checkout email per order (Phase 11's residual
gap). **Still not built**: editing one's own profile (`/account/me` is
currently read-only). Payment history/invoice viewing and password reset -
both flagged here originally as blocked on the missing email channel - are
now built; see Phase 27 below.

**Honesty note, same as Phases 12-14**: written and statically checked in a
sandbox with no Postgres/network - not run against a live database yet.
`tests/test_customer_accounts.py` should be run for real
(`pytest tests/test_customer_accounts.py`) before this phase is trusted the
way Phases 1-11 are.

## Phases 16-25 - remaining refinements + deployment infra (this session, continued after Phase 15)
Kept intentionally shorter than Phases 1-15's entries above: the detailed
per-decision reasoning for each of these now lives in the code itself
(docstrings and inline comments at each change site), following the same
"comments explain why, this document indexes what and points at it" split
this file has used all along - duplicating all of it here would just be
the same text twice. This section is the index.

- **Phase 16 - Redis-backed rate limiting.** `core/middleware.RedisRateLimiter`
  (fixed-window via atomic INCR+EXPIRE) alongside the original in-memory
  `RateLimiter`, chosen via `settings.RATE_LIMIT_BACKEND` (default
  `"memory"` - zero behavior change for anything existing). `rate_limit_auth`
  became `async`; both call sites (`identity/router.py`, `accounts/router.py`)
  updated to `await` it. See `core/middleware.py`'s class docstrings for the
  fixed-window-vs-sliding-log trade-off reasoning.
- **Phase 17 - Edit-listing.** `commerce.ListingUpdate` +
  `PATCH /api/v1/listings/{id}` (title/description/price/featured only -
  see `schemas.ListingUpdate`'s docstring for why `animal_id`/`pricing_type`
  are deliberately excluded).
- **Phase 18 - Global search (spec §37).** New `modules/search/`, new
  `search.use` permission granted to every staff role. One bounded ILIKE
  query per entity type (animals/customers/orders/invoices/suppliers/
  inventory/employees/assets) rather than a single UNION - see
  `search/service.py`'s module docstring.
- **Phase 19 - Bulk CSV import (spec §73).** New `modules/bulk_import/`.
  `dry_run=true` (default) previews and validates without writing;
  `dry_run=false` writes valid rows and reports invalid ones by row number,
  never blocking the good rows for the bad ones. Livestock import takes
  `farm_id` as a call parameter (every row needs one; a CSV column would
  make the caller repeat it per-row for no reason) - see
  `bulk_import/service.py`'s `import_livestock` docstring.
- **Phase 20 - PDF export (spec §44/§59).** New `reportlab` dependency.
  `finance/pdf.py` (invoice PDFs, `GET /api/v1/finance/orders/{id}/invoice.pdf`)
  and `reporting.service.render_livestock_report_pdf`
  (`GET /api/v1/reports/export/livestock.pdf`). See either module's
  docstring for the "written, not run - reportlab isn't installable in this
  sandbox" caveat, which applies to both.
- **Phase 21 - QR codes (spec §38).** New `qrcode` dependency.
  `GET /api/v1/livestock/{id}/qrcode.svg` (staff, SVG so no Pillow/libjpeg
  needed in the image) plus a new public, narrow
  `GET /api/v1/public/{org_slug}/animals/{id}/qr-profile` endpoint
  (`public.schemas.AnimalQRProfileOut` - same allowlist reasoning as
  `PublicListingOut`, extended to animals that aren't necessarily listed
  for sale). New `PUBLIC_SITE_BASE_URL` setting - a real deployment must
  override the localhost default or every QR code printed before that
  change points at the wrong place. The frontend page it links to
  (`{PUBLIC_SITE_BASE_URL}/{org_slug}/animals/{id}`) does not exist in
  `apps/web` yet - generating the code and building the page it points to
  are separable, and only the former was in scope here.
- **Phase 22 - Organization settings (spec §56/§57/§60).** `Organization`
  gained `invoice_prefix`/`po_prefix`/`employee_prefix`/`asset_prefix`/
  `tax_rate`/`default_weight_unit`/`default_volume_unit` (migration `0014`),
  editable via `GET/PATCH /api/v1/organization/settings`. This closes a
  flagged-but-unfixed gap from Phase 12-14 (`finance/service.py` had an
  explicit `# spec §60: real deployments make the prefix org-configurable`
  comment sitting next to the hard-coded `"INV-"` literal) and fixes a real
  bug: `generate_invoice` previously hard-coded `tax_amount=Decimal("0")`
  unconditionally, contradicting spec §57's explicit "do not hard-code tax
  rates" instruction - now computed from `org.tax_rate`, defaulting to 0%
  so no existing org's invoices change unless they explicitly configure a
  rate.
- **Phase 23 - FIFO inventory costing (spec §14).** The most substantial
  item in this batch. `inventory/service._fifo_layers_remaining` walks a
  given item's entire movement ledger once, oldest-first, netting every
  outbound movement against the inbound layers it actually drew from -
  computed fresh every call from the immutable ledger (same "derived, never
  a stored counter" principle as `current_stock`), never mutating old
  `StockMovement` rows. `fifo_unit_cost_for_consumption` feeds this into
  `record_movement`: an outbound movement with no explicit `unit_cost` now
  gets one estimated from FIFO layers (quantized to match the column's
  actual `NUMERIC(12,2)` precision - an early draft quantized to 4 decimal
  places and would have silently mismatched what Postgres actually stores;
  caught before it shipped, not after). This also means the
  `InventorySpend` finance event - previously gated on an explicit
  `unit_cost` being supplied - now fires for FIFO-estimated costs too,
  closing a real undercounting gap (an unpriced consumption previously
  generated no expense record at all). New `GET /api/v1/inventory/valuation`
  reports quantity/value per item, kept as its own endpoint rather than
  folded into `GET /items` since it's real per-item ledger-walking work not
  worth paying on every plain list call (spec §46).
- **Phase 24 - Observability (spec §47).** New `core/observability.py`:
  `PrometheusMiddleware` + `GET /metrics` (labeled by route *template*, not
  raw path, to avoid unbounded cardinality from per-ID labels - the most
  common Prometheus mistake), and `setup_tracing()` for OpenTelemetry,
  genuinely a no-op unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set. New
  dependencies: `prometheus-client`, `opentelemetry-api`/`-sdk`/
  `-instrumentation-fastapi`/`-exporter-otlp-proto-http`. **Important
  distinction from every other new dependency this session**:
  `prometheus-client` backs middleware wrapping *every* request, so unlike
  reportlab/qrcode (only imported inside the specific handlers that use
  them), a missing `prometheus-client` install would fail the entire app at
  startup, not just one feature.
- **Phase 25 - Deployment infrastructure (spec §48/§75).** New
  `infrastructure/terraform/` (AWS: VPC with public/private subnets, ECS
  Fargate running the API behind an ALB with autoscaling, RDS Postgres,
  ElastiCache Redis, S3 for the object-storage abstraction spec §2 asks
  for, ECR) and `infrastructure/kubernetes/` as an alternative (Deployment
  with an `alembic upgrade head` init container, Service, HPA, Ingress) -
  the latter deliberately runs only the application tiers, not
  self-hosted Postgres/Redis, matching spec §48's own wording ("managed
  PostgreSQL, Redis" as distinct from "containerized services"). New
  `docs/deployment.md` (spec §75 names this file explicitly; it did not
  exist before this phase). **This is the one category of work in the
  entire session that could not even be `py_compile`-checked** - Terraform
  and Kubernetes YAML aren't Python. Verification here means: every
  cross-file Terraform resource reference was manually checked against
  every declared resource name (no typos, nothing referencing something
  that doesn't exist), and all three Kubernetes files were confirmed to
  parse as valid YAML - but neither `terraform plan` nor
  `kubectl apply --dry-run` has ever actually run, because this sandbox has
  neither binary, no network, and no cloud credentials. This is a strictly
  weaker verification bar than everything else in this document, and
  `docs/deployment.md` says so again at its own top rather than only here.

**What's still genuinely open after Phase 25**: SMS/WhatsApp notification
delivery specifically (email now works as of Phase 27 - see that entry
below - but spec §13's SMS/WhatsApp channels don't), live-testing
M-Pesa/Stripe/SMTP against real sandboxes, actual browser verification of
`apps/web`, and CI/CD actually deploying (rather than just testing/build-
checking) - `.github/workflows/ci.yml` has a build-only Docker step
already; wiring it to push to ECR and run `terraform apply`/`kubectl apply`
on a protected branch is real additional scope not attempted alongside
everything else in this session. (Banners and frontend UI for Phases
12-25, both listed here originally, are now built - see Phase 26 below.)

## Phase 26 - frontend catches up to Phases 12-25
Same "index, not a duplicate" approach as the Phase 16-25 entry above -
detailed reasoning lives in each new/edited file itself. New pages: 
`admin/procurement/`, `admin/procurement/purchase-orders/[id]/`,
`admin/employees/`, `admin/employees/[id]/`, `admin/assets/`,
`admin/assets/[id]/`, `admin/search/`, `admin/settings/`,
`admin/inventory/valuation/`, `shop/[orgSlug]/account/register/`,
`shop/[orgSlug]/account/login/`, `shop/[orgSlug]/account/`. Edited:
`admin/listings/page.tsx` (edit modal), `admin/orders/[id]/page.tsx`
(invoice + PDF download), `admin/livestock/[id]/page.tsx` (QR code card),
`admin/livestock/page.tsx`/`admin/inventory/page.tsx`/
`admin/customers/page.tsx` (bulk import), `shop/[orgSlug]/page.tsx`
(banners), `shop-header.tsx` (account nav link), `lib/types.ts` (every new
interface), `lib/api.ts` (`apiUpload`, `apiDownload`, exported `API_BASE`).
New shared component: `components/bulk-import-modal.tsx`.

Full detail - including the verification-status caveat, which is
materially weaker here than anywhere else in this document since this
sandbox has no `node_modules` and no network to install them - is in
`README.md`'s "Phase 26" section and `apps/web/README.md`'s matching
entry. Short version: every file's brace/paren/bracket balance was checked
and every field name cross-referenced against `types.ts` by hand; nothing
was type-checked, linted, or built, and nothing was opened in a browser.
`npm install && npx tsc --noEmit && npm run build` is the next real step,
the same way `pytest` is for Phases 12-25's backend code.

## Phase 27 - email channel + password reset (spec §5/§13/§55)
`modules/notifications/email/` reuses `modules/payments/providers/`'s exact
shape: `EmailProvider` (abstract) → `MockEmailProvider` (always succeeds,
no network, what tests use) → `SMTPEmailProvider` (real stdlib `smtplib`,
no new dependency, written-not-live-tested same as `mpesa.py`/
`stripe_provider.py`). Every send writes a durable `EmailOutbox` row
regardless of provider (mirrors `Payment` being the durable record
independent of which payment provider processed it) - visible at
`GET /api/v1/notifications/email-outbox`, gated on `audit.view` (same
permission as the audit log - both are "what actually happened"
visibility, not day-to-day operational access).

`PasswordResetToken` mirrors `RefreshToken`'s hashed-token-at-rest pattern
in `identity/models.py` line for line - SHA-256 hash stored, raw token
only ever exists in the email and the confirm request. `request_password_
reset` is deliberately enumeration-safe: identical response whether or not
the email matches an account, checked by
`test_password_reset_unknown_email_does_not_leak_existence`. Tokens are
single-use (`used_at` checked before allowing reuse) and expire in 60
minutes (`PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`).

The `PaymentSucceeded` event now has a second subscriber
(`on_payment_succeeded` in `notifications/handlers.py`) alongside whatever
already existed - this is the first customer-facing (not staff in-app)
notification in the codebase, and it didn't exist before because there was
nowhere to send it; the in-app `Notification` model is staff-only (keyed
to this org's own users), so a payment confirmation reaching the actual
customer had to wait for an email channel to exist at all.

`accounts.schemas.MyOrderDetailOut` (customer portal order detail) gained
`invoice` and `payments` fields - closing the one specific gap Phase 15's
own entry flagged by name ("payment history/invoice viewing... `/account/
orders/{id}` doesn't currently surface payment or invoice data").

Migration `0015` - `password_reset_tokens`, `email_outbox`. Chain is now
0001→0015, still a single unbroken line, still one head.

**Honesty note, unchanged pattern from Phases 12-25**: written and
`python -m py_compile`-checked in the same no-network, no-Postgres
sandbox - not run. `tests/test_password_reset_and_email.py` (7 tests) and
the new assertions appended to `tests/test_customer_accounts.py` are
written against the same real-Alembic-migration harness the rest of the
suite uses and should be run for real before trusted.

## Phase 28 - frontend for Phase 27
`/reset-password` (one page, two modes - request form with no `?token=`,
confirm form once one's present - shared by staff and customer logins
since the backend endpoint doesn't distinguish between them), "Forgot your
password?" links on both login pages, an email send-log table added to
`/admin/settings`, and `/shop/[orgSlug]/account/orders/[orderId]`
(invoice + payment history, per Phase 27's `MyOrderDetailOut` additions) -
the account page's order list now links to it instead of showing inert
cards. Same verification status as Phase 26: no `node_modules`, nothing
type-checked or built in this sandbox; brace/bracket balance and every
`types.ts` field reference checked by hand.

## Phase 29 - the gaps found by actually using the app
Not backend logic - everything here except two small additions (noted
below) was already implemented; this phase is entirely about the fact that
Phase 26's "frontend catches up" pass covered every *internal* admin
feature but missed the literal front door, and a systematic router-by-page
audit (every `app/modules/*/router.py` endpoint checked against every
`apps/web/src/app/**/page.tsx`) turned up several more.

- **`/register`** - no page anywhere called `POST /api/v1/auth/register`.
  Every test account so far existed only because a user ran `curl`
  manually. This is the single most consequential fix in this phase: a
  multi-tenant SaaS platform with no UI path to create a new tenant is not
  really onboardable.
- **`/admin/users`** - no staff invite/role-management UI existed at all.
  Required one small backend addition: `GET /api/v1/users/roles`
  (`identity/router.py`) - every org's roles have existed since
  `register_organization` first ran in Phase 1, but nothing ever listed
  them for a caller, silently blocking any UI that needed to offer a role
  picker.
- **`/admin/cms`** - the public storefront (Phase 7, Phase 26) has
  rendered farm profile/testimonials/blog/FAQs/banners this whole time;
  there was never a way to *write* any of it through the UI. One tabbed
  page covering all five `cms.manage`-gated resources.
- **`/admin/reservations`** - required a second small backend addition:
  `commerce.service.list_reservations` + `GET /api/v1/reservations`.
  create/get-one/cancel/expire-stale existed since Phase 4; nothing ever
  listed them as a set.
- **`/admin/notifications`**, **`/admin/reports/profitability`**, customer
  edit on `/admin/customers`, and a "Record payment" section on
  `/admin/orders/[id]` - four more endpoints (`notifications` list/read/
  preferences, `reports.profitability`, `customers.update`,
  `payments.{mock,mpesa,stripe}`) that had working backend logic and no
  UI anywhere.

Same verification status as every phase since 12: written, reviewed
(brace/bracket balance and `types.ts` field references checked by hand
across all 49 frontend files as of this phase; the two backend additions
are `py_compile`-clean with new tests in `test_auth_and_rbac.py` and
`test_commerce.py`), never executed.

## Phase 30 - gaps closed after the storefront redesign

Everything here is additive; migrations `0023`-`0027` only add tables/columns/indexes and all
downgrade cleanly.

| Gap | Resolution |
|---|---|
| Platform audit skipped any `/status` route and every livestock POST, and logged crop writes twice | `audit_middleware.is_self_audited` is an exact method+path allow-list of the routes that audit themselves |
| Platform-admin passwords had no minimum | 12-72 characters on create and reset (not on login, so existing admins keep working); seed script and forms agree |
| Billing subscribe / payment history were open to any signed-in user; malformed receipt id was a 500 | require `users.manage`; receipt id typed as UUID (422) |
| First claimant of a custom domain locked everyone out; Vercel registered before ownership proof; unverified claimant could unregister a verified domain | claims never block; one *verified* holder (partial unique index, migration 0026); DNS proof evicts a stale holder; Vercel only after verification; strict hostname validation |
| Crops bypassed plan limits | `max_crop_plantings` on tiers (0027), enforced on create and on downgrade |
| Parallel requests rotated the refresh token several times and logged users out | single-flight refresh + "someone already refreshed" detection; downloads retry once |
| Customers could not pay online | M-Pesa panel on the order page; `GET /public/payment-methods` lists only fully configured methods; phone numbers normalised to `2547XXXXXXXX` everywhere (guest, staff, billing) |
| Lists silently stopped at the first page | `apiFetchAll` / `platformApiFetchAll`; deterministic `(created_at, id)` ordering |
| Validation errors displayed as raw JSON | `formatErrorDetail` in both API clients |
| Admin ignored the `permissions` the backend already sends | `lib/permissions.ts` map (verified by the audit), `<Can>` / `useCan`, access-denied page, role-aware landing page |
| No edit UI for 5 entities; no audit viewer; reservations could not be created | `EditEntityModal` driven by `lib/edit-configs.ts` (audit-verified against the `*Update` schemas); `/admin/audit` (audit route gained filters, paging and `user_name`); reservation form + "Clear expired" |
| Secrets in the ECS task definition; no CORS / site URL settings | Secrets Manager + `secrets` block; optional `cors_origins`, `public_site_base_url`, `extra_environment`, `extra_secrets` variables |

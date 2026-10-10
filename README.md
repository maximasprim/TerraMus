# Livestock Farm Management, ERP & E-Commerce Platform

Built in phases per the master spec (§64). **All nine backend phases (1-9) are complete, plus guest checkout (Phase 11), customer self-service accounts (Phase 15), procurement/employees/assets (Phases 12-14), and a real frontend (`apps/web`) covering the full staff workflow and a public storefront - see "Frontend" below for exactly what that does and doesn't cover, and "Phases 12-15" below for the most recently added backend modules and their verification status.**

## Phase 1 - Architecture, Database, Authentication, RBAC, Farm Management ✅
## Phase 2 - Livestock: core model, lifecycle timeline, weights, movement ✅
## Phase 2b - Health: vet records, follow-up/due tracking ✅
## Phase 3 - Breeding, Dairy, Feed & Inventory ✅
## Phase 4 - Customers, Listings, Reservations, Orders ✅
## Phase 5 - Payments (M-Pesa/Stripe/Mock), Finance ledger, Invoicing ✅
## Phase 6 - Reporting, Notifications ✅
## Phase 7 - CMS, public site data API, SEO ✅
## Phase 8 - Security headers, rate limiting, structured logging, readiness probe ✅
## Phase 9 - Multi-stage Dockerfile, GitHub Actions CI ✅ (not executed against real Docker/CI infra - see note)
## Phase 11 - Guest checkout ✅ (no customer login required, real order flow - see "Frontend" below for its UI)
## Phase 12 - Procurement: suppliers, purchase orders, goods-received → inventory ledger ✅ (written this session - see "Phases 12-15" below for verification status)
## Phase 13 - Employee management: HR profiles, employment status, work shifts ✅ (same verification caveat)
## Phase 14 - Farm asset management: equipment, straight-line depreciation, maintenance log ✅ (same verification caveat)
## Phase 15 - Customer self-service accounts: register/login/profile/order history ✅ (same verification caveat)

- `docs/architecture.md` - module boundaries, tenant isolation strategy, roadmap
- `docs/database.md` - ERD covering all phases (Mermaid)
- `.github/workflows/ci.yml` - runs the real test suite against a Postgres service container on every push/PR
- `apps/api/` - FastAPI backend:
  - `modules/identity/` - Organization (tenant root), User, permission-based RBAC
    (Role/Permission/RolePermission/UserRole), JWT access + rotating refresh tokens,
    audit_logs table (DB-enforced append-only via trigger), a role-update
    endpoint (`PATCH /users/{id}/roles`) and its own real audit trail
    (`GET /audit-logs`)
  - `modules/farm/` - Farm → Branch → Location (paddock/barn/pen/grazing_area/quarantine)
  - `modules/livestock/` - Animal core model (§6), immutable event timeline (§7),
    weight tracking with ADG (§8), location movement history (§10), a status state
    machine enforcing terminal states (§52.1), and a partial profitability endpoint
    (§25, acquisition cost only - feed/health costs land in Ph2b/Ph3)
  - `modules/health/` - HealthRecord (vaccination/treatment/deworming/examination/
    injury/lab_result/vet_visit/prescription, §5), nested under
    `/livestock/{id}/health`, plus org-wide `/health/due?within_days=N` for
    overdue + upcoming follow-ups. Writes into the animal's timeline in the same
    transaction via a documented shared-kernel seam (`record_external_event`).
  - `modules/breeding/` - BreedingRecord (mating/AI → pregnancy checks →
    delivery, §7), auto-creates offspring Animals with dam/sire lineage on
    delivery, reusing the Phase 2 animal-creation logic rather than duplicating it
  - `modules/dairy/` - LactationCycle + MilkProductionRecord (§8), one active
    cycle per animal enforced, one session per animal/date DB-enforced, herd-wide
    daily summary (total/average/top producers, §12)
  - `modules/inventory/` - InventoryItem + StockMovement as a strict append-only
    ledger (§9-14): current stock is always `SUM(quantity)`, never a mutable
    counter; negative stock blocked unless explicitly allowed per item (§52.11);
    movements can tag `animal_id` for per-animal feed cost (§13)
  - `modules/customers/` - Customer CRM (§16), org-scoped, with a
    find-or-create-by-contact seam for future guest checkout
  - `modules/commerce/` - Listing, Reservation, Order/OrderItem/OrderStatusEvent
    (§17-19). Reservations and Orders use `SELECT ... FOR UPDATE` row locking
    plus partial unique DB indexes to make double-booking an animal actually
    impossible under concurrent requests, not just unlikely - verified with a
    real `asyncio.gather()` concurrency test, not just sequential checks.
    Order status follows an explicit transition table (same pattern as the
    Phase 2 animal status machine); reaching `paid` sells the animal, a
    pre-payment `cancelled` releases it.
  - `modules/payments/` - `PaymentProvider` abstraction (§20) with `MpesaProvider`
    (Daraja STK Push, §21), `StripeProvider` (Payment Intents, §22), and a fully
    functional `MockProvider` for dev/test. Payment status is only ever set by
    a verified, signature-checked webhook - never by the initiating API call
    (§20/§65.10). Webhook idempotency is enforced by a DB unique constraint on
    `(provider, event_id)`, not just an application check.
  - `modules/finance/` - `FinanceTransaction` ledger + `Invoice` (sequential
    per-org numbering via a row-locked counter, §59). Populated automatically
    via event subscriptions (`AnimalAcquired` → expense, `PaymentSucceeded` →
    income + invoice, `HealthRecordCreated`/`InventorySpend` → vet/feed
    expense, added in Phase 6 - see "bugs found" below) rather than direct
    calls from Commerce/Livestock/Health/Inventory - the real payoff of the
    event bus built back in Phase 2.
  - `modules/reporting/` - sits above every other domain module and is
    imported by none of them (avoids the import-cycle risk of enriching
    `livestock`'s own endpoints directly). `/reports/dashboard` composes herd
    stats, milk, inventory value, and monthly finance into the top-card set
    from §68; `/reports/profitability` now uses real feed/health costs
    instead of the Phase 2 acquisition-only placeholder, with an explicit
    `is_actual` flag distinguishing a real sale from an estimate;
    `/reports/export/livestock.csv` is a real CSV export (PDF/Excel deferred
    - see known gaps)
  - `modules/notifications/` - in-app `Notification` + per-category
    `NotificationPreference`. Recipients are derived from RBAC
    (`get_users_with_permission`, added to `identity/service.py`) rather than
    a separate subscription list. Handlers subscribe to 9 event types already
    being published since Phase 2. `POST /notifications/run-scheduled-checks`
    is real, tested logic standing in for a daily cron job that doesn't exist
    yet (no task scheduler in this build - Phase 9 territory)
  - `modules/cms/` - `FarmProfile` (deliberately separate from `Organization`
    - see docs/database.md), `Testimonial`, `BlogPost`, `FAQ`, `Banner`, all
    staff-managed via `cms.manage` with a published/unpublished draft state
  - `modules/public/` - sits above `cms`/`commerce`/`livestock`/`farm`, same
    architectural role as `reporting`. Every route is genuinely unauthenticated
    (`/api/v1/public/{org_slug}/...`), resolving the org by its existing
    `slug`. Response schemas are a strict field allowlist - no
    `acquisition_cost`, `current_value`, `supplier`, or internal notes ever
    reach a public response, the same principle spec §38 states for QR codes.
    Also serves per-org `sitemap.xml`/`robots.txt` (§45), and real guest
    checkout (`POST /orders`, no login) that reuses `commerce.service
    .create_order` unchanged - same row-locking, same listing-deactivation
    fix - plus email-verified order lookup and guest payment initiation.
  - `modules/procurement/` - Supplier CRUD + PurchaseOrder with a real
    `requested→approved→ordered→received→invoiced→paid` lifecycle (§9/§26,
    Phase 12, this session). Receiving goods posts real `StockMovement`s into
    the Phase 3 inventory ledger via a direct in-transaction call to
    `inventory.service.record_movement` - the same reuse-the-other-module's-
    service-function approach `breeding` already used for `livestock
    .create_animal`. Not yet live-tested - see "Phases 12-15" below.
  - `modules/employees/` - Employee HR profile (§27, Phase 13, this session),
    optionally linked to a login `User` via a nullable FK; employment-status
    lifecycle (`active/on_leave/suspended/terminated`) with an append-only
    history trail; lightweight `WorkShift` rota entries. Deliberately doesn't
    build payroll/attendance/leave - spec §27 itself lists those as later
    modules. Not yet live-tested.
  - `modules/assets/` - farm asset/equipment tracking (§15, Phase 14, this
    session): tractors, vehicles, milking equipment, etc., with straight-line
    depreciation computed at read time (never stored, so it can't drift
    stale) and an immutable maintenance/repair log that rolls up total cost.
    Logging a completed repair against an asset automatically moves it back
    to `in_use` from `under_maintenance`. Not yet live-tested.
  - `modules/accounts/` - customer self-service accounts (§16/§70, Phase 15,
    this session): reuses `identity.User` directly (a new nullable
    `customer_id` FK links it to the Phase 4 `Customer` CRM record) rather
    than building a parallel auth system - `DEFAULT_ROLE_GRANTS` already had
    an empty-permission `"Customer"` role waiting for exactly this since
    Phase 1. Registration reuses `find_or_create_by_contact`, so a guest-
    checkout customer who later registers gets their order history linked,
    not duplicated. Not yet live-tested.
  - `core/events.py` - minimal in-process pub/sub (`AnimalAcquired`, `AnimalSold`,
    `AnimalWeightUpdated`, `AnimalDeceased`, `HealthRecordCreated`,
    `VaccinationDue`, `HealthFollowUpDue`, `PregnancyConfirmed`, `BirthRecorded`,
    `MilkProductionRecorded`, `InventoryLow`, `InventoryExpiring`, `InventorySpend`,
    `OrderCreated`, `OrderPaid`, `OrderCancelled`, `OrderCompleted`,
    `ReservationExpired`, `PaymentInitiated`, `PaymentSucceeded`,
    `PaymentFailed`), a drop-in extraction point for RabbitMQ/Kafka
    later (§31)
  - `core/` - config, async SQLAlchemy session, password hashing, JWT helpers,
    `middleware.py` (request ID/structured logging, security headers,
    in-memory rate limiting - spec §29/§47, Phase 8)
  - `alembic/` - thirteen migrations (identity/farm schema; append-only audit
    trigger; livestock schema reusing the same append-only trigger;
    health_records; animal lineage columns + breeding/dairy/inventory schema;
    customers + commerce schema with partial unique indexes; payments +
    finance schema; notifications schema; cms schema + listing slug;
    procurement; employees; assets; customer-account linkage on `users`)
  - `tests/` - **85 tests covering Phases 1-11** (run against real
    Alembic-migrated databases - not SQLAlchemy's `create_all()` - see "bugs
    found" below for why that distinction matters), **plus 4 more test files
    for Phases 12-15 (this session, written but not yet executed - see
    "Phases 12-15" below)**: auth, cross-tenant isolation (independently checked
    at every module boundary), permission denial, animal lifecycle +
    weight/ADG, the sold-animal terminal-state guard, the full health
    follow-up lifecycle, the full breeding→pregnancy→delivery→offspring flow,
    dairy's duplicate-session and single-active-cycle guards, both branches of
    the inventory negative-stock guard, commerce's double-booking guards
    (including a real concurrency test), the full order lifecycle to
    `paid`/animal-`sold`, the full payment→signed-webhook→paid→finance-ledger→
    invoice flow, webhook idempotency-on-replay and bad-signature rejection,
    the finance-ledger/profitability-report consistency regression (see "bugs
    found" below), actual-vs-expected profitability, event-driven
    notifications with RBAC-derived recipients and preference opt-out, the
    scheduled-checks reservation-expiry flow, unauthenticated public browsing
    with published-only filtering, the public-listing field-allowlist (no
    cost data leaked), the listing-auto-deactivation regression (see "bugs
    found" below), a direct test that every append-only table actually
    rejects `UPDATE` at the DB level, and the middleware suite (request ID
    propagation, security headers, DB-checking readiness probe, and the
    login rate limiter actually blocking at its threshold - see "bugs found"
    below for the cross-test-pollution bug that testing it at full-suite
    scale caught) - all passing
- `docker-compose.yml` - Postgres + Redis + API with hot reload (dev; see
  the file's own comments on the non-root Dockerfile user vs. the bind-mount
  trade-off)
- `scripts/seed.py` - demo org with one user per standard role (§61)

## Run it

```bash
cd farmplatform
cp apps/api/.env.example apps/api/.env   # edit JWT_SECRET at minimum
docker compose up --build
# API on http://localhost:8000, docs at /docs
```

Seed demo data (after the stack is up):
```bash
docker compose exec api python -m scripts.seed
```

Run tests (needs a `farmdb_test` database):
```bash
cd apps/api
pip install -r requirements.txt
pytest
```

## Verified live (not just imports) - Phases 1-11 only, see "Phases 12-15" below for the rest
All of Phases 1-11 were run end-to-end against a real Postgres instance during
development - migrations, full auth/RBAC/tenant-isolation flows, animal
creation, weight/ADG calculation, movement, the sold/terminal-state guard,
health record creation with its timeline + health_status side effects,
due/overdue follow-up tracking, the full breeding→pregnancy-confirmation→
delivery→auto-created-offspring flow (with dam/sire lineage), dairy lactation
cycles + milk sessions with duplicate-day guards, the inventory ledger's
negative-stock guard, the full listing→reservation→order→paid flow (including
the double-booking guards), the full payment→signed-webhook→paid→
finance-ledger→invoice flow (including idempotent replay and bad-signature
rejection), the dashboard/profitability reports (with real feed+health cost
aggregation), event-driven notifications with RBAC-derived recipients, fully
unauthenticated public browsing (profile, listings, blog, testimonials, FAQs,
sitemap) with the published-only filter and the cost-field allowlist, and
the Phase 8 middleware (request ID propagation, security headers, a
DB-checking readiness probe, and the login rate limiter actually firing at
its threshold - confirmed with 12 real login attempts against a live server:
10 normal 401s, then 429/429) all confirmed working via live HTTP calls, with
the automated pytest suite (85 tests) passing on top.

Real bugs were found and fixed along the way:
- A passlib/bcrypt version incompatibility.
- Async SQLAlchemy relationship lazy-loading under Pydantic serialization.
- A chronology bug where the acquisition-time weight record used "now"
  instead of the acquisition date.
- A pytest-asyncio event-loop scope mismatch.
- **(Phase 4) `create_listing` relied solely on a DB partial-unique-index for
  duplicate prevention, with no application-level pre-check** - worked
  correctly against the real migrated database, but exposed a deeper problem:
- **(Phase 4) The test suite used `Base.metadata.create_all()` instead of real
  Alembic migrations.** This silently skipped every constraint expressed as
  raw SQL in a migration (all the append-only triggers, both partial unique
  indexes) rather than as a SQLAlchemy Column/Constraint object - meaning the
  duplicate-listing bug above passed in manual curl testing (real migrated DB)
  but would have passed pytest too, incorrectly, since pytest's schema was
  missing the constraint that was supposed to catch it. Fixed by having
  `tests/conftest.py` run real `alembic upgrade head`/`downgrade base` per
  test.
- **(Phase 5) Fire-and-forget event handlers that open their own DB session
  (`finance/handlers.py`) broke under pytest with "attached to a different
  loop."** Root cause was two-layered: the handler did
  `from app.core.database import AsyncSessionLocal`, binding the name at
  import time; when the test fixture later swapped the module's session
  factory to match the test's own event loop, the handler's already-bound
  reference didn't see the swap, because `from module import name` copies a
  reference rather than tracking the module attribute. Fixed by having the
  handler reference `db_module.AsyncSessionLocal` (module attribute lookup at
  call time) instead of importing the name directly - a small change, but the
  kind of gotcha that's invisible until something like a per-test event loop
  exposes it. In production this never manifests (the app has one event loop
  for its whole lifetime); it took writing the Phase 5 payment tests to
  surface it.
- **(Phase 6) The finance ledger and the profitability report disagreed on
  the same animal's cost.** The report pulled feed/health costs directly from
  their source tables (correct), but the ledger only ever recorded
  acquisition cost - `HealthRecordCreated` didn't carry `cost`, and inventory
  consumption never published anything Finance could subscribe to. A farm
  owner would have seen two different numbers for the same animal on two
  different screens. Fixed by enriching `HealthRecordCreated`'s payload and
  adding a new `InventorySpend` event (fired only for consumption/wastage/
  expired movements with a known unit cost), plus two new Finance handlers.
  Verified live and covered by a regression test
  (`test_reporting.py::test_health_and_feed_costs_flow_into_finance_ledger`).
- **(Phase 6) The fix for the bug above had its own bug.** The two new
  Finance handlers used a bare `AsyncSessionLocal()` instead of the
  `db_module.AsyncSessionLocal()` pattern the rest of that same file uses
  (the exact fix from the Phase 5 bug two entries up) - caused a `NameError`
  that the event bus's fire-and-forget error handling silently swallowed by
  design, so it only surfaced by reading the server log during live testing,
  not from an HTTP error. A reminder that a documented pattern in a file
  doesn't enforce itself on the next addition to that file - it still has to
  be applied deliberately each time.
- **(Phase 7) Nothing deactivated a `Listing` when its animal left `for_sale`.**
  Since Phase 4, `create_reservation` and `create_order` correctly transitioned
  the *animal's* status to `reserved`, but never touched the `Listing` row
  pointing at it. This was invisible until Phase 7 built the first thing that
  actually reads `is_active` listings for an external audience - the public
  catalog would have shown an animal as available when it was already
  reserved or sold. Found via this phase's own live testing (checked the
  public listings endpoint after reserving the demo animal, expected it to
  disappear, it didn't). Fixed with `_deactivate_active_listing_for_animal()`,
  called from both `create_reservation` and `create_order`; covered by two
  regression tests. A pre-existing gap from Phase 4, only surfaced once
  Phase 7 gave it an external consumer.
- **(Phase 7) `public/schemas.py`'s response models were missing
  `ConfigDict(from_attributes=True)`** on four of five schemas - worked fine
  wherever Pydantic serialized a plain dict, broke immediately
  (`ValidationError: Input should be a valid dictionary`) the moment
  `model_validate()` was called on an ORM object, which is every single public
  endpoint except listings (which happened to be hand-constructed dicts, not
  `model_validate()` calls, so it alone worked on the first try). Found via
  live testing - 4 of 6 public endpoints 500'd on first run. Fixed by adding
  the missing config to all four schemas; reverified live before writing the
  regression tests.
- **(Phase 8) Adding the rate limiter broke 44 unrelated tests two-thirds of
  the way through the full suite.** `auth_rate_limiter` is module-level state
  on the shared FastAPI `app` object, which pytest imports once for the whole
  session - every prior test's `register()`/`login()` calls accumulated hit
  counts, until a later test's legitimate auth attempt got a `429` instead of
  the `401`/`200` it expected. The isolated `test_middleware.py` run (5 tests)
  passed cleanly and gave no hint of this; only running the full 74-test suite
  surfaced it. Fixed by clearing the limiter's state in the `client` fixture
  itself (`tests/conftest.py`), the same place the DB-session and event-loop
  isolation fixes from earlier phases already live - this is exactly why that
  fixture keeps growing a "reset shared state" section rather than each
  concern inventing its own isolation mechanism.

Note on this sandbox specifically: the background `uvicorn`/`postgres`
processes get torn down between tool calls, so all live verification had to
happen within single atomic shell invocations (start server → run scenario →
inspect logs, all in one call) rather than a persistently running server.
Docker itself isn't available in this sandbox at all, so the Dockerfile and
CI workflow are reviewed-correct, not execution-verified - see "Known gaps."

## Known gaps (see docs/architecture.md for detail)
- **Customer accounts are now real** (Phase 15: `POST /public/{org_slug}/account/register`,
  `GET /api/v1/account/me`/`orders`/`orders/{id}`, reusing the same JWT login every
  staff user gets), **and payment/invoice history and password reset are
  now real too** (Phase 27 - see that section below). What's still
  missing from spec §16's own list: editing one's own profile from the
  portal (`/account/me` remains read-only).
- M-Pesa (Daraja) and Stripe providers are implemented to spec but **not
  verified against the real APIs** - this sandbox can't reach either network.
  The `MockProvider` exercises the identical integration code path
  (`payments/service.py`) and is fully live-tested; the provider adapters
  themselves aren't. Treat them as correctly-shaped starting points, not
  verified-working code, until tried against real (sandbox) credentials.
- Notifications are in-app only - no email/SMS/push channel is implemented.
- No real task scheduler - `POST /notifications/run-scheduled-checks` has
  real logic behind it but nothing calls it automatically yet.
- Reporting's inventory valuation (current stock × most recent purchase unit
  cost) is a rough approximation, not FIFO/weighted-average cost accounting.
- PDF/Excel report export isn't implemented - only CSV.
- **Rate limiting is per-process, in-memory.** Correct for this build's
  single-instance docker-compose topology; needs a Redis-backed limiter
  (Redis is already present) before horizontal scaling to multiple replicas.
- **No metrics/tracing stack.** Structured logging with request IDs is the
  foundation, not the full observability picture spec §47 asks for - no
  Prometheus/Grafana/OpenTelemetry.
- **The Dockerfile and CI workflow are unverified by actual execution** -
  Docker isn't available in this sandbox, and there's no network access to
  trigger a real GitHub Actions run. Both are internally consistent on
  review and their constituent pieces (migrations, pytest, the multi-stage
  build's stage references) were each independently verified, but that's a
  different claim from "this Dockerfile has actually been built."
- No staging/production environment - only local dev (`docker-compose.yml`)
  exists; no infrastructure-as-code for either.

## Frontend - real, but a slice, not the whole thing
`apps/web` is a working Next.js 14 (App Router, TypeScript, Tailwind)
frontend - not a mockup. It covers: login (real JWT auth with transparent
refresh-token rotation), the admin dashboard (`/reports/dashboard`), farm/
branch/location management, a livestock list + registration form + detail
view (tabs for Overview/Timeline/Health/Weights/Breeding/Dairy/Movements,
real forms, status-transition buttons), listings (create for any `for_sale`
animal, deactivate - active listings only, no history view), inventory
(item cards with live stock levels and low-stock highlighting, a movement
ledger with a form that correctly handles the unsigned-vs-signed quantity
distinction the backend requires), customers + orders (order detail with
full status history and its own status-transition buttons), finance
(Summary/Transactions/Profitability tabs, with a real transaction-entry
form), and a real, separate public storefront at `/shop/[orgSlug]` with no
login: browse listings with customer testimonials shown inline, a listing
detail page with a genuine guest-checkout form, order-status lookup gated
by the same email-ownership check the backend enforces, a blog, and
category-grouped FAQs - all consuming the CMS backend that's existed since
Phase 7 with zero prior frontend. `npm run build` compiles cleanly (21
routes), and every read and write call was checked against the live backend
in this session - including driving both an animal and an order through
real status sequences via the same buttons the UI renders, confirming the
backend still independently rejects an invalid transition if attempted
directly in both cases, confirming a listing created by staff produces the
same slug format the storefront's checkout depends on, confirming the
negative-stock guard fires through the exact request the movement form
sends, confirming the Profitability tab's real-sale math (90,000 − 40,000
acquisition = 50,000 profit) matches the backend exactly, walking a full
breeding lifecycle through to a real auto-created offspring animal with
lineage set, walking a full dairy cycle (start lactation → record milk →
dry off), walking the entire public storefront flow end to end - browse →
detail → guest checkout with a delivery address → order confirmation →
status lookup, plus confirming a published blog post/testimonial/FAQ
appears publicly while an unpublished draft does not - with no
authentication at any step, and moving an animal between two paddocks with
both the movement history and the animal's own current location updating
correctly. See `apps/web/README.md` for exactly what is and isn't covered,
and `docs/design-notes.md` for the visual design reasoning.

**What this is not:** apps/web's storefront now has real screens for
editing listings, customer accounts (register/login/profile/order history),
and banners (see the "Phase 26 - Frontend catches up" section below for
detail) - this paragraph originally said none of those existed, and that's
now out of date. Nothing here has been opened in an actual browser though
(no headless browser tool in this sandbox, and no `node_modules` installed
- no network access to `npm install` either) - build success and
API-contract matching were never verified live, and now neither has
TypeScript compilation itself. See the Phase 26 section for exactly what
that means for trust level.

## What's NOT in this delivery
Editing an existing listing, and banners (listing browse/detail/checkout,
blog, testimonials, and FAQs are all live in `/shop`; banners have a
working backend per Phase 7 but nothing renders them yet). Customer
self-service accounts (register/login/profile/order history) **are** now
implemented (Phase 15) at the API level, but `apps/web`'s public storefront
doesn't have UI for them yet - only the backend endpoints exist so far. The
API itself remains fully usable directly, or via its auto-generated docs at
`/docs`, for anything not yet covered by `apps/web`.

## If continuing this project
The backend roadmap (spec §64) is complete, plus Procurement/Employees/
Assets/Customer-Accounts (Phases 12-15), Rate-Limiting/Search/Bulk-Import/
Editing/PDF/QR/Org-Settings/FIFO-Costing/Observability/Deployment-Infra
(Phases 16-25), Email/Password-Reset (Phase 27), and the frontend now has
real screens for all of it including tenant registration, team/role
management, and public-site content management (Phases 26, 28, and 29 -
see the summary sections near the end of this file). What's genuinely
left: SMS delivery specifically (email now works - see Phase 27 - but
SMS/WhatsApp per spec §13 do not), live-testing the payment providers and
the SMTP email provider against real sandboxes, and - the most important
gap of all at this point - **actually running any of it**. Nothing added
from Phase 12 onward, backend or frontend, has been executed: no `pytest`
run, no `tsc` run, no browser opened. See the verification sections
throughout this document before trusting any of it the way Phases 1-11
are trusted.

## Phases 12-15 (this session) - Procurement, Employees, Assets, Customer Accounts
Four more bounded contexts from the original spec, added after the rest of
this README was written: **Procurement** (`modules/procurement` - suppliers,
purchase orders with a real requested→...→paid lifecycle, goods-received
posts real stock movements into the Phase 3 inventory ledger), **Employee
management** (`modules/employees` - HR profiles optionally linked to a login
user, employment-status lifecycle, lightweight work-shift rota),
**Farm asset management** (`modules/assets` - equipment/vehicles with
straight-line depreciation computed at read time and an immutable
maintenance log), and **Customer self-service accounts** (`modules/accounts`
- see the Phase 15 entry above). Full detail, including the specific design
reasoning and what's deliberately still out of scope for each, is in
`docs/architecture.md`'s Phase 12-15 entries.

**Verification status - read this before trusting these four the way
Phases 1-11 above are trusted.** Unlike everything above, Phases 12-15 were
written in a sandbox with **no network access and no Postgres or Python
packages installed** - they were `python -m py_compile`/AST-checked and
manually cross-referenced against the real signatures of every function
they call, but **never run against a live database**. The migration chain
(0001→0013) is a single verified-linear sequence with no branches, and
`tests/test_procurement.py`, `tests/test_employees.py`, `tests/test_assets.py`,
and `tests/test_customer_accounts.py` are written against the exact same
real-Alembic-migration test harness (`tests/conftest.py`) the other 85
tests use - but none of those four files has actually been executed. This
is the same "correctly-shaped, not proven by execution" distinction this
README already draws for the M-Pesa/Stripe providers and the Dockerfile;
it now also applies to these four modules specifically.

**Run this first, before anything else, to close that gap:**
```bash
cd apps/api
alembic upgrade head   # applies 0010-0013 for the first time against a real DB
pytest tests/test_procurement.py tests/test_employees.py tests/test_assets.py tests/test_customer_accounts.py -v
pytest   # then the full suite, to confirm nothing in Phases 1-11 regressed
```
If anything in those four files fails, it's a real bug to fix, not a
sandbox artifact - treat a failure there with exactly the same seriousness
this README's "bugs found" section treats every other phase's live-testing
discoveries, and please compare it against `docs/architecture.md`'s Phase
12-15 entries first, since the reasoning for *why* something was built a
particular way is written there, not just the "what."

## Phases 16-25 (this session, continued) - operational refinements + deployment infra
After Phases 12-15 above, the same session continued through the remaining
gap list: **Redis-backed rate limiting** (`core/middleware.RedisRateLimiter`,
opt-in via `RATE_LIMIT_BACKEND=redis`, in-memory stays the default so
nothing existing changed behavior), **edit-listing**
(`PATCH /api/v1/listings/{id}`), **global search**
(`GET /api/v1/search?q=` across animals/customers/orders/invoices/
suppliers/inventory/employees/assets), **bulk CSV import**
(`modules/bulk_import` - preview-then-confirm for customers/suppliers/
inventory items/livestock, per-row error reporting), **PDF export**
(invoice PDFs and a livestock report PDF, via a new `reportlab` dependency),
**QR codes** (`modules/livestock`'s `.svg` endpoint plus a new narrow public
QR-profile endpoint, via a new `qrcode` dependency), **organization
settings** (`GET/PATCH /api/v1/organization/settings` - configurable
currency/timezone/numbering prefixes/tax rate/default units, spec §56/§57/
§60; this also fixed a real bug where invoice tax was hard-coded to zero
regardless of any tax rate), **FIFO inventory costing**
(`GET /api/v1/inventory/valuation`, blended cost-basis tracking across
purchase batches - the most substantial item in this batch), **observability**
(`GET /metrics` in Prometheus format, plus opt-in OpenTelemetry tracing via
`OTEL_EXPORTER_OTLP_ENDPOINT`), and **deployment infrastructure**
(`infrastructure/terraform/` - full AWS ECS/RDS/ElastiCache/S3/ALB setup -
and `infrastructure/kubernetes/` as an alternative, plus the
`docs/deployment.md` spec §75 asks for, which didn't exist before this).

**Verification status is the same standing caveat as Phases 12-15, with one
addition.** Everything above except the infrastructure files was written
and `py_compile`-checked in the same no-network, no-Postgres sandbox - not
run live. The Terraform and Kubernetes files go one step further: they
can't even be `py_compile`-checked, since they aren't Python. Each `.tf`
file's resource references were manually cross-checked against every other
file's declared resource names (verified: every `aws_*.name.attribute`
reference used across `network.tf`/`data.tf`/`compute.tf`/`outputs.tf`
actually resolves to a resource declared somewhere in that set), and all
three Kubernetes YAML files were confirmed to parse as valid YAML - but
neither `terraform validate`/`plan` nor `kubectl apply --dry-run` has ever
been run against them, because this sandbox has neither binary and no cloud
credentials. `docs/deployment.md` explains exactly what to run yourself
before trusting either one.

**One dependency worth calling out specifically**: unlike reportlab/qrcode
(only imported inside the specific request handlers that use them, so a
missing package would only break those endpoints), `prometheus-client`
backs `PrometheusMiddleware`, which wraps every single request. If it
isn't installed in a real deployment, the *entire app* fails to start, not
just `/metrics`. It's a normal, small, pure-Python package with no unusual
install requirements - this is a low-risk dependency, but it's a different
kind of risk than the others added this session, and worth knowing before
assuming a missing package only affects one feature.

**Run this to verify Phases 16-25's application code** (the infrastructure
files have no equivalent - see `docs/deployment.md` instead):
```bash
cd apps/api
pytest tests/test_redis_rate_limiter.py tests/test_search.py tests/test_bulk_import.py \
       tests/test_public_qr.py tests/test_observability.py -v
pytest tests/test_commerce.py tests/test_finance.py tests/test_payments.py \
       tests/test_reporting.py tests/test_livestock.py tests/test_inventory.py \
       tests/test_auth_and_rbac.py -v   # touched by this batch - extra scrutiny warranted
pytest   # full suite, once more, to confirm nothing regressed across all 25 phases
```

## Phase 26 (this session, continued) - frontend catches up to Phases 12-25
Everything Phases 12-25 added to the backend now has a real screen in
`apps/web`, not just an API endpoint reachable via `/docs`:
**Procurement** (suppliers + purchase orders list, PO detail page with
status-transition buttons and history - mirrors the existing order-detail
pattern exactly), **Employees** (list + detail with status lifecycle and
work-shift scheduling), **Assets** (list + detail with maintenance log),
**Global search** (one page, results link to whichever entity types
actually have a detail route - search itself covers more types than
`apps/web` has detail pages for, and the search page says so rather than
producing broken links), **Organization settings** (currency/timezone/
numbering-prefix/tax-rate/units form), **Inventory valuation** (new report
page, linked from Inventory), **Bulk CSV import** (a shared
`BulkImportModal` component reused on Customers/Suppliers/Inventory, plus a
livestock-specific variant with a farm picker since that endpoint requires
one), **Edit-listing** (edit modal added to the existing Listings page,
preserving the SEO slug), **QR codes** (inline SVG preview + download
button on the animal detail page), **Invoice PDF download** (button on the
order detail page), and **Customer accounts** (register/login/profile+
orders under `/shop/[orgSlug]/account/*`, reusing the exact same JWT login
every staff member uses - no separate auth system, matching how the
backend itself was built in Phase 15), plus **banners now actually render**
on the shop homepage (Phase 7's backend had supported them since the
original build; nothing displayed them until now).

**Verification status - read this before trusting any of it.** This is a
materially weaker guarantee than even the backend's "written, not run"
caveat. The backend at least got `python -m py_compile` on every file. This
sandbox has **no `node_modules` installed and no network access to install
them** (`npm install` fails the same way `pip install` does) - meaning
**none of this frontend code has been type-checked, linted, or built even
once**. It was written by hand, matching the exact structure, naming, and
import patterns of the ~15 existing pages as closely as possible, and I
manually verified brace/paren/bracket balance across every new and edited
file plus cross-checked every field name used against the actual
`src/lib/types.ts` interfaces - but that is categorically different from a
compiler actually checking it. Treat this the way you'd treat code you
can see is well-organized and follows the right patterns, from someone who
has never once run it.

**Run this before trusting any of Phase 26**:
```bash
cd apps/web
npm install
npx tsc --noEmit     # will surface any real type errors - expect to find and fix some
npm run build
npm run dev           # then click through every new page by hand
```
One design choice worth knowing about: customer login (`/shop/[orgSlug]
/account/login`) and staff/admin login share the exact same token storage
in the browser (`localStorage`, same keys) - this mirrors the backend's own
design (a customer account is just an `identity.User` with a different
role, not a separate system), but it means logging in as a customer and an
admin in the *same browser* will overwrite one session with the other. Not
a bug - a direct consequence of the backend's Phase 15 design - but worth
knowing if you test both flows side by side.

## Phase 27 (this session, continued) - email channel + password reset
Closes the last documented "no email-sending capability exists anywhere in
this build" gap. New `modules/notifications/email/` follows the exact
provider-abstraction shape `modules/payments/providers/` already
established: an abstract `EmailProvider`, a `MockEmailProvider` that always
succeeds with no network call (what tests use, `EMAIL_PROVIDER_MODE=mock`
by default), and an `SMTPEmailProvider` using Python's stdlib `smtplib` -
no new dependency needed for this one. Every send, from either provider,
writes a durable `EmailOutbox` row (same "the record is independent of
which provider handled it" reasoning as `Payment`), visible to staff at
`GET /api/v1/notifications/email-outbox` and in `apps/web` on the new
Settings-page email log.

**Password reset** (spec §5): `PasswordResetToken` mirrors `RefreshToken`'s
hashed-token-at-rest pattern exactly - only a SHA-256 hash is ever stored,
tokens are single-use and expire in 60 minutes.
`POST /api/v1/auth/password-reset/request` is deliberately
enumeration-safe: the response is byte-identical whether or not the email
is registered, so this endpoint can never be used to check which emails
have accounts. `/reset-password` in `apps/web` handles both steps (request
form with no `?token=`, confirm form once one's present) in one page,
shared by staff and customer logins alike - the backend endpoint doesn't
distinguish between them, matching Phase 15's "a customer account is just
an ordinary User" design.

**Customer portal payment/invoice viewing** (spec §16, the one specific
item Phase 15's own write-up flagged as still missing): `GET /api/v1/account
/orders/{id}` now returns `invoice` and `payments`, not just status/items.
A new `apps/web` page (`/shop/[orgSlug]/account/orders/[orderId]`) displays
both; the account page's order list now links to it instead of showing
inert cards.

7 new backend tests (full reset flow, single-use enforcement,
enumeration-safety, the payment-confirmation email actually firing,
tenant isolation on the outbox, the new invoice/payment fields on order
detail) - same "written, `py_compile`-clean, never executed" status as
every other backend phase since 12.

## Phase 28 (this session) - frontend for Phase 27
`/reset-password` (shared request/confirm page), "Forgot your password?"
links on both the staff and customer login pages, the email send-log table
on `/admin/settings`, and `/shop/[orgSlug]/account/orders/[orderId]`
(invoice + payment history) with the account page's order list now linking
to it. Same verification caveat as Phase 26 - no `node_modules`, nothing
type-checked or built, brace/bracket balance and `types.ts` field names
checked by hand.

## Phase 29 (this session) - the gaps found by actually using the app
Triggered by a direct, simple question: "where does a tenant even
register? I land on a login page." That surfaced that Phase 26 had built
UI for every internal admin feature but missed the actual front door - a
multi-tenant platform with no sign-up page. A systematic follow-up audit
(every backend router's endpoints checked against every existing frontend
page) found several more: features with complete, working backend logic
and genuinely zero UI anywhere.

**Built**: `/register` (tenant + owner signup - the most consequential fix
here), `/admin/users` (invite staff, assign/revoke roles - required one
small backend addition, `GET /api/v1/users/roles`, since nothing ever
listed an org's roles despite them existing since Phase 1), `/admin/cms`
(farm profile/testimonials/blog/FAQs/banners - the public site has
displayed all of this since Phase 7, but nothing let a farm owner write
it), `/admin/reservations` (required a second small backend addition,
`GET /api/v1/reservations` - create/cancel/expire-stale existed, listing
didn't), `/admin/notifications` (inbox + category preferences),
`/admin/reports/profitability`, customer editing on `/admin/customers`,
and payment recording on `/admin/orders/[id]`.

Same verification status as Phases 26/28 throughout - see
`apps/web/README.md`'s Phase 29 section and `docs/architecture.md`'s
matching entry for full detail.

## Phase 30 - storefront, photos, inbox, hardening, and a contract audit

**Public site.** `/shop/[org]` was redesigned as a modern store: header with
search/cart, home (hero carousel, categories, featured deals, produce and
livestock rows, story, testimonials, blog, FAQs), a filterable `/store`,
`/about`, `/contact`, and a product page with a photo gallery and buy box. Shoppers
can now pay online with **M-Pesa** (STK push, polled until the callback confirms)
or settle offline with the farm. Card payments are not wired (see "Not done").

**New features.** Multiple photos per listing (stored in Postgres by default, or in a
Supabase Storage bucket with `STORAGE_BACKEND=supabase`), a contact-form inbox
(`/admin/inquiries`), an audit-log viewer (`/admin/audit`), edit screens for animals,
crops, assets, employees and suppliers, reservation creation / clearing expired
holds, livestock CSV/PDF export, and a permission-aware admin (menu items, pages and
write buttons follow the signed-in user's role). Migrations `0023`-`0027`.

**Hardening.** The public mock-payment webhook (a free "paid" order) is closed - mock
is development-only; public checkout/contact/payment are rate limited and use the real
client IP behind a load balancer (`TRUSTED_PROXY_COUNT`); abandoned guest orders expire
and re-list their animal; the platform audit middleware logs every platform write exactly
once; platform-admin passwords need 12+ characters; billing mutations need `users.manage`;
custom domains need DNS proof before they are routed or registered with Vercel and can no
longer be squatted; crop plantings have a plan cap; refresh-token rotation no longer logs
users out under parallel requests; Terraform keeps secrets in Secrets Manager.
See `docs/public-site-additions.md` for every setting.

**Contract audit.** `python scripts/contract_audit/run.py` compares every frontend API
call, response type, request body, query parameter, dropdown list, edit form, permission
code and platform screen with the backend's real routes and schemas (no server, database or
network needed; exits non-zero on a serious mismatch, so it suits CI). It found, among
others, the dashboard `undefined` bug, super-admin status changes using the wrong HTTP verb,
and lists silently truncated at the first page.

**Verification status.** Static checks (compilation, import resolution, model-vs-migration
drift, migration chain, the audit above, `tsc --noEmit`) and the pure-logic tests pass. The
database-backed tests added in this phase follow the existing harness but were written without
a Postgres to run them against - run `pytest` before relying on them. The storefront redesign and
photo upload (including Supabase) were exercised in a browser by the project owner; the screens added
afterwards (edit forms, audit viewer, reservations form, M-Pesa payment panel, permission-aware buttons)
have only been type-checked and audited against the backend, not clicked through.

**Not done.** Card (Stripe) checkout on the storefront needs Stripe.js plus exposing the
PaymentIntent `client_secret`. Analytics endpoints (`/health/due`, `/breeding/upcoming-deliveries`,
`/dairy/summary`, per-animal profitability) have no UI. The Terraform changes have never been
`plan`ned.

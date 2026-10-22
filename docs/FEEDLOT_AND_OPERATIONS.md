# Feedlot, worksheet import/export, receivables, training, flocks & fish

Added October 2026 to close the gaps between the system and the **Sahara Oasis Bulls WG Worksheet**
(1st production cycle) and the **"Purpose of the System"** deck. Everything is additive: 3 migrations
(0029-0031), 7 new modules, no existing table rewritten, all 347 pre-existing tests still pass.

## 1. What was added

| Module | Prefix | Purpose |
|---|---|---|
| `feedlot` | `/api/v1/feedlot` | Intake batches (with landed cost), sale batches (dispatch days), bulk **weigh days**, sale/cull/death exits, performance (ADG, % gain, days on farm, bands, market-ready), costing documents, profitability, **worksheet import/export** |
| `receivables` | `/api/v1/receivables` | Credit sales: charges, part payments, write-offs, customer statements, FIFO ageing, sales by salesperson |
| `finance` (extended) | `/api/v1/finance` | New optional `farm_id` + `activity` on transactions, 13 new categories (seed, fertilizer, chemicals, fuel, lease, insurance, crop/fodder/poultry/egg/fish/rabbit sales, training revenue), `GET /finance/profitability` by activity / sub-farm / category / month |
| `training` | `/api/v1/training` | Courses, sessions, enrolments (capacity, billing, cancellations), attendance, certificates (PDF), summary |
| `groups` | `/api/v1/groups` | Flocks / ponds / hutches managed by headcount: mortality, eggs, feed, weights, sales; hen-day %, mortality %, approx. FCR, margin |
| `fuel` | `/api/v1/fuel` | Fuel logs per asset, auto-posts a `fuel` expense, consumption per hour/km |
| `feedback` | `/api/v1/feedback`, public `/listings/{slug}/feedback` | Moderated product reviews (pending → approved), average rating |
| `livestock.photo` | `/api/v1/livestock/{id}/photo` | Validated, resized (900px), metadata-stripped animal photo |
| `livestock` (extended) | | New terminal status **`culled`** (also in the DB check constraint) |

New permissions: `feedlot.read/weigh/manage`, `training.read/manage`, `groups.read/record/manage`
(seeded into the catalog **and** granted to existing organisations' system roles by the migrations).
A Farm Worker can weigh animals and record flock data but cannot manage batches, costing or training.

## 2. The worksheet, sheet by sheet

| Worksheet sheet | In the system |
|---|---|
| `BATCH n` | Intake batch + each animal's weights per weigh day; ADG / % gain / interval gain computed |
| `Sales weight Batch n` | **Sale batch** (a dispatch day; mixes animals from several intake batches) + per-animal exit |
| `Bull Inventory register` | Derived: sold (`TAG...saleBatch`), culled, current stock |
| `SUMMARY ADG` | `GET /feedlot/performance` |
| `PROFITABILITY`, `Profitability per Bull` | `GET /feedlot/profitability` (per bull, sale batch, intake batch) |
| `CONCENTRATE` | costing document kind `recipe` |
| `HAY`, `SILAGE -BLENDED` | costing documents kind `enterprise_budget` (+ acre-weighted blend) |
| `TOTAL FEEDING COSTS` | kind `ration_plan` (stage-based standard feed cost, linked to the recipe/budgets) |
| `OPERATIONS COST` | kind `overhead_pool` |
| `LAND USE` | kind `land_use` |

### Import: `POST /api/v1/feedlot/worksheet/import?dry_run=true|false`
* Always preview first (`dry_run=true` saves nothing). Re-importing the same file changes nothing; a newer copy of the
  workbook appends only new weigh dates / sales / batches (idempotent).
* Dates: the manual file stores `m/d/yy`, which swapped day and month in places. Each ambiguous date is resolved by the
  sequence it sits in (and by delivery date); **every correction is listed** in the report.
* Historical imports do **not** publish `AnimalAcquired`/`AnimalSold` events, so they cannot back-date ledger entries or
  double-book income. New sales recorded through the API **do** post to the ledger/receivables.
* Respects the subscription's animal limit (the Free plan caps at 25: a 130-head import needs a bigger plan; the preview
  tells you, and nothing is written).

### Export: `GET /api/v1/feedlot/worksheet/export?as_of=YYYY-MM-DD`
Same 21 sheet names in the same order, same column order and headers, Arial + yellow header/TOTAL styling, thin borders,
and the same colour rules (>=300 kg green; interval gain >20 cyan; ADG <=0.2 red / 0.4-0.7 green / >0.7 cyan), with **live,
correct Excel formulas**. Added value sits *after* your sheets (`ANALYTICS - Batches`, `ANALYTICS - Sales`,
`ANALYTICS - Action list`, `DATA NOTES`) and in extra columns to the right (pre-sale shrink, price, amount).
Exports re-import to identical data (tested). "Append to the worksheet" = import the new weigh data, then export: the
BATCH sheets gain the new weigh-date columns automatically. (Editing an uploaded workbook *in place* is not supported:
inserting columns would not adjust its existing formulas.)

## 3. Corrections to the manual worksheet (the export does NOT reproduce these)
1. Dates are real dates shown `dd/mm/yyyy` (Batch 1 delivery was 12 Nov in the file; the real date is 11 Dec. Batch 4 read 1 Sep 2026; the real date is 9 Jan. The 11/5 weigh column read 5 Nov 2026 in every batch).
2. Day counts, bull counts and the as-at date are derived (no hand-typed `/228`, `/221/14`).
3. Total-row % WG divided by the entry weight of *all* bulls (15-42%); the true figures are 49-59%.
4. `BATCH 1!D12` pointed at row 4.
5. The profit table counted 104 bulls (formula stopped at sale batch 4); 108 distinct animals were sold.
6. Operations cost was a flat KES 13,758/bull regardless of days held; now allocated per bull-day (pool / actual bull-days).
7. Feeding cost was pasted numbers; now a live formula from the ration plan.
8. A culled bull (A084) had no loss line; culls/deaths are now charged as cost with no revenue.
9. Stale headers ("% WG as at 11/5/2026" over 28/7 data) are generated from the real date.

### Data-quality findings in your first-cycle workbook (fix at source if you keep using it)
* **A0116 is listed as sold twice** (sale batch 4 on 4/8 at 327 kg and sale batch 6 on 16/8 at 341 kg; same received date and entry weight) and appears twice in the register, so the manual profit counted its revenue and costs twice. The importer keeps the earliest and flags it.
* One **untagged** bull appears only in a sales sheet (sale batch 5, 13/8, 300 kg; received 9/1 = batch 4's delivery date; entry 184 kg). The BATCH 4 sheet lists 30 bulls (30 purchased) and every one of those tags is accounted for, so this is either a 31st animal or an animal whose tag was lost: please confirm. Imported as `TAGLESS-5-1`, so the system holds 31 animals for batch 4.
* The register shows 22 animals in current stock and hand-subtracts 2 (`=SUM(...)-2`); the system's active count (22) agrees with the register's list.
* A084 is "culled" with no date; the importer uses its last weigh date.
* Sale batch 4 animals sold on average ~9.8 kg lighter than their last on-farm weight (scale difference or transit shrink): worth tracking which scale was used.

## 4. Operational notes
* Run `pip install -r apps/api/requirements.txt` (adds `openpyxl==3.1.5`) and `alembic upgrade head`.
* Income reaches the ledger **when cash is received** (same basis as shop orders). A credit sale creates a customer charge;
  payments post income tagged with the sale's sub-farm/activity.
* Sales, group sales and fuel logs write their ledger/receivable entry in the **same transaction** as the record itself.
* Downgrading 0030 is refused if ledger rows already use the new categories (the ledger is append-only by design).
* Tests: `pytest` (~393 tests). By default each test clones a template database (~1 s/test). Set `TEST_FULL_MIGRATIONS=1`
  for the original method (downgrade to base + upgrade per test, ~10 s/test; also exercises every downgrade).
  `tests/fixtures/sahara_oasis_bulls_wg_sample.xlsx` is your real first-cycle workbook, used as a regression fixture. Delete it
  (and `test_feedlot_import.py` / the real-data export tests) if you do not want business data in the repository.

## 5. Screens (all features now have a UI)
| Screen | Where | Covers |
|---|---|---|
| Feedlot > Batches | `/admin/feedlot#batches` | Create intake batches (landed cost per head shown as you type), add animals with entry weights, create sale batches |
| Feedlot > Weigh day | `#weigh` | Bulk weigh-in, preview, **works offline** (section 6) |
| Feedlot > Sales & exits | `#sales` | Record a sale batch with a per-line preview (tag recognised? price? amount?), cash or credit sale, salesperson; cull / mortality |
| Feedlot > Costing | `#costing` | Structured editors for recipes, fodder budgets, ration plans (price from a fixed value, recipe, budget or blend), overhead pool, thresholds; land use as data |
| Feedlot > Worksheet | `#worksheet` | Preview / import / export the Bulls WG worksheet |
| Fuel | `/admin/fuel` | Log fills, consumption per machine, cost by activity |
| Reviews | `/admin/reviews` | Approve / reject customer reviews |
| Animal profile | `/admin/livestock/{id}` | Photo (camera or file; shrunk on the device before upload) |
| Shop listing | `/shop/{farm}/listings/{item}` | Customers read reviews and leave one (held for approval) |
| Receivables, Training, Flocks & Fish, Finance > By activity & farm | admin | as in section 1 |

## 6. Offline weigh-in (mobile)
Weighing happens at a crush pen with no signal, so the Weigh day screen works without one:
* **Saving offline.** With no connection (or if the server cannot be reached), "Save on this device" keeps the weigh day in the
  browser's local storage. The screen lists what is waiting, and sends it automatically when the connection returns (or
  with **Send now**). Sending the same weigh day twice is harmless (the server skips an animal already weighed that day).
* **Rejections are never silent.** If the server rejects a queued weigh day (for example a bad date) it stays in the list marked
  *Rejected* with the reason; it is not retried automatically and is not deleted until a person discards it.
  If the login has expired, sending stops with a clear message and nothing is lost.
* **Opening the app offline.** A service worker (`public/sw.js`, production builds only) saves the app's own files and the
  admin page shells. **Open the Weigh day page once while online** and it will open offline afterwards. Install it from the
  browser menu ("Add to Home screen"): it opens straight on Weigh day (`/admin/feedlot#weigh`). The worker never touches
  `/api/` or any other origin, so it cannot serve stale farm data or interfere with sign-in.
* **A lost connection is not a lost session.** Previously the app signed you out whenever its start-up "who am I?" call failed,
  which would have logged out anyone opening it with no signal. Now only a real 401/403 from the server signs you out; a
  network failure opens the app with the last known profile (kept on the device, wiped on logout; the server still checks every
  permission on every request).
* **Limits.** Tag validation happens when the weights are sent, so an unknown tag is reported then, not at the pen. Previews
  need a connection. Only weigh days are queued offline (sales, culls and batches need a connection). Browsers can clear local
  storage on request or in some private modes; the screen warns if the device cannot keep data. After a release, bump
  `VERSION` in `public/sw.js` to drop old caches.
* **Tests.** `npm run test:logic` (in `apps/web`) runs 48 checks: the queue's decisions (delivered / offline / rejected /
  login expired / server error / corrupt storage), the auth helpers, and the service worker rules (never intercepts the API,
  never caches redirects, errors or opaque responses). `tests/test_screen_payloads.py` sends the exact JSON the screens
  build to the real API, including a replay of an offline-queued weigh day.

## 7. Still open
* Scheduled daily alerts (vaccination / stock / reservation checks still run only when triggered by hand).
* Animal photos show on the animal's page only (not in lists, the QR profile or the shop).
* Intake and sale batches can be created from the screens but not edited afterwards (the API supports `PATCH` for both, and
  deleting an empty intake batch); costing documents can be created, edited and deleted from the screens.
* Slide 6 of the deck (Fodder Production) was blank; fodder production is covered through the fodder budgets.
* Crop plantings still have no irrigated flag (land use is stored as data).
* M-Pesa production hardening and the email case-sensitivity bug found in the first review are **separate and still open**.

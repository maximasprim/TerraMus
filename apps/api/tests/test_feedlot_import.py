"""End-to-end import of the real Sahara Oasis worksheet (tests/fixtures)."""
import pathlib

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio
FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sahara_oasis_bulls_wg_sample.xlsx"
H = lambda tok: {"Authorization": f"Bearer {tok}"}


async def _org(client, engine, name="Import Farm", email="imp@example.com"):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": name, "full_name": "Owner One", "email": email, "password": "supersecret123"})
    h = H(reg.json()["access_token"])
    await client.post("/api/v1/farms", json={"name": "Main"}, headers=h)
    async with engine.begin() as c:      # the Free plan caps animals at 25; a 130-head feedlot needs a bigger plan
        await c.execute(text("UPDATE subscription_tiers SET max_animals = NULL"))
        await c.execute(text("INSERT INTO subscription_tiers (id, slug, name, monthly_price_kes, max_users, max_animals, max_crop_plantings, is_active, created_at, updated_at) "
                             "SELECT gen_random_uuid(), 'x', 'x', 0, NULL, NULL, NULL, true, now(), now() WHERE false"))
    return h


async def _post(client, h, dry_run, path=FIXTURE):
    with open(path, "rb") as f:
        return await client.post(f"/api/v1/feedlot/worksheet/import?dry_run={'true' if dry_run else 'false'}", headers=h,
                                 files={"file": (path.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})


async def test_real_workbook_dry_run_commits_nothing_then_import_is_idempotent(client, engine):
    h = await _org(client, engine)
    dry = (await _post(client, h, True)).json()
    assert dry["ok"] and dry["dry_run"]
    assert dry["created"]["intake_batches"] == 5 and dry["created"]["animals"] == 131      # 130 tagged bulls + 1 untagged
    assert (await client.get("/api/v1/feedlot/intake-batches", headers=h)).json() == []     # nothing saved

    real = (await _post(client, h, False)).json()
    assert real["ok"], real["errors"]
    c = real["created"]
    assert (c["intake_batches"], c["sale_batches"], c["animals"], c["costing_documents"]) == (5, 6, 131, 8)
    assert c["sales"] == 108 and c["culls"] == 1               # 109 sale rows - 1 duplicate; A084 culled
    assert c["weight_records"] > 600
    rec = real["reconciliation"]
    assert rec["intake_animals"] == 131 and rec["sold"] == 108 and rec["culled"] == 1 and rec["active"] == 22
    assert rec["active"] == rec["register_current_stock_listed"]     # system and the worksheet's own register agree
    assert not rec["unaccounted"] and not rec["in_stock_and_sold"]
    assert len(real["date_corrections"]) >= 6
    codes = {w["code"] for w in real["warnings"]}
    assert "duplicate_sale" in codes                              # A0116 listed as sold twice in the worksheet
    dup = next(w for w in real["warnings"] if w["code"] == "duplicate_sale")
    assert "A0116" in dup["message"]

    again = (await _post(client, h, False)).json()                # idempotent: nothing new
    assert again["ok"] and again["created"].get("animals", 0) == 0 and again["created"].get("sales", 0) == 0
    assert again["created"].get("weight_records", 0) == 0 and again["created"].get("sale_batches", 0) == 0

    batches = {b["batch_number"]: b for b in (await client.get("/api/v1/feedlot/intake-batches", headers=h)).json()}
    assert batches[1]["landed_cost"] == 1584370 and batches[1]["head_registered"] == 30
    assert batches[4]["source"] == "Isiolo" and batches[4]["sex_class"] == "steer"
    assert str(batches[1]["delivered_on"]) == "2025-12-11"        # corrected from the worksheet's swapped 12 Nov


async def test_imported_numbers_match_worksheet_and_fix_its_errors(client, engine):
    h = await _org(client, engine, "Num Farm", "num@example.com")
    assert (await _post(client, h, False)).json()["ok"]
    pf = (await client.get("/api/v1/feedlot/profitability?as_of=2026-09-30", headers=h)).json()
    sb = {r["sale_batch"]: r for r in pf["by_sale_batch"]}
    assert sb[1]["head"] == 31 and sb[1]["total_weight_kg"] == 10979.0           # worksheet C11 / B11
    assert sb[1]["revenue"] == 3623070.0                                          # worksheet D11 (31 bulls x 330/kg)
    assert sb[2]["revenue"] == 3334080.0 and sb[4]["revenue"] == 3909760.0
    # the worksheet's sale batch 6 / A0116 double-count is not reproduced: 108 sold, not 109
    assert sum(r["head"] for r in pf["by_sale_batch"]) == 108
    perf = (await client.get("/api/v1/feedlot/performance?as_of=2026-07-28&intake_batch_id=" + (await client.get("/api/v1/feedlot/intake-batches", headers=h)).json()[0]["id"], headers=h)).json()
    active = [a for a in perf["animals"] if a["status"] == "active"]
    assert active and all(a["days_on_farm"] == 228 for a in active)               # Summary ADG: Batch 1 = 228 days
    # worksheet total-row % WG for batch 1 shows 18.7%; the true figure is ~54%
    gain = sum(a["overall_gain"] for a in active); entry = sum(a["entry_weight"] for a in active)
    assert 0.50 < gain / entry < 0.60

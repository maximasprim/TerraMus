"""The exact JSON the admin screens send (apps/web/src/app/admin/feedlot/*, fuel, reviews, groups ...).

TypeScript cannot check a payload against the backend's validators, so these tests send what the screens
build, byte for byte in shape: empty inputs omitted, numbers as numbers, money as strings.
"""
import io

import pytest
from PIL import Image

pytestmark = pytest.mark.asyncio


async def _org(client, email):
    reg = await client.post("/api/v1/auth/register", json={"organization_name": "Screen Farm", "full_name": "Owner One", "email": email, "password": "supersecret123"})
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    farm = (await client.post("/api/v1/farms", json={"name": "Segera"}, headers=h)).json()["id"]
    return h, farm


async def test_batches_screen_flow(client):
    h, farm = await _org(client, "sc1@example.com")
    # Batches tab > New intake batch (blank cost boxes become "0"; blank source is omitted)
    ib = await client.post("/api/v1/feedlot/intake-batches", headers=h, json={
        "delivered_on": "2026-01-09", "farm_id": farm, "sex_class": "steer", "head_purchased": 3,
        "purchase_cost": "150000", "transport_cost": "0", "other_fees": "0", "handlers_cost": "3000"})
    assert ib.status_code == 201, ib.text
    b = ib.json(); assert b["landed_cost_per_head"] == 51000.0
    # > Add animals (textarea lines parsed to numbers)
    r = await client.post(f"/api/v1/feedlot/intake-batches/{b['id']}/animals", headers=h, json={
        "animals": [{"animal_number": "S01", "entry_weight_kg": 210}, {"animal_number": "S02", "entry_weight_kg": 200.5}]})
    assert r.status_code == 201 and r.json()["created"] == 2
    # > New sale batch (price as a string, blank buyer omitted)
    sb = await client.post("/api/v1/feedlot/sale-batches", headers=h, json={"sold_on": "2026-07-01", "price_per_kg": "320"})
    assert sb.status_code == 201 and sb.json()["batch_number"] == 1
    # a sale batch with nothing but a date (price left blank) is also valid
    assert (await client.post("/api/v1/feedlot/sale-batches", headers=h, json={"sold_on": "2026-07-02"})).status_code == 201


async def test_sales_and_cull_screen_payloads(client):
    h, farm = await _org(client, "sc2@example.com")
    b = (await client.post("/api/v1/feedlot/intake-batches", headers=h, json={"delivered_on": "2026-01-09", "farm_id": farm, "head_purchased": 3, "purchase_cost": "90000"})).json()
    await client.post(f"/api/v1/feedlot/intake-batches/{b['id']}/animals", headers=h, json={"animals": [
        {"animal_number": t, "entry_weight_kg": 200} for t in ("S01", "S02", "S03")]})
    cust = (await client.post("/api/v1/customers", headers=h, json={"name": "Butcher Ltd"})).json()["id"]
    sb = (await client.post("/api/v1/feedlot/sale-batches", headers=h, json={"sold_on": "2026-07-01", "price_per_kg": "320"})).json()
    # Sales tab: line 1 uses the batch price (price_per_kg omitted), line 2 overrides it; customer + salesperson on every line
    res = (await client.post(f"/api/v1/feedlot/sale-batches/{sb['id']}/sales", headers=h, json={"entries": [
        {"animal_number": "S01", "exit_weight_kg": 324, "customer_id": cust, "salesperson": "Wanjiku"},
        {"animal_number": "S02", "exit_weight_kg": 331, "price_per_kg": 335, "customer_id": cust, "salesperson": "Wanjiku"}]})).json()
    assert res["sold"] == 2 and [r["amount"] for r in res["results"]] == [103680.0, 110885.0]
    assert (await client.get(f"/api/v1/receivables/customers/{cust}/statement", headers=h)).json()["balance"] == 214565.0
    # the screen blocks a missing price client-side; the server agrees it is invalid
    nb = (await client.post("/api/v1/feedlot/sale-batches", headers=h, json={"sold_on": "2026-07-02"})).json()
    bad = (await client.post(f"/api/v1/feedlot/sale-batches/{nb['id']}/sales", headers=h, json={"entries": [{"animal_number": "S03", "exit_weight_kg": 300}]})).json()
    assert bad["sold"] == 0 and bad["results"][0]["status"] == "error"
    # Cull card: optional weight and reason omitted when blank; animal chosen from the performance list
    perf = (await client.get("/api/v1/feedlot/performance", headers=h)).json()
    s03 = next(a for a in perf["animals"] if a["tag"] == "S03")
    assert {"animal_id", "tag", "intake_batch", "latest_weight", "status", "days_on_farm"} <= set(s03)      # fields the screen reads
    c = await client.post(f"/api/v1/feedlot/animals/{s03['animal_id']}/cull", headers=h, json={"exit_type": "died", "exit_date": "2026-05-01"})
    assert c.status_code == 201


async def test_costing_editors_emit_valid_documents_that_drive_profit(client):
    h, farm = await _org(client, "sc3@example.com")
    post = lambda body: client.post("/api/v1/feedlot/costing", headers=h, json=body)
    # RecipeEditor
    r = await post({"kind": "recipe", "name": "Concentrate", "data": {
        "ingredients": [{"name": "Maize germ", "quantity_kg": 472, "price_per_kg": 38}, {"name": "Rice polish", "quantity_kg": 157, "price_per_kg": 18}],
        "fixed_costs": [{"name": "Transport", "amount": 1500}]}})
    assert r.status_code == 201 and r.json()["computed"]["cost_per_kg"] == pytest.approx((472 * 38 + 157 * 18 + 1500) / 629, abs=1e-4)
    # BudgetEditor (hay: bales, kg per bale; amortised + repeated lines)
    bud = await post({"kind": "enterprise_budget", "name": "Hay (per acre)", "data": {
        "yield_per_year": 300, "yield_unit": "bale", "unit_weight_kg": 14, "assumptions": [],
        "lines": [{"item": "Land prep", "amount": 10000, "multiply_by": 1, "divide_by": 5}, {"item": "Harvest", "amount": 60, "multiply_by": 300, "divide_by": 1}]}})
    assert bud.status_code == 201 and bud.json()["computed"]["total_cost_per_year"] == 20000.0
    assert bud.json()["computed"]["cost_per_kg"] == pytest.approx(20000 / 300 / 14, abs=1e-4)
    # silage budget with acres, for the blend link
    sil = await post({"kind": "enterprise_budget", "name": "Napier (per acre)", "data": {"yield_per_year": 30000, "yield_unit": "kg", "acres": 10, "assumptions": [], "lines": [{"item": "All", "amount": 90000, "multiply_by": 1, "divide_by": 1}]}})
    assert sil.status_code == 201
    # RationEditor: hay from a budget, silage from a blend, concentrate from a recipe (manual map empty), exactly as built
    plan = await post({"kind": "ration_plan", "name": "Fattening", "data": {
        "stages": [{"label": "Stage 1", "days": 10, "feeds": {"silage": 5, "hay": 5, "concentrate": 1}}, {"days": 20, "feeds": {"silage": 6, "hay": 4, "concentrate": 2}}],
        "feed_costs": {}, "cost_links": {"hay": {"kind": "enterprise_budget", "name": "Hay (per acre)"}, "silage": {"kind": "blend", "names": ["Napier (per acre)"]},
                                         "concentrate": {"kind": "recipe", "name": "Concentrate"}}}})
    assert plan.status_code == 201, plan.text
    c = plan.json()["computed"]
    assert c["feed_costs"]["silage"] == pytest.approx(3.0) and c["total_days"] == 30 and c["total_cost"] > 0
    # ration with a manual price for every feed (the "A fixed price" mode)
    assert (await post({"kind": "ration_plan", "name": "Manual", "data": {"stages": [{"label": "", "days": 5, "feeds": {"silage": 1, "hay": 1, "concentrate": 1}}],
            "feed_costs": {"silage": 4, "hay": 16, "concentrate": 38}, "cost_links": {}}})).json()["computed"]["total_cost"] == 5 * 58
    # OverheadEditor, both sharing modes
    o = await post({"kind": "overhead_pool", "name": "Ops", "data": {"lines": [{"item": "Labour", "amount": 30000, "behaviour": "step"}], "heads": 10, "cycle_days": 100, "rate_mode": "bull_days"}})
    assert o.status_code == 201 and o.json()["computed"]["per_head"] == 3000.0
    assert (await post({"kind": "overhead_pool", "name": "Ops fixed", "data": {"lines": [{"item": "X", "amount": 1, "behaviour": "fixed"}], "heads": 0, "cycle_days": 0, "rate_mode": "fixed", "fixed_rate": 60}})).status_code == 201
    # SettingsEditor (only filled boxes are sent) and JSON editor (land use)
    s = await post({"kind": "settings", "name": "default", "data": {"market_ready_kg": 280, "day_offset": 1}})
    assert s.status_code == 201
    assert (await post({"kind": "land_use", "name": "Land use (acres)", "data": {"unit": "acres", "sites": ["Segera"], "rows": []}})).status_code == 201
    # editing = PATCH {name, data}; deleting = 204; a changed price flows through to the ration cost
    doc = next(d for d in (await client.get("/api/v1/feedlot/costing?kind=recipe", headers=h)).json())
    up = await client.patch(f"/api/v1/feedlot/costing/{doc['id']}", headers=h, json={"name": "Concentrate", "data": {"ingredients": [{"name": "Maize germ", "quantity_kg": 100, "price_per_kg": 50}], "fixed_costs": []}})
    assert up.json()["computed"]["cost_per_kg"] == 50.0
    plans = {p["name"]: p for p in (await client.get("/api/v1/feedlot/costing?kind=ration_plan", headers=h)).json()}
    assert plans["Fattening"]["computed"]["feed_costs"]["concentrate"] == 50.0           # followed the edited recipe
    assert (await client.delete(f"/api/v1/feedlot/costing/{plans['Manual']['id']}", headers=h)).status_code == 204
    # the settings threshold the user saved is honoured by the performance report
    assert (await client.get("/api/v1/feedlot/performance", headers=h)).json()["settings"]["market_ready_kg"] == 280


async def test_offline_queue_replay_is_idempotent_and_matches_screen_payload(client):
    h, farm = await _org(client, "sc4@example.com")
    b = (await client.post("/api/v1/feedlot/intake-batches", headers=h, json={"delivered_on": "2026-01-09", "farm_id": farm, "head_purchased": 2, "purchase_cost": "100000"})).json()
    await client.post(f"/api/v1/feedlot/intake-batches/{b['id']}/animals", headers=h, json={"animals": [{"animal_number": "Q01", "entry_weight_kg": 200}, {"animal_number": "Q02", "entry_weight_kg": 210}]})
    # exactly what syncQueue() posts for a queued item (scale_label/notes omitted when absent; no dry_run key)
    queued = {"weighed_on": "2026-03-01", "scale_label": "Crush pen", "entries": [{"animal_number": "Q01", "weight_kg": 250}, {"animal_number": "Q02", "weight_kg": 261.5}]}
    first = (await client.post("/api/v1/feedlot/weigh-days", headers=h, json=queued)).json()
    assert first["recorded"] == 2
    # the first request timed out on the way back, so the device sends it AGAIN: nothing is double-recorded
    replay = (await client.post("/api/v1/feedlot/weigh-days", headers=h, json=queued)).json()
    assert replay["recorded"] == 0 and {r["status"] for r in replay["results"]} == {"already_recorded"}
    perf = (await client.get("/api/v1/feedlot/performance?as_of=2026-03-02", headers=h)).json()
    assert {a["tag"]: len(a["intervals"]) for a in perf["animals"]} == {"Q01": 1, "Q02": 1}           # one interval each, not two
    # a weigh day queued with a typo is rejected cleanly (4xx) rather than silently dropped
    assert (await client.post("/api/v1/feedlot/weigh-days", headers=h, json={"weighed_on": "not-a-date", "entries": [{"animal_number": "Q01", "weight_kg": 250}]})).status_code == 422


async def test_fuel_review_photo_and_group_screen_payloads(client):
    h, farm = await _org(client, "sc5@example.com")
    a = (await client.post("/api/v1/assets", headers=h, json={"name": "Tractor", "asset_type": "tractor"})).json()
    # Fuel modal with the optional boxes left blank (cost blank -> 0; everything else omitted)
    assert (await client.post("/api/v1/fuel", headers=h, json={"asset_id": a["id"], "log_date": "2026-05-01", "litres": 40, "cost": 0, "post_to_finance": True})).status_code == 201
    assert (await client.post("/api/v1/fuel", headers=h, json={"asset_id": a["id"], "log_date": "2026-05-02", "litres": 20, "cost": 3400, "meter_reading": 1010,
            "purpose": "ploughing", "activity": "crops", "farm_id": farm, "driver": "Otieno", "post_to_finance": False})).status_code == 201
    assert len((await client.get("/api/v1/fuel?start_date=2026-04-01&end_date=2026-05-31", headers=h)).json()) == 2
    # Animal photo: the screen shrinks first (<= 1600 px JPEG) and PUTs the field named "file"
    an = (await client.post("/api/v1/livestock", headers=h, json={"farm_id": farm, "animal_number": "P-1", "species": "cattle", "sex": "male", "acquisition_date": "2024-01-01", "acquisition_method": "purchased"})).json()
    buf = io.BytesIO(); Image.new("RGB", (1600, 1200), (90, 120, 60)).save(buf, "JPEG", quality=85)
    up = await client.put(f"/api/v1/livestock/{an['id']}/photo", headers=h, files={"file": ("animal.jpg", buf.getvalue(), "image/jpeg")})
    assert up.status_code == 200
    assert (await client.get(f"/api/v1/livestock/{an['id']}/photo", headers=h)).status_code == 200
    # a phone-sized original that the screen could NOT shrink (unsupported browser) is still accepted up to 5 MB
    big = io.BytesIO(); Image.new("RGB", (4000, 3000), (10, 20, 30)).save(big, "JPEG", quality=95)
    assert len(big.getvalue()) < 5 * 1024 * 1024
    assert (await client.put(f"/api/v1/livestock/{an['id']}/photo", headers=h, files={"file": ("big.jpg", big.getvalue(), "image/jpeg")})).status_code == 200
    # Groups modal: blank optional fields omitted; weight sample + sale shapes from the record dialog
    g = (await client.post("/api/v1/groups", headers=h, json={"code": "L-9", "name": "Layers", "species": "poultry", "start_date": "2026-03-01", "initial_count": 100, "acquisition_cost": "0"})).json()
    rec = lambda **kw: client.post(f"/api/v1/groups/{g['id']}/records", headers=h, json=kw)
    assert (await rec(record_type="weight_sample", record_date="2026-04-01", quantity=10, avg_weight_kg=1.7)).status_code == 201
    assert (await rec(record_type="sale", record_date="2026-04-02", quantity=300, unit="eggs", value=9000, product="eggs")).status_code == 201
    assert (await rec(record_type="mortality", record_date="2026-04-03", quantity=2)).status_code == 201

import pytest

pytestmark = pytest.mark.asyncio


async def _org(client, name="Feedlot Farm", email="fl@example.com"):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": name, "full_name": "Owner One", "email": email, "password": "supersecret123"})
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    farm = (await client.post("/api/v1/farms", json={"name": "Main"}, headers=h)).json()
    return h, farm["id"]


async def _batch_with_animals(client, h, farm_id, tags=("A01", "A02", "A03")):
    b = (await client.post("/api/v1/feedlot/intake-batches", headers=h, json={
        "delivered_on": "2025-12-11", "farm_id": farm_id, "head_purchased": 3, "purchase_cost": "150000",
        "transport_cost": "3000", "other_fees": "1500", "handlers_cost": "1500"})).json()
    r = await client.post(f"/api/v1/feedlot/intake-batches/{b['id']}/animals", headers=h, json={
        "animals": [{"animal_number": t, "entry_weight_kg": w} for t, w in zip(tags, (210, 200, 190))]})
    assert r.status_code == 201, r.text
    return b


async def test_intake_batch_numbering_cost_and_duplicate(client):
    h, farm = await _org(client)
    b = (await client.post("/api/v1/feedlot/intake-batches", headers=h, json={
        "delivered_on": "2025-12-11", "farm_id": farm, "head_purchased": 30, "purchase_cost": "1500000",
        "transport_cost": "30000", "other_fees": "15000", "handlers_cost": "15000"})).json()
    assert b["batch_number"] == 1 and b["name"] == "BATCH 1"
    assert b["landed_cost"] == 1560000 and b["landed_cost_per_head"] == 52000.0
    b2 = (await client.post("/api/v1/feedlot/intake-batches", headers=h, json={"delivered_on": "2025-12-18"})).json()
    assert b2["batch_number"] == 2
    dup = await client.post("/api/v1/feedlot/intake-batches", headers=h, json={"delivered_on": "2025-12-18", "batch_number": 2})
    assert dup.status_code == 409


async def test_register_animals_sets_landed_cost_entry_weight_and_link(client):
    h, farm = await _org(client)
    b = await _batch_with_animals(client, h, farm)
    animals = (await client.get("/api/v1/livestock", headers=h)).json()
    items = animals["items"] if isinstance(animals, dict) else animals
    a1 = next(a for a in items if a["animal_number"] == "A01")
    assert float(a1["acquisition_cost"]) == 52000.0 and float(a1["current_weight"]) == 210.0
    batches = (await client.get("/api/v1/feedlot/intake-batches", headers=h)).json()
    assert batches[0]["head_registered"] == 3 and batches[0]["head_active"] == 3
    again = await client.post(f"/api/v1/feedlot/intake-batches/{b['id']}/animals", headers=h, json={
        "animals": [{"animal_number": "A01", "entry_weight_kg": 210}]})
    assert again.json()["results"][0]["status"] == "exists"      # idempotent, no duplicate


async def test_bulk_weigh_day_records_flags_and_never_regresses_current_weight(client):
    h, farm = await _org(client)
    await _batch_with_animals(client, h, farm)
    r = (await client.post("/api/v1/feedlot/weigh-days", headers=h, json={
        "weighed_on": "2026-01-14", "scale_label": "Pen scale",
        "entries": [{"animal_number": "A01", "weight_kg": 220}, {"animal_number": "A02", "weight_kg": 209},
                    {"animal_number": "NOPE", "weight_kg": 150}]})).json()
    assert r["recorded"] == 2
    assert {x["status"] for x in r["results"]} == {"recorded", "unknown_animal"}
    assert len(r["problems"]) == 1
    # same day again -> not double-recorded
    again = (await client.post("/api/v1/feedlot/weigh-days", headers=h, json={
        "weighed_on": "2026-01-14", "entries": [{"animal_number": "A01", "weight_kg": 999}]})).json()
    assert again["results"][0]["status"] == "already_recorded" and again["recorded"] == 0
    # a later weigh, then a BACK-DATED weigh must not overwrite the newer current_weight
    await client.post("/api/v1/feedlot/weigh-days", headers=h, json={
        "weighed_on": "2026-03-01", "entries": [{"animal_number": "A01", "weight_kg": 260}]})
    await client.post("/api/v1/feedlot/weigh-days", headers=h, json={
        "weighed_on": "2026-02-01", "entries": [{"animal_number": "A01", "weight_kg": 240}]})
    items = (await client.get("/api/v1/livestock", headers=h)).json()
    items = items["items"] if isinstance(items, dict) else items
    assert float(next(a for a in items if a["animal_number"] == "A01")["current_weight"]) == 260.0
    # implausible jump is flagged (still recorded) and dry-run changes nothing
    dry = (await client.post("/api/v1/feedlot/weigh-days", headers=h, json={
        "weighed_on": "2026-03-02", "dry_run": True, "entries": [{"animal_number": "A01", "weight_kg": 400}]})).json()
    assert dry["results"][0]["status"] == "would_record" and dry["results"][0]["flags"] and dry["session_id"] is None
    sessions = (await client.get("/api/v1/feedlot/weigh-days", headers=h)).json()
    assert [s["weighed_on"] for s in sessions][:1] == ["2026-03-01"] or len(sessions) >= 3


async def test_performance_uses_worksheet_conventions(client):
    h, farm = await _org(client)
    await _batch_with_animals(client, h, farm)
    await client.post("/api/v1/feedlot/weigh-days", headers=h, json={
        "weighed_on": "2026-07-28", "entries": [{"animal_number": "A01", "weight_kg": 349}]})
    p = (await client.get("/api/v1/feedlot/performance?as_of=2026-07-28", headers=h)).json()
    a01 = next(a for a in p["animals"] if a["tag"] == "A01")
    assert a01["days_on_farm"] == 228 and a01["overall_gain"] == 139.0
    assert a01["adg"] == pytest.approx(139 / 228, abs=1e-4) and a01["market_ready"] is True
    assert p["summary"]["market_ready"] == 1 and p["summary"]["head"] == 3
    assert set(p["summary"]["no_recent_weight"]) == {"A02", "A03"}


async def test_sale_cull_and_profitability(client):
    h, farm = await _org(client)
    await _batch_with_animals(client, h, farm)
    for d, w in (("2026-06-01", 330), ):
        await client.post("/api/v1/feedlot/weigh-days", headers=h, json={
            "weighed_on": d, "entries": [{"animal_number": "A01", "weight_kg": w}]})
    # costing: ration + overhead pool
    plan = await client.post("/api/v1/feedlot/costing", headers=h, json={
        "kind": "ration_plan", "name": "Fattening", "data": {
            "stages": [{"label": "all", "days": 100, "feeds": {"hay": 10}}], "feed_costs": {"hay": 10}}})
    assert plan.status_code == 201 and plan.json()["computed"]["total_cost"] == 10000.0
    await client.post("/api/v1/feedlot/costing", headers=h, json={
        "kind": "overhead_pool", "name": "Ops", "data": {"lines": [{"item": "Labour", "amount": 30000}]}})
    sb = (await client.post("/api/v1/feedlot/sale-batches", headers=h, json={
        "sold_on": "2026-06-22", "price_per_kg": "330"})).json()
    assert sb["batch_number"] == 1
    sold = (await client.post(f"/api/v1/feedlot/sale-batches/{sb['id']}/sales", headers=h, json={
        "entries": [{"animal_number": "A01", "exit_weight_kg": 324}, {"animal_number": "ZZZ", "exit_weight_kg": 300}]})).json()
    assert sold["sold"] == 1 and sold["results"][0]["amount"] == 106920.0
    assert sold["results"][1]["status"] == "unknown_animal"
    # selling the same animal twice is refused
    items = (await client.get("/api/v1/livestock", headers=h)).json()
    items = items["items"] if isinstance(items, dict) else items
    a01 = next(a for a in items if a["animal_number"] == "A01")
    assert a01["status"] == "sold"
    twice = await client.post(f"/api/v1/feedlot/animals/{a01['id']}/sale", headers=h, json={
        "exit_date": "2026-06-23", "exit_weight_kg": 300, "price_per_kg": 300})
    assert twice.status_code == 409
    # cull A02: full loss, counted in the batch loss rate
    a02 = next(a for a in items if a["animal_number"] == "A02")
    c = await client.post(f"/api/v1/feedlot/animals/{a02['id']}/cull", headers=h, json={
        "exit_type": "culled", "exit_date": "2026-03-01", "reason": "lame"})
    assert c.status_code == 201
    pf = (await client.get("/api/v1/feedlot/profitability?as_of=2026-07-28", headers=h)).json()
    t = pf["totals"]
    assert t["head_realised"] == 2 and t["revenue"] == 106920.0
    assert pf["by_intake_batch"][0]["head_culled"] == 1 and pf["by_intake_batch"][0]["loss_rate_pct"] == 33.3
    # overhead pool is fully allocated across bull-days (never over/under-charged)
    allocated = sum(a["ops_cost"] for a in pf["animals"])
    assert allocated == pytest.approx(30000, abs=1.0)
    culled_row = next(a for a in pf["animals"] if a["tag"] == "A02")
    assert culled_row["profit"] < 0 and culled_row["revenue"] == 0
    assert pf["by_sale_batch"][0]["head"] == 1


async def test_costing_validation_and_unique_names(client):
    h, _ = await _org(client)
    bad = await client.post("/api/v1/feedlot/costing", headers=h, json={
        "kind": "ration_plan", "name": "x", "data": {"stages": [{"feeds": {}}]}})
    assert bad.status_code == 422
    ok = await client.post("/api/v1/feedlot/costing", headers=h, json={
        "kind": "recipe", "name": "Conc", "data": {"ingredients": [{"quantity_kg": 100, "price_per_kg": 30}]}})
    assert ok.status_code == 201 and ok.json()["computed"]["cost_per_kg"] == 30.0
    assert (await client.post("/api/v1/feedlot/costing", headers=h, json={
        "kind": "recipe", "name": "Conc", "data": {}})).status_code == 409


async def test_tenant_isolation_and_auth(client):
    h1, farm1 = await _org(client, "Org One", "one@example.com")
    h2, _ = await _org(client, "Org Two", "two@example.com")
    b = await _batch_with_animals(client, h1, farm1)
    assert (await client.get("/api/v1/feedlot/intake-batches", headers=h2)).json() == []
    assert (await client.patch(f"/api/v1/feedlot/intake-batches/{b['id']}", headers=h2, json={"name": "hax"})).status_code == 404
    assert (await client.get("/api/v1/feedlot/performance", headers=h2)).json()["summary"]["head"] == 0
    assert (await client.get("/api/v1/feedlot/intake-batches")).status_code in (401, 403)
    # batches with animals can't be deleted
    assert (await client.delete(f"/api/v1/feedlot/intake-batches/{b['id']}", headers=h1)).status_code == 409

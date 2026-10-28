"""Profitability report must include sales made OUTSIDE the web shop (recorded in the
feedlot module, by hand or via worksheet import), with a per-animal breakdown of what
was used and what came back or was lost. Existing web-order behaviour is covered by
test_reporting.py and must not change."""
import pytest
from sqlalchemy import update

from app.core import database as db_module
from app.modules.feedlot.models import FeedlotExit

pytestmark = pytest.mark.asyncio


async def _org(client, name="Report Feedlot Farm", email="rf@example.com"):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": name, "full_name": "Owner", "email": email, "password": "supersecret123"})
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    farm = (await client.post("/api/v1/farms", json={"name": "Main"}, headers=h)).json()
    return h, farm["id"]


async def _scenario(client):
    """A01 sold @330/kg (324 kg), A02 culled, A03 still on the farm; ration plan + overhead pool set."""
    h, farm = await _org(client)
    b = (await client.post("/api/v1/feedlot/intake-batches", headers=h, json={
        "delivered_on": "2025-12-11", "farm_id": farm, "head_purchased": 3, "purchase_cost": "150000",
        "transport_cost": "3000", "other_fees": "1500", "handlers_cost": "1500"})).json()
    await client.post(f"/api/v1/feedlot/intake-batches/{b['id']}/animals", headers=h, json={
        "animals": [{"animal_number": t, "entry_weight_kg": w} for t, w in zip(("A01", "A02", "A03"), (210, 200, 190))]})
    await client.post("/api/v1/feedlot/weigh-days", headers=h, json={
        "weighed_on": "2026-06-01", "entries": [{"animal_number": "A01", "weight_kg": 330},
                                                {"animal_number": "A03", "weight_kg": 300}]})
    await client.post("/api/v1/feedlot/costing", headers=h, json={
        "kind": "ration_plan", "name": "Fattening", "data": {
            "stages": [{"label": "all", "days": 100, "feeds": {"hay": 10}}], "feed_costs": {"hay": 10}}})
    await client.post("/api/v1/feedlot/costing", headers=h, json={
        "kind": "overhead_pool", "name": "Ops", "data": {"lines": [{"item": "Labour", "amount": 30000}]}})
    sb = (await client.post("/api/v1/feedlot/sale-batches", headers=h, json={
        "sold_on": "2026-06-22", "price_per_kg": "330"})).json()
    await client.post(f"/api/v1/feedlot/sale-batches/{sb['id']}/sales", headers=h, json={
        "entries": [{"animal_number": "A01", "exit_weight_kg": 324}]})
    items = (await client.get("/api/v1/livestock", headers=h)).json()
    items = items["items"] if isinstance(items, dict) else items
    ids = {a["animal_number"]: a["id"] for a in items}
    await client.post(f"/api/v1/feedlot/animals/{ids['A02']}/cull", headers=h, json={
        "exit_type": "culled", "exit_date": "2026-03-01", "reason": "lame"})
    return h, ids


def _row(report, tag):
    return next(a for a in report["animals"] if a["animal_number"] == tag)


async def test_feedlot_sale_shows_actual_sale_price_and_profit(client):
    h, ids = await _scenario(client)
    report = (await client.get("/api/v1/reports/profitability", headers=h)).json()
    a01 = _row(report, "A01")
    assert float(a01["sale_price"]) == 106920.0            # 324 kg x KES 330 - same as the worksheet
    assert a01["is_actual"] is True and a01["sale_channel"] == "feedlot" and a01["outcome"] == "sold"
    assert float(a01["price_per_kg"]) == pytest.approx(330.0)
    assert float(a01["acquisition_cost"]) == 52000.0       # landed cost per head
    assert float(a01["feed_cost"]) > 0 and float(a01["overhead_cost"]) > 0
    # the two screens must agree on the numbers
    fl = (await client.get("/api/v1/feedlot/profitability?as_of=2099-01-01", headers=h)).json()
    fl_a01 = next(a for a in fl["animals"] if a["tag"] == "A01")
    assert float(a01["profit"]) == pytest.approx(fl_a01["profit"], abs=0.02)
    assert float(a01["total_investment"]) == pytest.approx(fl_a01["total_cost"], abs=0.02)


async def test_culled_animal_is_a_realised_loss_with_no_revenue(client):
    h, ids = await _scenario(client)
    report = (await client.get("/api/v1/reports/profitability", headers=h)).json()
    a02 = _row(report, "A02")
    assert a02["outcome"] == "culled" and a02["is_actual"] is True and a02["sale_price"] is None
    assert float(a02["profit"]) == pytest.approx(-float(a02["total_investment"]))


async def test_active_feedlot_animal_is_a_projection_not_an_actual(client):
    h, ids = await _scenario(client)
    report = (await client.get("/api/v1/reports/profitability", headers=h)).json()
    a03 = _row(report, "A03")
    assert a03["outcome"] == "active" and a03["is_actual"] is False and a03["sale_price"] is None
    assert a03["estimate_source"] == "feedlot_projection" and a03["expected_sale_price"] is not None


async def test_totals_split_sold_culled_and_active(client):
    h, ids = await _scenario(client)
    t = (await client.get("/api/v1/reports/profitability", headers=h)).json()["totals"]
    assert (t["head_sold"], t["head_culled"], t["head_died"], t["head_active"]) == (1, 1, 0, 1)
    assert float(t["realised_revenue"]) == 106920.0
    assert float(t["realised_profit"]) == pytest.approx(float(t["realised_revenue"]) - float(t["realised_cost"]))
    assert float(t["loss_from_culled_died"]) < 0
    assert [c["channel"] for c in t["by_channel"]] == ["feedlot"] and t["by_channel"][0]["head"] == 1


async def test_sold_without_a_recorded_price_is_flagged_not_shown_as_a_loss(client):
    h, ids = await _scenario(client)
    async with db_module.AsyncSessionLocal() as s:       # simulate an import where the price was never found
        await s.execute(update(FeedlotExit).values(amount=0).where(FeedlotExit.exit_type == "sold"))
        await s.commit()
    a01 = _row((await client.get("/api/v1/reports/profitability", headers=h)).json(), "A01")
    assert a01["outcome"] == "sold" and a01["sale_price"] is None and a01["profit"] is None
    assert a01["is_actual"] is False and a01["estimate_source"] == "sale_price_missing"
    br = (await client.get(f"/api/v1/reports/profitability/animals/{ids['A01']}", headers=h)).json()
    assert br["returns"][0]["category"] == "no_revenue"


async def test_breakdown_lists_what_was_used_and_what_came_back(client):
    h, ids = await _scenario(client)
    br = (await client.get(f"/api/v1/reports/profitability/animals/{ids['A01']}", headers=h)).json()
    assert [c["category"] for c in br["costs"]] == ["purchase", "feed", "health", "overhead"]
    assert sum(float(c["amount"]) for c in br["costs"]) == pytest.approx(float(br["summary"]["total_investment"]))
    assert br["returns"][0]["category"] == "sale" and float(br["returns"][0]["amount"]) == 106920.0
    assert "324" in br["returns"][0]["note"] and "330" in br["returns"][0]["note"]
    assert float(br["net"]) == pytest.approx(float(br["total_return"]) - float(br["total_cost"]), abs=0.02)
    assert br["net_is_actual"] is True


async def test_breakdown_for_culled_and_active_animals(client):
    h, ids = await _scenario(client)
    cull = (await client.get(f"/api/v1/reports/profitability/animals/{ids['A02']}", headers=h)).json()
    assert cull["returns"][0]["category"] == "no_revenue" and float(cull["total_return"]) == 0.0
    assert cull["reason"] == "lame" and float(cull["net"]) < 0
    live = (await client.get(f"/api/v1/reports/profitability/animals/{ids['A03']}", headers=h)).json()
    assert live["returns"][0]["category"] == "projected_sale" and live["net_is_actual"] is False


async def test_non_feedlot_animal_is_unchanged(client):
    h, farm = await _org(client, "Plain Farm", "plain@example.com")
    loc_farm = farm
    branch = (await client.post(f"/api/v1/farms/{loc_farm}/branches", json={"name": "B"}, headers=h)).json()
    loc = (await client.post(f"/api/v1/farms/{loc_farm}/branches/{branch['id']}/locations",
                             json={"name": "P1", "location_type": "paddock"}, headers=h)).json()
    animal = (await client.post("/api/v1/livestock", headers=h, json={
        "farm_id": farm, "location_id": loc["id"], "animal_number": "PLAIN-1", "species": "cattle", "sex": "female",
        "acquisition_date": "2024-01-01", "acquisition_method": "purchased", "acquisition_cost": "40000"})).json()
    row = _row((await client.get("/api/v1/reports/profitability", headers=h)).json(), "PLAIN-1")
    assert row["total_investment"] == "40000.00" and float(row["overhead_cost"]) == 0.0
    assert row["sale_channel"] is None and row["outcome"] == "active" and row["profit"] is None
    br = (await client.get(f"/api/v1/reports/profitability/animals/{animal['id']}", headers=h)).json()
    assert [c["category"] for c in br["costs"]] == ["purchase", "feed", "health"]   # no feedlot overhead line


async def test_breakdown_is_tenant_isolated_and_permissioned(client):
    h1, ids = await _scenario(client)
    h2, _ = await _org(client, "Other Farm", "other@example.com")
    assert (await client.get(f"/api/v1/reports/profitability/animals/{ids['A01']}", headers=h2)).status_code == 404
    assert (await client.get(f"/api/v1/reports/profitability/animals/{ids['A01']}")).status_code in (401, 403)
    other = (await client.get("/api/v1/reports/profitability", headers=h2)).json()
    assert other["animals"] == [] and other["totals"]["head_sold"] == 0

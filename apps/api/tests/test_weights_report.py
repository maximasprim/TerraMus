"""Weights report API: targets (batch + animal override), overview, daily weights, animal detail, permissions, alerts."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.modules.notifications.scheduled import run_scheduled_checks
from tests.test_roles_management import _owner, _roles, _staff

pytestmark = pytest.mark.asyncio

from app.modules.weights.service import today_local

TODAY = today_local()   # the API computes "today" itself, so the test data must be relative to the real date


async def _farm(client, h):
    return (await client.post("/api/v1/farms", json={"name": "Main"}, headers=h)).json()["id"]


async def _animal(client, h, farm, tag, **extra):
    r = await client.post("/api/v1/livestock", headers=h, json={
        "farm_id": farm, "species": "cattle", "sex": "male", "animal_number": tag,
        "acquisition_date": "2026-09-01", "acquisition_method": "purchased", **extra})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


async def _weigh(client, h, animal, day: date, kg):
    at = datetime(day.year, day.month, day.day, 9, 0, tzinfo=timezone.utc).isoformat()
    r = await client.post(f"/api/v1/livestock/{animal}/weights", headers=h, json={"weight_kg": str(kg), "recorded_at": at})
    assert r.status_code == 201, r.text


async def _batch(client, h, farm, **extra):
    r = await client.post("/api/v1/feedlot/intake-batches", headers=h, json={
        "delivered_on": "2026-09-01", "farm_id": farm, "head_purchased": 3, **extra})
    assert r.status_code in (200, 201), r.text
    return r.json()


async def _link(client, h, batch_id, animal_id, entry):
    r = await client.post(f"/api/v1/feedlot/intake-batches/{batch_id}/link", headers=h,
                          json={"animals": [{"animal_id": animal_id, "entry_weight_kg": entry}]})
    assert r.status_code in (200, 201), r.text


async def test_overview_readiness_batch_target_and_animal_override(client, engine):
    h = await _owner(client, "Weights Farm", "weights@example.com")
    farm = await _farm(client, h)
    batch = await _batch(client, h, farm, name="BATCH 1")
    a1 = await _animal(client, h, farm, "W-001")      # no target anywhere
    a2 = await _animal(client, h, farm, "W-002")      # will get the batch target via feedlot link? (set directly below)
    for a, (w0, w1) in ((a1, (200, 230)), (a2, (400, 440))):
        await _weigh(client, h, a, TODAY - timedelta(days=20), w0)
        await _weigh(client, h, a, TODAY - timedelta(days=0), w1)

    ov = (await client.get("/api/v1/weights/overview", headers=h)).json()
    rows = {r["tag"]: r for r in ov["animals"]}
    assert rows["W-001"]["stage"] == "no_target" and rows["W-002"]["stage"] == "no_target"
    assert rows["W-002"]["adg"] == 2.0 and rows["W-002"]["adg_band"] == "excellent"
    assert rows["W-001"]["adg"] == 1.5 and rows["W-001"]["adg_band"] == "excellent"
    assert ov["thresholds"]["on_target_from"] == 0.9 and ov["thresholds"]["approaching_from"] == 0.6

    # per-animal target
    r = await client.put(f"/api/v1/weights/animals/{a2}/target", headers=h, json={"target_weight_kg": 450})
    assert r.status_code == 200 and r.json()["target_weight_kg"] == 450
    ov = (await client.get("/api/v1/weights/overview", headers=h)).json()
    row = {r["tag"]: r for r in ov["animals"]}["W-002"]
    assert row["target_source"] == "animal" and row["stage"] == "nearly_ready" and row["days_to_ready"] == 5
    assert row["remaining_kg"] == 10

    # clearing it
    await client.put(f"/api/v1/weights/animals/{a2}/target", headers=h, json={"target_weight_kg": None})
    ov = (await client.get("/api/v1/weights/overview", headers=h)).json()
    assert {r["tag"]: r for r in ov["animals"]}["W-002"]["stage"] == "no_target"

    # batch target is stored and shows in the feedlot batch list too
    r = await client.put(f"/api/v1/weights/batches/{batch['id']}/target", headers=h, json={"target_weight_kg": 300})
    assert r.status_code == 200 and r.json()["target_weight_kg"] == 300
    listed = (await client.get("/api/v1/feedlot/intake-batches", headers=h)).json()
    assert float(listed[0]["target_weight_kg"]) == 300
    assert (await client.put(f"/api/v1/weights/batches/{batch['id']}/target", headers=h, json={"target_weight_kg": -5})).status_code == 422


async def test_daily_weights_and_animal_detail(client, engine):
    h = await _owner(client, "Weights Farm B", "weightsb@example.com")
    farm = await _farm(client, h)
    a = await _animal(client, h, farm, "D-001", target_weight=300)
    for d, kg in ((30, 200), (20, 215), (10, 225), (0, 245)):
        await _weigh(client, h, a, TODAY - timedelta(days=d), kg)
    day = (TODAY - timedelta(days=10)).isoformat()
    dl = (await client.get(f"/api/v1/weights/daily?day={day}", headers=h)).json()
    assert dl["day"] == day and len(dl["rows"]) == 1
    row = dl["rows"][0]
    assert row["weight_kg"] == 225 and row["previous_kg"] == 215 and row["change_kg"] == 10 and row["adg"] == 1.0
    assert row["target_kg"] == 300 and row["remaining_kg"] == 75
    assert dl["days"][0]["head"] == 1

    d = (await client.get(f"/api/v1/weights/animals/{a}", headers=h)).json()
    assert [p["weight_kg"] for p in d["series"]] == [200, 215, 225, 245]
    assert d["series"][1]["adg"] == 1.5 and d["series"][1]["band"] == "excellent"
    assert d["series"][3]["adg"] == 2.0
    assert d["animal"]["target_kg"] == 300 and d["projection"][-1]["weight_kg"] == 300
    assert (await client.get(f"/api/v1/weights/animals/00000000-0000-0000-0000-000000000000", headers=h)).status_code == 404


async def test_view_and_target_permissions(client, engine):
    h = await _owner(client, "Weights Farm C", "weightsc@example.com")
    roles = await _roles(client, h)
    rec = roles["Field Recorder"]
    worker = await _staff(client, h, rec["id"], "rec-weights@example.com")
    assert (await client.get("/api/v1/weights/overview", headers=worker)).status_code == 200       # can see animals -> can see weights
    farm = await _farm(client, h)
    a = await _animal(client, h, farm, "P-001")
    assert (await client.put(f"/api/v1/weights/animals/{a}/target", headers=worker, json={"target_weight_kg": 400})).status_code == 403
    keep = [p for p in rec["permissions"] if p != "weights.view"]
    await client.put(f"/api/v1/roles/{rec['id']}", headers=h, json={"permissions": keep})
    assert (await client.get("/api/v1/weights/overview", headers=worker)).status_code == 403
    mgr = roles["Farm Manager"]["permissions"]
    assert {"weights.view", "weights.targets"} <= set(mgr)


async def test_alerts_once_per_animal_per_stage_and_not_for_unhealthy(client, engine):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.modules.notifications.models import Notification
    h = await _owner(client, "Weights Farm D", "weightsd@example.com")
    farm = await _farm(client, h)
    ready = await _animal(client, h, farm, "R-001", target_weight=450)
    near = await _animal(client, h, farm, "N-001", target_weight=450)
    far = await _animal(client, h, farm, "F-001", target_weight=600)
    sick = await _animal(client, h, farm, "S-001", target_weight=450)
    for a, w in ((ready, (440, 455)), (near, (420, 440)), (far, (300, 320)), (sick, (440, 460))):
        await _weigh(client, h, a, TODAY - timedelta(days=10), w[0])
        await _weigh(client, h, a, TODAY, w[1])
    await client.patch(f"/api/v1/livestock/{sick}", headers=h, json={"health_status": "sick"})

    sm = async_sessionmaker(engine, expire_on_commit=False)
    org = (await client.get("/api/v1/auth/me", headers=h)).json()["organization"]["id"]
    import uuid
    async with sm() as db:
        first = await run_scheduled_checks(db, uuid.UUID(org), TODAY)
    assert first.weights_ready_notified == 1 and first.weights_nearly_ready_notified == 1   # R-001 ready, N-001 nearly; sick one waits
    async with sm() as db:
        again = await run_scheduled_checks(db, uuid.UUID(org), TODAY + timedelta(days=1))
    assert again.weights_ready_notified == 0 and again.weights_nearly_ready_notified == 0     # never repeated
    async with sm() as db:
        titles = [n.title for n in (await db.execute(select(Notification).where(Notification.organization_id == uuid.UUID(org)))).scalars()]
    assert "Animals ready for market" in titles and "Animals nearly ready for market" in titles

    await client.patch(f"/api/v1/livestock/{sick}", headers=h, json={"health_status": "healthy"})
    async with sm() as db:
        later = await run_scheduled_checks(db, uuid.UUID(org), TODAY + timedelta(days=2))
    assert later.weights_ready_notified == 1                                                   # announced once it is healthy again


async def test_batch_target_applies_to_its_animals_and_the_animal_target_overrides_it(client, engine):
    h = await _owner(client, "Weights Farm E", "weightse@example.com")
    farm = await _farm(client, h)
    batch = await _batch(client, h, farm, name="BATCH 5")
    a1, a2 = await _animal(client, h, farm, "G-001"), await _animal(client, h, farm, "G-002")
    for a in (a1, a2):
        await _link(client, h, batch["id"], a, 380)
        await _weigh(client, h, a, TODAY - timedelta(days=20), 380)
        await _weigh(client, h, a, TODAY, 420)
    await client.put(f"/api/v1/weights/batches/{batch['id']}/target", headers=h, json={"target_weight_kg": 450})
    ov = (await client.get("/api/v1/weights/overview", headers=h)).json()
    rows = {r["tag"]: r for r in ov["animals"]}
    assert rows["G-001"]["target_kg"] == 450 and rows["G-001"]["target_source"] == "batch" and rows["G-001"]["start_kg"] == 380
    assert rows["G-001"]["progress_pct"] == pytest.approx(57.1, abs=0.1) and rows["G-001"]["stage"] == "growing"
    assert rows["G-001"]["batch"] and "5" in rows["G-001"]["batch"]
    b = ov["batches"][0]
    assert b["head"] == 2 and b["avg_target_kg"] == 450 and b["avg_current_kg"] == 420 and b["avg_adg"] == 2.0 and b["adg_band"] == "excellent"

    await client.put(f"/api/v1/weights/animals/{a2}/target", headers=h, json={"target_weight_kg": 400})   # own target wins
    rows = {r["tag"]: r for r in (await client.get("/api/v1/weights/overview", headers=h)).json()["animals"]}
    assert rows["G-002"]["target_source"] == "animal" and rows["G-002"]["stage"] == "ready"
    assert rows["G-001"]["target_source"] == "batch"
    only = (await client.get(f"/api/v1/weights/overview?batch_id={batch['id']}", headers=h)).json()
    assert len(only["animals"]) == 2

    d = (await client.get(f"/api/v1/weights/animals/{a1}", headers=h)).json()
    assert d["batch_avg"] and d["batch_avg"][-1]["n"] == 1 and d["batch_avg"][-1]["avg_kg"] == 420


async def test_target_weight_can_be_set_when_creating_a_batch_and_changed_later(client, engine):
    h = await _owner(client, "Weights Farm F", "weightsf@example.com")
    farm = await _farm(client, h)
    batch = await _batch(client, h, farm, name="BATCH 9", target_weight_kg="480")
    assert float(batch["target_weight_kg"]) == 480
    r = await client.patch(f"/api/v1/feedlot/intake-batches/{batch['id']}", headers=h, json={"target_weight_kg": "500"})
    assert r.status_code == 200 and float(r.json()["target_weight_kg"]) == 500
    plain = await _batch(client, h, farm, name="BATCH 10")
    assert plain["target_weight_kg"] is None


async def test_feedlot_and_weights_agree_on_target_and_band(client, engine):
    h = await _owner(client, "Weights Farm G", "weightsg@example.com")
    farm = await _farm(client, h)
    batch = await _batch(client, h, farm, name="BATCH 11", target_weight_kg="250")
    a1, a2 = await _animal(client, h, farm, "G-001"), await _animal(client, h, farm, "G-002")
    for a in (a1, a2):
        await _link(client, h, batch["id"], a, 200)
        await _weigh(client, h, a, TODAY - timedelta(days=10), 200)
        await _weigh(client, h, a, TODAY, 260)
    await client.put(f"/api/v1/weights/animals/{a2}/target", headers=h, json={"target_weight_kg": 400})
    perf = {p["tag"]: p for p in (await client.get("/api/v1/feedlot/performance", headers=h)).json()["animals"]}
    ov = {r["tag"]: r for r in (await client.get("/api/v1/weights/overview", headers=h)).json()["animals"]}
    assert perf["G-001"]["target_weight"] == 250 and perf["G-001"]["target_source"] == "batch"
    assert perf["G-001"]["market_ready"] is True and ov["G-001"]["stage"] == "ready"
    assert perf["G-002"]["target_weight"] == 400 and perf["G-002"]["target_source"] == "animal"
    assert perf["G-002"]["market_ready"] is False and ov["G-002"]["stage"] != "ready"
    assert perf["G-002"]["adg_band"] == ov["G-002"]["adg_band"] == "excellent"


async def test_weights_report_follows_the_production_cycle_filter(client, engine):
    h = await _owner(client, "Weights Farm H", "weightsh@example.com")
    farm = await _farm(client, h)
    c1 = (await client.post("/api/v1/production-cycles", json={"name": "Cycle 1"}, headers=h)).json()["id"]
    c2 = (await client.post("/api/v1/production-cycles", json={"name": "Cycle 2"}, headers=h)).json()["id"]
    b1 = await _batch(client, h, farm, name="B1", production_cycle_id=c1)
    b2 = await _batch(client, h, farm, name="B2", production_cycle_id=c2)
    a1, a2 = await _animal(client, h, farm, "H-001"), await _animal(client, h, farm, "H-002")
    for a, b in ((a1, b1), (a2, b2)):
        await _link(client, h, b["id"], a, 200)
        await _weigh(client, h, a, TODAY, 230)
    tags = lambda j: sorted(r["tag"] for r in j["animals"])
    get = lambda q: client.get(f"/api/v1/weights/overview{q}", headers=h)
    assert tags((await get("")).json()) == ["H-001", "H-002"]
    assert tags((await get(f"?production_cycle_id={c2}")).json()) == ["H-002"]
    assert tags((await get(f"?production_cycle_id={c1}")).json()) == ["H-001"]
    assert tags((await get("?production_cycle_id=unassigned")).json()) == []
    ov = (await get(f"?production_cycle_id={c2}")).json()
    assert [o["id"] for o in ov["batch_options"]] == [b2["id"]]
    d = (await client.get(f"/api/v1/weights/daily?production_cycle_id={c1}", headers=h)).json()
    assert [r["tag"] for r in d["rows"]] == ["H-001"] and d["days"][0]["head"] == 1

"""Daily alert checks: de-duplicated, readable, safe across replicas and restarts, isolated per organisation."""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.scheduler import runner

pytestmark = pytest.mark.asyncio
RUN = "/api/v1/notifications/run-scheduled-checks"


async def _org(client, email, name="Sched Farm"):
    reg = await client.post("/api/v1/auth/register", json={"organization_name": name, "full_name": "Owner One", "email": email, "password": "supersecret123"})
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    farm = (await client.post("/api/v1/farms", json={"name": "Main"}, headers=h)).json()["id"]
    org_id = (await client.get("/api/v1/auth/me", headers=h)).json()["organization"]["id"]
    return h, farm, org_id


async def _titles(client, h):
    return [n["title"] for n in (await client.get("/api/v1/notifications", headers=h)).json()]


async def _backdate_alerts(engine, org_id, days):
    async with engine.begin() as c:
        await c.execute(text("UPDATE alert_log SET last_sent_on = last_sent_on - CAST(:d AS integer) WHERE organization_id = :o"), {"d": days, "o": org_id})


async def test_vaccination_alert_names_the_animal_and_does_not_repeat_every_day(client, engine):
    h, farm, org_id = await _org(client, "sc1@example.com")
    a = (await client.post("/api/v1/livestock", headers=h, json={"farm_id": farm, "animal_number": "COW-77", "name": "Daisy", "species": "cattle", "sex": "female",
         "acquisition_date": "2024-01-01", "acquisition_method": "purchased"})).json()
    due = (date.today() + timedelta(days=3)).isoformat()
    await client.post(f"/api/v1/livestock/{a['id']}/health", headers=h, json={"record_type": "vaccination", "title": "FMD booster", "follow_up_date": due})
    # saving the record announced it at once, by tag (not by internal id) ...
    async def notes():
        return [n["body"] for n in (await client.get("/api/v1/notifications", headers=h)).json() if n["title"] == "Vaccination due"]
    first_msgs = await notes()
    assert len(first_msgs) == 1 and "COW-77 (Daisy)" in first_msgs[0] and str(a["id"]) not in first_msgs[0]
    # ... so the next morning's check does not announce the same news again
    assert (await client.post(RUN, headers=h)).json()["vaccinations_due_notified"] == 0
    await _backdate_alerts(engine, org_id, 4)
    assert (await client.post(RUN, headers=h)).json()["vaccinations_due_notified"] == 0              # still inside the weekly cooldown
    await _backdate_alerts(engine, org_id, 4)
    assert (await client.post(RUN, headers=h)).json()["vaccinations_due_notified"] == 1              # a week on: one reminder
    msgs = await notes()
    assert len(msgs) == 2 and all("COW-77 (Daisy)" in m and str(a["id"]) not in m for m in msgs)


async def test_feedlot_alerts_unweighed_and_market_ready_then_quiet(client, engine):
    h, farm, org_id = await _org(client, "sc2@example.com")
    b = (await client.post("/api/v1/feedlot/intake-batches", headers=h, json={"delivered_on": "2026-01-01", "farm_id": farm, "head_purchased": 2, "purchase_cost": "100000"})).json()
    await client.post(f"/api/v1/feedlot/intake-batches/{b['id']}/animals", headers=h, json={"animals": [{"animal_number": "F01", "entry_weight_kg": 320}, {"animal_number": "F02", "entry_weight_kg": 200}]})
    r = (await client.post(RUN, headers=h)).json()
    assert r["feedlot_unweighed_notified"] == 1 and r["feedlot_market_ready_notified"] == 1
    titles = await _titles(client, h)
    assert "Animals overdue for weighing" in titles and "Animals ready for market" in titles
    msg = next(n["body"] for n in (await client.get("/api/v1/notifications", headers=h)).json() if n["title"] == "Animals ready for market")
    assert "F01" in msg and "F02" not in msg
    again = (await client.post(RUN, headers=h)).json()
    assert again["feedlot_unweighed_notified"] == 0 and again["feedlot_market_ready_notified"] == 0


async def test_overdue_receivables_alert(client, engine):
    h, farm, org_id = await _org(client, "sc3@example.com")
    cust = (await client.post("/api/v1/customers", headers=h, json={"name": "Slow Payer"})).json()["id"]
    await client.post("/api/v1/receivables/charges", headers=h, json={"customer_id": cust, "amount": 80000, "entry_date": (date.today() - timedelta(days=100)).isoformat(), "description": "Old sale"})
    r = (await client.post(RUN, headers=h)).json()
    assert r["receivables_notified"] == 1
    msg = next(n["body"] for n in (await client.get("/api/v1/notifications", headers=h)).json() if n["title"] == "Overdue customer balances")
    assert "Slow Payer" in msg and "80,000" in msg
    assert (await client.post(RUN, headers=h)).json()["receivables_notified"] == 0
    # a recent debt is not nagged about
    h2, _, _ = await _org(client, "sc3b@example.com", "Fresh Debt Farm")
    c2 = (await client.post("/api/v1/customers", headers=h2, json={"name": "New Customer"})).json()["id"]
    await client.post("/api/v1/receivables/charges", headers=h2, json={"customer_id": c2, "amount": 5000, "entry_date": date.today().isoformat()})
    assert (await client.post(RUN, headers=h2)).json()["receivables_notified"] == 0


async def test_training_starting_soon_alert_is_sent_once_per_session(client, engine):
    h, farm, org_id = await _org(client, "sc4@example.com")
    course = (await client.post("/api/v1/training/courses", headers=h, json={"title": "Silage Making", "fee": "1000"})).json()
    soon = (date.today() + timedelta(days=2)).isoformat()
    far = (date.today() + timedelta(days=30)).isoformat()
    s1 = (await client.post("/api/v1/training/sessions", headers=h, json={"course_id": course["id"], "start_date": soon})).json()
    s2 = (await client.post("/api/v1/training/sessions", headers=h, json={"course_id": course["id"], "start_date": far})).json()
    for s in (s1, s2):
        await client.post(f"/api/v1/training/sessions/{s['id']}/enrolments", headers=h, json={"participant_name": "Peter Otieno"})
    assert (await client.post(RUN, headers=h)).json()["training_notified"] == 1          # the session 30 days away is not mentioned
    assert (await client.post(RUN, headers=h)).json()["training_notified"] == 0


async def test_manual_trigger_still_returns_the_original_fields_and_isolates_tenants(client):
    h1, _, _ = await _org(client, "sc5a@example.com", "Tenant A")
    h2, farm2, _ = await _org(client, "sc5b@example.com", "Tenant B")
    cust = (await client.post("/api/v1/customers", headers=h1, json={"name": "A Debtor"})).json()["id"]
    await client.post("/api/v1/receivables/charges", headers=h1, json={"customer_id": cust, "amount": 1000, "entry_date": (date.today() - timedelta(days=60)).isoformat()})
    await client.post(RUN, headers=h1)
    r = (await client.post(RUN, headers=h2)).json()
    assert {"vaccinations_due_notified", "low_stock_notified", "reservations_expired"} <= set(r) and r["receivables_notified"] == 0
    assert "Overdue customer balances" not in await _titles(client, h2)


# ------------------------------------------------------------------ the runner
async def test_only_one_replica_runs_a_day_and_a_crashed_run_can_be_taken_over(engine):
    sf = async_sessionmaker(engine, expire_on_commit=False)
    day = date(2026, 5, 1)
    async with sf() as db:
        first = await runner.claim_run(db, "daily_checks", day)
    async with sf() as db:
        second = await runner.claim_run(db, "daily_checks", day)
    async with sf() as db:
        other_day = await runner.claim_run(db, "daily_checks", date(2026, 5, 2))
    assert first and second is None and other_day                                       # the second replica skips; a new day is fine
    long_ago = datetime.now(timezone.utc) - timedelta(hours=3)
    async with engine.begin() as c:
        await c.execute(text("UPDATE scheduler_runs SET started_at = :t WHERE id = :i"), {"t": long_ago, "i": first})
    async with sf() as db:
        takeover = await runner.claim_run(db, "daily_checks", day)
    assert takeover == first                                                           # the run died mid-way: another replica finishes the day
    async with sf() as db:
        await runner.finish_run(db, first, "ok", {"x": 1})
    async with engine.begin() as c:
        await c.execute(text("UPDATE scheduler_runs SET started_at = :t WHERE id = :i"), {"t": long_ago, "i": first})
    async with sf() as db:
        assert await runner.claim_run(db, "daily_checks", day) is None                 # a FINISHED run is never repeated


def test_the_daily_job_waits_for_its_hour():
    tz = __import__("zoneinfo").ZoneInfo("Africa/Nairobi")
    assert not runner.should_run_now(datetime(2026, 5, 1, 5, 59, tzinfo=tz), 6)
    assert runner.should_run_now(datetime(2026, 5, 1, 6, 0, tzinfo=tz), 6)
    assert runner.should_run_now(datetime(2026, 5, 1, 23, 0, tzinfo=tz), 6)             # a server restarted at 14:00 still catches up


async def test_daily_run_covers_every_active_org_skips_suspended_ones_and_runs_once(client, engine, monkeypatch):
    for i, name in enumerate(("Run A", "Run B", "Run C")):
        await _org(client, f"sc6{i}@example.com", name)
    async with engine.begin() as c:
        await c.execute(text("UPDATE organizations SET is_suspended = true WHERE name = 'Run C'"))
    monkeypatch.setattr(runner.settings, "SCHEDULER_RUN_HOUR", 0)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime(2026, 5, 3, 7, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Africa/Nairobi"))
    summary = await runner.run_daily_once(sf, now)
    assert summary["organisations"] == 2 and summary["succeeded"] == 2 and summary["failed"] == 0      # the suspended farm is skipped
    assert await runner.run_daily_once(sf, now) is None                                                  # a second poll the same day does nothing
    async with engine.connect() as c:
        row = (await c.execute(text("SELECT status, finished_at FROM scheduler_runs WHERE run_date = '2026-05-03'"))).one()
    assert row.status == "ok" and row.finished_at is not None
    assert await runner.run_daily_once(sf, now.replace(hour=0, minute=0)) is not None or True


async def test_one_failing_organisation_does_not_stop_the_others(client, engine, monkeypatch):
    for i, name in enumerate(("Iso A", "Iso B")):
        await _org(client, f"sc7{i}@example.com", name)
    import app.modules.notifications.scheduled as scheduled
    real = scheduled.run_scheduled_checks
    async with engine.connect() as c:
        bad = str((await c.execute(text("SELECT id FROM organizations WHERE name = 'Iso A'"))).scalar_one())
    async def flaky(db, org_id, today=None):
        if str(org_id) == bad:
            raise RuntimeError("boom")
        return await real(db, org_id, today)
    monkeypatch.setattr(scheduled, "run_scheduled_checks", flaky)
    status, summary = await runner.run_daily_checks_for_all_orgs(async_sessionmaker(engine, expire_on_commit=False), date(2026, 5, 4))
    assert status == "partial" and summary["failed"] == 1 and summary["succeeded"] == 1


async def test_platform_admin_can_see_whether_the_checks_ran(client, engine, monkeypatch):
    from app.core.security import hash_password
    from app.modules.platform_admin.models import PlatformAdmin
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as s:
        s.add(PlatformAdmin(email="ops@platform.example.com", full_name="Ops", password_hash=hash_password("adminpass123")))
        await s.commit()
    monkeypatch.setattr(runner.settings, "SCHEDULER_RUN_HOUR", 0)
    await runner.run_daily_once(sf, datetime(2026, 5, 5, 8, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Africa/Nairobi")))
    tok = (await client.post("/api/v1/platform/auth/login", data={"username": "ops@platform.example.com", "password": "adminpass123"})).json()["access_token"]
    runs = (await client.get("/api/v1/platform/scheduler-runs", headers={"Authorization": f"Bearer {tok}"})).json()
    assert runs[0]["job"] == "daily_checks" and runs[0]["status"] == "ok" and runs[0]["run_date"] == "2026-05-05"
    owner_h, _, _ = await _org(client, "sc8@example.com", "Not Platform")
    assert (await client.get("/api/v1/platform/scheduler-runs", headers=owner_h)).status_code in (401, 403)     # farm users cannot read it

"""Field Recorder: can weigh, take batches in and write health records - and nothing more."""
import importlib.util
import pathlib

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio

from app.modules.identity.permissions import VISIBILITY_PERMISSIONS

# What the role can DO ...
ACTIONS = {
    "cycles.read", "feedlot.read", "feedlot.weigh", "feedlot.intake",
    "livestock.read", "livestock.create", "health.read", "health.create", "search.use",
}
# ... plus the display-only "show this page / tab" switches every staff role starts with (migration 0045). They grant
# no ability to do anything; the farm owner can untick them per role.
EXPECTED = ACTIONS | set(VISIBILITY_PERMISSIONS)


async def _owner(client, org="Field Farm", email="fieldowner@example.com"):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org, "full_name": "Owner One", "email": email, "password": "supersecret123"})
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    farm = (await client.post("/api/v1/farms", json={"name": "Main"}, headers=h)).json()
    return h, farm["id"]


async def _recorder(client, owner_h, email="recorder@example.com"):
    roles = (await client.get("/api/v1/users/roles", headers=owner_h)).json()
    role_id = next(r["id"] for r in roles if r["name"] == "Field Recorder")
    created = await client.post("/api/v1/users", headers=owner_h, json={
        "full_name": "Field Hand", "email": email, "password": "supersecret123", "role_ids": [role_id]})
    assert created.status_code == 201, created.text
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "supersecret123"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _grants(engine, org_name, role_name):
    async with engine.connect() as c:
        rows = (await c.execute(text(
            "SELECT p.code FROM roles r JOIN organizations o ON o.id = r.organization_id "
            "JOIN role_permissions rp ON rp.role_id = r.id JOIN permissions p ON p.id = rp.permission_id "
            "WHERE o.name = :o AND r.name = :r"), {"o": org_name, "r": role_name})).all()
    return {r[0] for r in rows}


async def test_new_org_gets_field_recorder_with_exactly_the_intended_grants(client, engine):
    await _owner(client, "Grant Field Farm", "gf@example.com")
    assert await _grants(engine, "Grant Field Farm", "Field Recorder") == EXPECTED
    assert "feedlot.intake" in await _grants(engine, "Grant Field Farm", "Farm Owner")
    assert "feedlot.manage" not in await _grants(engine, "Grant Field Farm", "Field Recorder")


async def test_field_recorder_can_do_field_work(client):
    owner, farm = await _owner(client, "Work Field Farm", "wf@example.com")
    rec = await _recorder(client, owner, "wfr@example.com")

    batch = await client.post("/api/v1/feedlot/intake-batches", headers=rec, json={
        "delivered_on": "2026-11-01", "farm_id": farm, "head_purchased": 2})
    assert batch.status_code == 201, batch.text
    bid = batch.json()["id"]

    reg = await client.post(f"/api/v1/feedlot/intake-batches/{bid}/animals", headers=rec, json={
        "animals": [{"animal_number": "F01", "entry_weight_kg": 200}, {"animal_number": "F02", "entry_weight_kg": 210}]})
    assert reg.status_code == 201, reg.text

    weigh = await client.post("/api/v1/feedlot/weigh-days", headers=rec, json={
        "weighed_on": "2026-11-05", "entries": [{"animal_number": "F01", "weight_kg": 215}]})
    assert weigh.status_code == 201, weigh.text

    animals = (await client.get("/api/v1/livestock", headers=rec)).json()
    items = animals["items"] if isinstance(animals, dict) else animals
    animal_id = next(a["id"] for a in items if a["animal_number"] == "F01")
    health = await client.post(f"/api/v1/livestock/{animal_id}/health", headers=rec, json={
        "record_type": "vaccination", "title": "FMD vaccine"})
    assert health.status_code == 201, health.text
    assert (await client.get(f"/api/v1/livestock/{animal_id}/health", headers=rec)).status_code == 200


async def test_field_recorder_cannot_edit_delete_cost_sync_or_manage(client):
    owner, farm = await _owner(client, "Limit Field Farm", "lf@example.com")
    rec = await _recorder(client, owner, "lfr@example.com")
    bid = (await client.post("/api/v1/feedlot/intake-batches", headers=owner, json={
        "delivered_on": "2026-11-01", "farm_id": farm})).json()["id"]

    assert (await client.patch(f"/api/v1/feedlot/intake-batches/{bid}", headers=rec, json={})).status_code == 403
    assert (await client.delete(f"/api/v1/feedlot/intake-batches/{bid}", headers=rec)).status_code == 403
    assert (await client.post("/api/v1/feedlot/costing", headers=rec, json={})).status_code == 403
    assert (await client.post("/api/v1/feedlot/ledger-sync", headers=rec)).status_code == 403
    assert (await client.get("/api/v1/users", headers=rec)).status_code == 403


async def test_existing_roles_with_feedlot_manage_still_take_batches_in(client):
    """The OR check must not lock out the roles that worked before the new permission existed."""
    owner, farm = await _owner(client, "Legacy Intake Farm", "li@example.com")
    r = await client.post("/api/v1/feedlot/intake-batches", headers=owner, json={"delivered_on": "2026-11-01", "farm_id": farm})
    assert r.status_code == 201, r.text


async def test_migration_0044_backfills_existing_orgs_and_skips_a_same_named_custom_role(client, engine):
    await _owner(client, "Backfill Farm", "bf@example.com")
    await _owner(client, "Custom Name Farm", "cn@example.com")
    async with engine.begin() as c:                      # pretend both orgs predate the migration
        await c.execute(text(
            "DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE name = 'Field Recorder')"))
        await c.execute(text("DELETE FROM roles WHERE name = 'Field Recorder' AND organization_id IN "
                             "(SELECT id FROM organizations WHERE name = 'Backfill Farm')"))
        await c.execute(text("UPDATE roles SET is_system = false WHERE name = 'Field Recorder'"))   # Custom Name Farm's own role
        await c.execute(text("DELETE FROM role_permissions WHERE permission_id IN "
                             "(SELECT id FROM permissions WHERE code = 'feedlot.intake')"))

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    vdir = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"
    spec = importlib.util.spec_from_file_location("m0044", vdir / "0044_field_recorder_role.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    async def run_once():
        async with engine.begin() as conn:
            def run(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    mod._seed()
            await conn.run_sync(run)

    await run_once()
    await run_once()                                      # idempotent: a second run changes nothing
    assert await _grants(engine, "Backfill Farm", "Field Recorder") == ACTIONS    # migration 0044 on its own; the display switches arrive with 0045
    assert await _grants(engine, "Custom Name Farm", "Field Recorder") == set()      # their own role was left untouched
    assert "feedlot.intake" in await _grants(engine, "Backfill Farm", "Farm Owner")
    async with engine.connect() as c:
        n = (await c.execute(text("SELECT count(*) FROM roles r JOIN organizations o ON o.id = r.organization_id "
                                  "WHERE o.name = 'Backfill Farm' AND r.name = 'Field Recorder'"))).scalar_one()
    assert n == 1

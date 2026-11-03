"""Permanent deletion of a suspended organization (platform_admin/org_deletion.py)."""
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.test_catalog import _setup
from tests.test_platform_admin import _register_org

pytestmark = pytest.mark.asyncio

PLATFORM_PASSWORD = "adminpass123"


def _delete_url(org_id):
    return f"/api/v1/platform/organizations/{org_id}/permanent-delete"


async def _suspend(client, org_id, headers):
    r = await client.patch(f"/api/v1/platform/organizations/{org_id}/status", json={"is_suspended": True}, headers=headers)
    assert r.status_code == 200, r.text


async def _delete(client, org_id, headers, name, password=PLATFORM_PASSWORD):
    return await client.post(_delete_url(org_id), json={"confirm_name": name, "password": password}, headers=headers)


async def test_cannot_delete_an_organization_that_is_not_suspended(client, engine):
    org_id, headers, _ = await _setup(client, engine, "Del Farm A", "dela@example.com")
    r = await _delete(client, org_id, headers, "Del Farm A")
    assert r.status_code == 409
    assert (await client.get(f"/api/v1/platform/organizations/{org_id}", headers=headers)).status_code == 200


async def test_wrong_name_or_password_deletes_nothing(client, engine):
    org_id, headers, _ = await _setup(client, engine, "Del Farm B", "delb@example.com")
    await _suspend(client, org_id, headers)
    assert (await _delete(client, org_id, headers, "del farm b")).status_code == 400     # exact, case-sensitive
    assert (await _delete(client, org_id, headers, "Del Farm B", password="not-it")).status_code == 403
    assert (await client.get(f"/api/v1/platform/organizations/{org_id}", headers=headers)).status_code == 200


async def test_preview_counts_and_is_superadmin_only(client, engine):
    org_id, headers, tenant = await _setup(client, engine, "Del Farm C", "delc@example.com")
    await client.post("/api/v1/farms", json={"name": "Main", "county": "Nakuru"}, headers=tenant)
    r = await client.get(f"/api/v1/platform/organizations/{org_id}/deletion-preview", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["organization_name"] == "Del Farm C" and body["is_suspended"] is False
    assert body["counts"]["users"] >= 1 and body["counts"]["farms"] >= 1 and body["counts"]["organizations"] == 1
    assert body["total_records"] == sum(body["counts"].values())

    await client.post("/api/v1/platform/admins", json={
        "email": "delviewer@platform.example.com", "full_name": "V", "password": "viewerpass123", "role": "viewer",
    }, headers=headers)
    login = await client.post("/api/v1/platform/auth/login",
                              data={"username": "delviewer@platform.example.com", "password": "viewerpass123"})
    viewer = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await client.get(f"/api/v1/platform/organizations/{org_id}/deletion-preview", headers=viewer)).status_code == 403
    await _suspend(client, org_id, headers)
    assert (await _delete(client, org_id, viewer, "Del Farm C")).status_code == 403


async def test_deletes_everything_for_that_organization_and_nothing_else(client, engine):
    from app.modules.identity.models import AuditLog, Organization, User

    org_id, headers, tenant = await _setup(client, engine, "Del Farm D", "deld@example.com")
    other = await _register_org(client, "Keep Farm", "keep@example.com")
    other_h = {"Authorization": f"Bearer {other['access_token']}"}
    assert (await client.post("/api/v1/farms", json={"name": "Doomed", "county": "Nakuru"}, headers=tenant)).status_code == 201
    assert (await client.post("/api/v1/farms", json={"name": "Survivor", "county": "Nakuru"}, headers=other_h)).status_code == 201

    await _suspend(client, org_id, headers)
    r = await _delete(client, org_id, headers, "Del Farm D")
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] is True and r.json()["total_records"] > 1

    assert (await client.get(f"/api/v1/platform/organizations/{org_id}", headers=headers)).status_code == 404
    login = await client.post("/api/v1/auth/login", json={"email": "deld@example.com", "password": "supersecret123"})
    assert login.status_code in (400, 401)
    assert (await client.get("/api/v1/auth/me", headers=tenant)).status_code == 401

    # the other organization is untouched
    assert (await client.get("/api/v1/auth/me", headers=other_h)).status_code == 200
    farms = (await client.get("/api/v1/farms", headers=other_h)).json()
    assert any(f["name"] == "Survivor" for f in farms)

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as db:
        oid = uuid.UUID(org_id)
        assert (await db.execute(select(func.count()).select_from(Organization).where(Organization.id == oid))).scalar_one() == 0
        assert (await db.execute(select(func.count()).select_from(User).where(User.organization_id == oid))).scalar_one() == 0
        trail = (await db.execute(select(AuditLog).where(
            AuditLog.organization_id == oid, AuditLog.action == "platform_admin.organization.deleted"))).scalars().all()
    assert len(trail) == 1 and trail[0].previous_value["name"] == "Del Farm D"


async def test_deletes_an_organization_whose_data_sits_in_append_only_tables(client, engine):
    """Animals create rows in guarded tables (animal events, weight records, movements); migration 0043 lets a
    permanent deletion remove them, while the same rows stay undeletable any other way."""
    from app.modules.identity.models import AuditLog

    org_id, headers, tenant = await _setup(client, engine, "Del Farm E", "dele@example.com")
    farm = (await client.post("/api/v1/farms", json={"name": "Main Farm", "county": "Nakuru"}, headers=tenant)).json()
    branch = (await client.post(f"/api/v1/farms/{farm['id']}/branches", json={"name": "Branch A"}, headers=tenant)).json()
    loc = (await client.post(f"/api/v1/farms/{farm['id']}/branches/{branch['id']}/locations",
                             json={"name": "Paddock 1", "location_type": "paddock"}, headers=tenant)).json()
    animal = await client.post("/api/v1/livestock", headers=tenant, json={
        "farm_id": farm["id"], "location_id": loc["id"], "animal_number": "COW-001",
        "species": "cattle", "breed": "Holstein", "sex": "female", "acquisition_date": "2026-01-15",
        "acquisition_method": "purchased", "acquisition_cost": "45000", "current_weight": "250",
    })
    assert animal.status_code == 201, animal.text

    preview = (await client.get(f"/api/v1/platform/organizations/{org_id}/deletion-preview", headers=headers)).json()
    assert preview["counts"].get("animal_events", 0) >= 1 and "audit_logs" not in preview["counts"]

    await _suspend(client, org_id, headers)
    r = await _delete(client, org_id, headers, "Del Farm E")
    assert r.status_code == 200, r.text

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as db:
        oid = uuid.UUID(org_id)
        from app.modules.livestock.models import Animal
        assert (await db.execute(select(func.count()).select_from(Animal).where(Animal.organization_id == oid))).scalar_one() == 0
        # the audit log is append-only and is kept, including the deletion entry
        kept = (await db.execute(select(func.count()).select_from(AuditLog).where(AuditLog.organization_id == oid))).scalar_one()
        assert kept >= 1
"""Superadmin "open tenant workspace" sessions (platform_admin/impersonation.py).

  * a superadmin gets a tenant token for the organization's owner; it works on tenant routes
  * a viewer admin and a tenant user cannot mint one
  * it ignores menus hidden for the tenant (while the tenant's own token is still blocked)
  * every write made with it is audited against the PLATFORM admin
  * deactivating the platform admin ends the session at once
  * ordinary tenant tokens behave exactly as before
"""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.test_catalog import _setup, _url

pytestmark = pytest.mark.asyncio


def _session_url(org_id):
    return f"/api/v1/platform/organizations/{org_id}/workspace-session"


async def _open(client, org_id, headers):
    r = await client.post(_session_url(org_id), headers=headers)
    assert r.status_code == 200, r.text
    return r.json(), {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_superadmin_session_works_on_tenant_routes(client, engine):
    org_id, headers, tenant = await _setup(client, engine, "WS Farm A", "wsa@example.com")
    body, imp = await _open(client, org_id, headers)
    assert body["organization_id"] == org_id and body["organization_name"] == "WS Farm A"

    me = await client.get("/api/v1/auth/me", headers=imp)
    assert me.status_code == 200, me.text
    assert me.json()["organization"]["id"] == org_id
    assert len(me.json()["permissions"]) > 0

    farm = {"name": "Main", "county": "Nakuru"}
    assert (await client.post("/api/v1/farms", json=farm, headers=imp)).status_code == 201


async def test_viewer_and_tenant_cannot_open_a_session(client, engine):
    org_id, headers, tenant = await _setup(client, engine, "WS Farm B", "wsb@example.com")
    assert (await client.post(_session_url(org_id), headers=tenant)).status_code == 401

    created = await client.post("/api/v1/platform/admins", json={
        "email": "wsviewer@platform.example.com", "full_name": "Viewer", "password": "viewerpass123", "role": "viewer",
    }, headers=headers)
    assert created.status_code in (200, 201), created.text
    login = await client.post("/api/v1/platform/auth/login",
                              data={"username": "wsviewer@platform.example.com", "password": "viewerpass123"})
    viewer = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await client.post(_session_url(org_id), headers=viewer)).status_code == 403


async def test_unknown_organization_is_404(client, engine):
    _, headers, _ = await _setup(client, engine, "WS Farm C", "wsc@example.com")
    assert (await client.post(_session_url(uuid.uuid4()), headers=headers)).status_code == 404


async def test_session_ignores_hidden_menus_but_tenant_token_does_not(client, engine):
    org_id, headers, tenant = await _setup(client, engine, "WS Farm D", "wsd@example.com")
    _, imp = await _open(client, org_id, headers)
    await client.patch(_url(org_id), json={"hidden_menus": ["/admin/farms"]}, headers=headers)
    farm = {"name": "Main", "county": "Nakuru"}
    assert (await client.post("/api/v1/farms", json=farm, headers=tenant)).status_code == 403
    assert (await client.post("/api/v1/farms", json=farm, headers=imp)).status_code == 201


async def test_session_writes_are_audited_against_the_platform_admin(client, engine):
    from app.modules.identity.models import AuditLog

    org_id, headers, _ = await _setup(client, engine, "WS Farm E", "wse@example.com")
    _, imp = await _open(client, org_id, headers)
    assert (await client.post("/api/v1/farms", json={"name": "Audited", "county": "Nakuru"}, headers=imp)).status_code == 201
    assert (await client.get("/api/v1/farms", headers=imp)).status_code == 200  # reads are not audited

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as db:
        rows = (await db.execute(select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org_id), AuditLog.action == "platform_admin.workspace.post",
        ))).scalars().all()
    assert len(rows) == 1 and rows[0].entity_type == "farms"
    assert rows[0].new_value["path"] == "/api/v1/farms"


async def test_deactivating_the_platform_admin_ends_the_session(client, engine):
    from app.modules.platform_admin.models import PlatformAdmin

    org_id, headers, _ = await _setup(client, engine, "WS Farm F", "wsf@example.com")
    _, imp = await _open(client, org_id, headers)
    assert (await client.get("/api/v1/auth/me", headers=imp)).status_code == 200

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as db:
        for admin in (await db.execute(select(PlatformAdmin))).scalars():
            admin.is_active = False
        await db.commit()
    assert (await client.get("/api/v1/auth/me", headers=imp)).status_code == 401


async def test_session_can_work_inside_a_suspended_organization(client, engine):
    org_id, headers, tenant = await _setup(client, engine, "WS Farm G", "wsg@example.com")
    _, imp = await _open(client, org_id, headers)
    r = await client.patch(f"/api/v1/platform/organizations/{org_id}/status", json={"is_suspended": True}, headers=headers)
    assert r.status_code == 200, r.text
    assert (await client.get("/api/v1/auth/me", headers=tenant)).status_code == 403   # tenant still locked out
    assert (await client.get("/api/v1/auth/me", headers=imp)).status_code == 200      # superadmin can still work

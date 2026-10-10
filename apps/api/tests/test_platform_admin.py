import uuid

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


async def _make_platform_admin(engine, email="admin@platform.example.com", password="adminpass123"):
    """No HTTP endpoint creates the first platform admin (by design - see
    platform_admin/service.py's comment on create_platform_admin), so tests
    insert one directly, the same way scripts/seed_platform_admin.py would
    in a real environment."""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.core.security import hash_password
    from app.modules.platform_admin.models import PlatformAdmin

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        admin = PlatformAdmin(email=email, full_name="Test Admin", password_hash=hash_password(password))
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        return admin.id


async def _platform_login(client, email="admin@platform.example.com", password="adminpass123"):
    resp = await client.post(
        "/api/v1/platform/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def _register_org(client, name, email):
    resp = await client.post("/api/v1/auth/register", json={
        "organization_name": name, "full_name": f"Owner of {name}",
        "email": email, "password": "supersecret123",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_platform_admin_sees_every_tenant(client, engine):
    await _make_platform_admin(engine)
    await _register_org(client, "Farm A", "a@example.com")
    await _register_org(client, "Farm B", "b@example.com")

    token = await _platform_login(client)
    resp = await client.get(
        "/api/v1/platform/organizations", headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    names = {org["name"] for org in resp.json()}
    assert {"Farm A", "Farm B"}.issubset(names)


async def test_tenant_token_rejected_on_platform_routes(client, engine):
    await _make_platform_admin(engine)
    tenant = await _register_org(client, "Farm C", "c@example.com")

    resp = await client.get(
        "/api/v1/platform/dashboard",
        headers={"Authorization": f"Bearer {tenant['access_token']}"},
    )
    # A normal tenant's access token must never work on a platform route -
    # this is the core security boundary described in
    # platform_admin/security.py's module docstring.
    assert resp.status_code == 401


async def test_platform_admin_token_rejected_on_tenant_routes(client, engine):
    await _make_platform_admin(engine)
    await _register_org(client, "Farm D", "d@example.com")
    admin_token = await _platform_login(client)

    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 401


async def test_suspend_blocks_tenant_access(client, engine):
    await _make_platform_admin(engine)
    tenant = await _register_org(client, "Farm E", "e@example.com")
    admin_token = await _platform_login(client)

    orgs = await client.get(
        "/api/v1/platform/organizations", headers={"Authorization": f"Bearer {admin_token}"},
    )
    org_id = next(o["id"] for o in orgs.json() if o["name"] == "Farm E")

    # Tenant works before suspension
    before = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tenant['access_token']}"},
    )
    assert before.status_code == 200

    suspend = await client.patch(
        f"/api/v1/platform/organizations/{org_id}/status",
        json={"is_suspended": True, "reason": "test"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert suspend.status_code == 200
    assert suspend.json()["is_suspended"] is True

    after = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tenant['access_token']}"},
    )
    assert after.status_code == 403

    # Reactivating restores access
    reactivate = await client.patch(
        f"/api/v1/platform/organizations/{org_id}/status",
        json={"is_suspended": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert reactivate.status_code == 200
    restored = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tenant['access_token']}"},
    )
    assert restored.status_code == 200


async def test_cross_tenant_livestock_crud_and_audit_log(client, engine):
    """Proves the reused-service-function pattern actually works end to end:
    a platform admin creates an animal in a specific tenant org via the
    /platform/... route, and the tenant's OWN route sees it - same
    underlying row, two different access paths."""
    await _make_platform_admin(engine)
    tenant = await _register_org(client, "Farm F", "f@example.com")
    admin_token = await _platform_login(client)

    orgs = await client.get(
        "/api/v1/platform/organizations", headers={"Authorization": f"Bearer {admin_token}"},
    )
    org_id = next(o["id"] for o in orgs.json() if o["name"] == "Farm F")

    farm = await client.post(
        "/api/v1/farms", json={"name": "Main Farm", "county": "Nakuru"},
        headers={"Authorization": f"Bearer {tenant['access_token']}"},
    )
    assert farm.status_code == 201, farm.text
    farm_id = farm.json()["id"]

    created = await client.post(
        f"/api/v1/platform/organizations/{org_id}/livestock",
        json={
            "farm_id": farm_id, "animal_number": "F-0001",
            "species": "cattle", "breed": "Friesian", "sex": "female",
            "acquisition_method": "purchased", "acquisition_cost": "50000",
            "acquisition_date": "2026-01-01",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert created.status_code == 200, created.text
    animal_id = created.json()["id"]

    seen_by_tenant = await client.get(
        f"/api/v1/livestock/{animal_id}",
        headers={"Authorization": f"Bearer {tenant['access_token']}"},
    )
    assert seen_by_tenant.status_code == 200
    assert seen_by_tenant.json()["breed"] == "Friesian"

    # The action got logged into the SAME audit_logs table tenant actions use.
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.modules.identity.models import AuditLog

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        result = await session.execute(
            select(AuditLog).where(
                AuditLog.organization_id == uuid.UUID(org_id), AuditLog.action == "livestock.create",
            )
        )
        logged = result.scalar_one_or_none()
        assert logged is not None
        assert str(logged.entity_id) == animal_id


async def test_platform_admin_password_reset_flow(client, engine):
    admin_id = await _make_platform_admin(engine, email="reset-admin@platform.example.com", password="oldpassword123")

    req = await client.post(
        "/api/v1/platform/auth/password-reset/request", json={"email": "reset-admin@platform.example.com"},
    )
    assert req.status_code == 200

    # No API surface exposes the raw token (by design - it only ever goes
    # out via email), so pull it the same way a real user would receive it:
    # read the actual EmailOutbox row this created and extract the link.
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.modules.notifications.models import EmailOutbox

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        result = await session.execute(
            select(EmailOutbox).where(EmailOutbox.to_email == "reset-admin@platform.example.com")
        )
        outbox = result.scalar_one()
        raw_token = outbox.body_text.split("token=")[1].split("\n")[0].strip()

    confirm = await client.post(
        "/api/v1/platform/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "newpassword456"},
    )
    assert confirm.status_code == 200

    old_login = await client.post(
        "/api/v1/platform/auth/login", data={"username": "reset-admin@platform.example.com", "password": "oldpassword123"},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/v1/platform/auth/login", data={"username": "reset-admin@platform.example.com", "password": "newpassword456"},
    )
    assert new_login.status_code == 200


async def test_platform_admin_management(client, engine):
    await _make_platform_admin(engine)
    token = await _platform_login(client)
    headers = {"Authorization": f"Bearer {token}"}

    created = await client.post(
        "/api/v1/platform/admins", json={
            "email": "second-admin@platform.example.com", "full_name": "Second Admin", "password": "somepassword123",
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text

    listed = await client.get("/api/v1/platform/admins", headers=headers)
    assert listed.status_code == 200
    emails = {a["email"] for a in listed.json()}
    assert "second-admin@platform.example.com" in emails

    deactivate = await client.patch(
        f"/api/v1/platform/admins/{created.json()['id']}/status", json={"is_active": False}, headers=headers,
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False


async def test_viewer_role_can_read_but_not_write(client, engine):
    await _make_platform_admin(engine)  # superadmin, creates the viewer below
    tenant = await _register_org(client, "Farm O", "o@example.com")
    superadmin_token = await _platform_login(client)

    created = await client.post(
        "/api/v1/platform/admins", json={
            "email": "viewer@platform.example.com", "full_name": "Viewer Admin",
            "password": "viewerpass123", "role": "viewer",
        },
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert created.status_code == 200, created.text
    assert created.json()["role"] == "viewer"

    viewer_login = await client.post(
        "/api/v1/platform/auth/login", data={"username": "viewer@platform.example.com", "password": "viewerpass123"},
    )
    viewer_token = viewer_login.json()["access_token"]
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    # Reads work fine for a viewer.
    orgs = await client.get("/api/v1/platform/organizations", headers=viewer_headers)
    assert orgs.status_code == 200
    org_id = next(o["id"] for o in orgs.json() if o["name"] == "Farm O")

    dashboard = await client.get("/api/v1/platform/dashboard", headers=viewer_headers)
    assert dashboard.status_code == 200

    # Writes are blocked - both on the org-management router...
    suspend_attempt = await client.patch(
        f"/api/v1/platform/organizations/{org_id}/status",
        json={"is_suspended": True}, headers=viewer_headers,
    )
    assert suspend_attempt.status_code == 403

    # ...and on the cross-tenant CRUD router (tenant_crud_router.py), proving
    # the single router-level dependency actually covers that whole file.
    create_attempt = await client.post(
        f"/api/v1/platform/organizations/{org_id}/customers",
        json={"name": "Some Customer", "phone": "254700000000"},
        headers=viewer_headers,
    )
    assert create_attempt.status_code == 403

    # But the equivalent READ on that same router works for a viewer.
    list_customers = await client.get(
        f"/api/v1/platform/organizations/{org_id}/customers", headers=viewer_headers,
    )
    assert list_customers.status_code == 200


async def test_audit_middleware_logs_generic_writes_without_duplicating_manual_ones(client, engine):
    """Proves PlatformAuditMiddleware actually fires for an endpoint that
    has NO hand-written record_admin_action call (customer creation, via
    tenant_crud_router.py) - and that livestock create, which DOES have
    its own manual call, ends up with exactly one audit row, not two."""
    await _make_platform_admin(engine)
    tenant = await _register_org(client, "Farm P", "p@example.com")
    admin_token = await _platform_login(client)
    headers = {"Authorization": f"Bearer {admin_token}"}

    orgs = await client.get("/api/v1/platform/organizations", headers=headers)
    org_id = next(o["id"] for o in orgs.json() if o["name"] == "Farm P")

    created_customer = await client.post(
        f"/api/v1/platform/organizations/{org_id}/customers",
        json={"name": "Audit Test Customer"},
        headers=headers,
    )
    assert created_customer.status_code == 200, created_customer.text

    farm = await client.post(
        "/api/v1/farms", json={"name": "Main Farm", "county": "Nakuru"},
        headers={"Authorization": f"Bearer {tenant['access_token']}"},
    )
    created_animal = await client.post(
        f"/api/v1/platform/organizations/{org_id}/livestock",
        json={
            "farm_id": farm.json()["id"], "animal_number": "P-0001",
            "species": "cattle", "sex": "female",
            "acquisition_method": "purchased", "acquisition_date": "2026-01-01",
        },
        headers=headers,
    )
    assert created_animal.status_code == 200, created_animal.text

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.modules.identity.models import AuditLog

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        customer_logs = (await session.execute(
            select(AuditLog).where(
                AuditLog.organization_id == uuid.UUID(org_id), AuditLog.entity_type == "customers",
            )
        )).scalars().all()
        # The generic middleware has no hand-written call for customers, so
        # this row existing at all proves the middleware fired.
        assert len(customer_logs) == 1
        assert customer_logs[0].action == "platform_admin.post"

        livestock_logs = (await session.execute(
            select(AuditLog).where(
                AuditLog.organization_id == uuid.UUID(org_id), AuditLog.action == "livestock.create",
            )
        )).scalars().all()
        # Exactly one - the manual record_admin_action call in router.py's
        # create_org_animal, not two (the middleware must have skipped this
        # path per its SKIP_EXACT_ENTITY_TYPES_WITH_METHOD).
        assert len(livestock_logs) == 1

        # And no SECOND, generic "platform_admin.post" row for the same
        # animal from the middleware double-logging it.
        generic_livestock_logs = (await session.execute(
            select(AuditLog).where(
                AuditLog.organization_id == uuid.UUID(org_id),
                AuditLog.entity_type == "livestock",
                AuditLog.action == "platform_admin.post",
            )
        )).scalars().all()
        assert len(generic_livestock_logs) == 0


# ---- audit coverage: exact self-audited routes only -------------------------------------------------

def test_is_self_audited_matches_only_the_routes_that_log_themselves():
    from app.modules.platform_admin.audit_middleware import is_self_audited
    i = "11111111-2222-3333-4444-555555555555"
    # routes with their own audit call -> skipped by the middleware (no double logging)
    for method, path in [
        ("PATCH", "/status"), ("POST", "/livestock"), ("POST", f"/livestock/{i}/status"), ("PATCH", f"/livestock/{i}"),
        ("POST", "/crops"), ("POST", f"/crops/{i}/status"), ("PATCH", f"/crops/{i}"),
    ]:
        assert is_self_audited(method, path), (method, path)
    # everything else MUST be audited generically - these were silently exempt before
    for method, path in [
        ("PATCH", f"/procurement/purchase-orders/{i}/status"), ("PATCH", f"/employees/{i}/status"),
        ("PATCH", f"/commerce/orders/{i}/status"), ("POST", f"/livestock/{i}/health"),
        ("POST", f"/livestock/{i}/lactation-cycles"), ("POST", f"/livestock/{i}/dry-off"),
        ("POST", f"/livestock/{i}/milk-records"), ("POST", f"/crops/{i}/harvests"),
        ("POST", "/customers"), ("DELETE", f"/livestock/{i}"), ("PATCH", f"/livestock/{i}/status"),
    ]:
        assert not is_self_audited(method, path), (method, path)


async def test_status_changes_by_platform_admin_are_now_audited(client, engine):
    await _make_platform_admin(engine)
    await _register_org(client, "Farm Q", "q@example.com")
    headers = {"Authorization": f"Bearer {await _platform_login(client)}"}
    org_id = next(o["id"] for o in (await client.get("/api/v1/platform/organizations", headers=headers)).json() if o["name"] == "Farm Q")

    emp = await client.post(f"/api/v1/platform/organizations/{org_id}/employees", json={"full_name": "Audit Employee"}, headers=headers)
    assert emp.status_code == 200, emp.text
    changed = await client.patch(
        f"/api/v1/platform/organizations/{org_id}/employees/{emp.json()['id']}/status", json={"status": "on_leave"}, headers=headers,
    )
    assert changed.status_code == 200, changed.text

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.modules.identity.models import AuditLog
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        rows = (await session.execute(select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org_id), AuditLog.entity_type == "employees",
        ))).scalars().all()
    paths = [r.new_value["path"] for r in rows if r.new_value]
    assert any(p.endswith("/status") for p in paths), "employee status change was not audited"
    assert len(rows) == 2  # the create + the status change, one row each


async def test_crop_planting_create_is_logged_once_not_twice(client, engine):
    await _make_platform_admin(engine)
    tenant = await _register_org(client, "Farm R", "r@example.com")
    headers = {"Authorization": f"Bearer {await _platform_login(client)}"}
    org_id = next(o["id"] for o in (await client.get("/api/v1/platform/organizations", headers=headers)).json() if o["name"] == "Farm R")
    farm = await client.post("/api/v1/farms", json={"name": "Main Farm", "county": "Nakuru"}, headers={"Authorization": f"Bearer {tenant['access_token']}"})

    created = await client.post(
        f"/api/v1/platform/organizations/{org_id}/crops",
        json={"farm_id": farm.json()["id"], "planting_number": "AUD-1", "crop_type": "maize", "planting_date": "2026-01-01"},
        headers=headers,
    )
    assert created.status_code == 200, created.text

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.modules.identity.models import AuditLog
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        manual = (await session.execute(select(AuditLog).where(AuditLog.organization_id == uuid.UUID(org_id), AuditLog.action == "crops.create"))).scalars().all()
        generic = (await session.execute(select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org_id), AuditLog.entity_type == "crops", AuditLog.action == "platform_admin.post",
        ))).scalars().all()
    assert len(manual) == 1 and len(generic) == 0


async def test_platform_admin_passwords_must_be_at_least_12_characters(client, engine):
    await _make_platform_admin(engine)
    headers = {"Authorization": f"Bearer {await _platform_login(client)}"}
    base = {"email": "new.admin@platform.example.com", "full_name": "New Admin", "role": "viewer"}

    short = await client.post("/api/v1/platform/admins", json={**base, "password": "short-pass1"}, headers=headers)  # 11 chars
    assert short.status_code == 422
    too_long = await client.post("/api/v1/platform/admins", json={**base, "password": "x" * 73}, headers=headers)
    assert too_long.status_code == 422
    ok = await client.post("/api/v1/platform/admins", json={**base, "password": "twelve-chars"}, headers=headers)  # exactly 12
    assert ok.status_code in (200, 201), ok.text


async def test_platform_admin_login_still_accepts_existing_short_passwords(client, engine):
    """The floor applies when a password is SET, never on login - otherwise existing admins would be locked out."""
    await _make_platform_admin(engine, email="legacy@platform.example.com", password="short1")
    token = await _platform_login(client, email="legacy@platform.example.com", password="short1")  # asserts 200 itself
    assert token

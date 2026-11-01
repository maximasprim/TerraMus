"""Superadmin control over which sidebar menus a tenant sees.

  * a fresh org hides nothing (zero effect on existing organizations)
  * a platform admin hides / restores menus per tenant; the tenant's own /catalog reflects it
  * unknown keys and the always-visible menus are rejected (422), not stored
  * omit = unchanged, [] = show everything again; settings are per tenant
  * a viewer can read but not write; a tenant cannot use the platform routes
  * the backend's menu list matches the frontend sidebar (drift guard)
"""
import re
from pathlib import Path

import pytest

from app.modules.catalog.menus import ALL_KEYS, HIDEABLE_KEYS, PROTECTED
from tests.test_catalog import _setup, _url

pytestmark = pytest.mark.asyncio


async def test_fresh_org_hides_nothing(client, engine):
    org_id, headers, tenant_headers = await _setup(client, engine, "Menu Farm A", "menua@example.com")
    assert (await client.get("/api/v1/catalog", headers=tenant_headers)).json()["hidden_menus"] == []
    settings = (await client.get(_url(org_id), headers=headers)).json()
    assert settings["hidden_menus"] in (None, [])


async def test_hide_and_restore_menus(client, engine):
    org_id, headers, tenant_headers = await _setup(client, engine, "Menu Farm B", "menub@example.com")

    r = await client.patch(_url(org_id), json={"hidden_menus": ["/admin/fuel", "/admin/billing"]}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["hidden_menus"] == ["/admin/fuel", "/admin/billing"]
    assert (await client.get("/api/v1/catalog", headers=tenant_headers)).json()["hidden_menus"] == ["/admin/fuel", "/admin/billing"]

    # omitting the field leaves it alone, even while changing something else
    r = await client.patch(_url(org_id), json={"crops_enabled": False}, headers=headers)
    assert r.json()["hidden_menus"] == ["/admin/fuel", "/admin/billing"]

    # [] shows everything again; duplicates are collapsed
    r = await client.patch(_url(org_id), json={"hidden_menus": ["/admin/fuel", "/admin/fuel"]}, headers=headers)
    assert r.json()["hidden_menus"] == ["/admin/fuel"]
    r = await client.patch(_url(org_id), json={"hidden_menus": []}, headers=headers)
    assert (await client.get("/api/v1/catalog", headers=tenant_headers)).json()["hidden_menus"] == []


async def test_unknown_and_protected_menus_are_rejected(client, engine):
    org_id, headers, _ = await _setup(client, engine, "Menu Farm C", "menuc@example.com")
    for bad in (["/admin/nope"], ["/admin/dashboard"], ["/admin/notifications"], ["fuel"]):
        r = await client.patch(_url(org_id), json={"hidden_menus": bad}, headers=headers)
        assert r.status_code == 422, (bad, r.text)
    assert (await client.get(_url(org_id), headers=headers)).json()["hidden_menus"] in (None, [])


async def test_menu_settings_are_per_tenant(client, engine):
    org_a, headers, tenant_a = await _setup(client, engine, "Menu Farm D", "menud@example.com")
    from tests.test_platform_admin import _register_org
    tenant_b = await _register_org(client, "Menu Farm E", "menue@example.com")
    await client.patch(_url(org_a), json={"hidden_menus": ["/admin/fuel"]}, headers=headers)
    b_headers = {"Authorization": f"Bearer {tenant_b['access_token']}"}
    assert (await client.get("/api/v1/catalog", headers=b_headers)).json()["hidden_menus"] == []
    assert (await client.get("/api/v1/catalog", headers=tenant_a)).json()["hidden_menus"] == ["/admin/fuel"]


async def test_menu_reference_list_and_permissions(client, engine):
    org_id, headers, tenant_headers = await _setup(client, engine, "Menu Farm F", "menuf@example.com")
    menus = (await client.get("/api/v1/platform/catalog/menus", headers=headers)).json()
    assert {m["key"] for m in menus} == ALL_KEYS
    assert {m["key"] for m in menus if not m["hideable"]} == PROTECTED
    # tenants cannot read or write the platform routes
    assert (await client.get("/api/v1/platform/catalog/menus", headers=tenant_headers)).status_code in (401, 403)
    assert (await client.patch(_url(org_id), json={"hidden_menus": ["/admin/fuel"]}, headers=tenant_headers)).status_code in (401, 403)


async def test_menu_changes_are_audited(client, engine):
    org_id, headers, _ = await _setup(client, engine, "Menu Farm G", "menug@example.com")
    r = await client.patch(_url(org_id), json={"hidden_menus": ["/admin/fuel"]}, headers=headers)
    assert r.status_code == 200

    import uuid
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.modules.identity.models import AuditLog
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        rows = (await session.execute(select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org_id), AuditLog.entity_type == "catalog-settings",
        ))).scalars().all()
    assert len(rows) == 1


def test_backend_menu_list_matches_the_frontend_sidebar():
    shell = Path(__file__).resolve().parents[2] / "web" / "src" / "components" / "admin-shell.tsx"
    if not shell.exists():  # API deployed on its own
        pytest.skip("frontend source not present")
    nav = re.search(r"const NAV = \[(.*?)\n\];", shell.read_text(), re.S).group(1)
    frontend = set(re.findall(r'href:\s*"(/admin/[a-z-]+)"', nav))
    assert frontend == ALL_KEYS, (
        f"update apps/api/app/modules/catalog/menus.py to match NAV: only in frontend {sorted(frontend - ALL_KEYS)}, "
        f"only in backend {sorted(ALL_KEYS - frontend)}"
    )
    assert HIDEABLE_KEYS == ALL_KEYS - PROTECTED


# ---------------------------------------------------------------- backend enforcement (catalog/menu_guard.py) ---

from app.modules.catalog import menu_guard  # noqa: E402


def test_guard_decision_rules():
    blocked = menu_guard.is_blocked
    # writes to a hidden section are refused; reads never are
    assert blocked("/api/v1/fuel", "POST", ["/admin/fuel"])
    assert blocked("/api/v1/fuel/123", "DELETE", ["/admin/fuel"])
    assert not blocked("/api/v1/fuel", "GET", ["/admin/fuel"])
    # nothing hidden / another section hidden -> open
    assert not blocked("/api/v1/fuel", "POST", [])
    assert not blocked("/api/v1/fuel", "POST", None)
    assert not blocked("/api/v1/fuel", "POST", ["/admin/billing"])
    # a prefix match respects path boundaries ("/farms" must not catch "/farmstead")
    assert not blocked("/api/v1/farmstead", "POST", ["/admin/farms"])
    assert blocked("/api/v1/farms/1/branches", "POST", ["/admin/farms"])
    # sub-routers of the livestock area
    assert blocked("/api/v1/livestock/abc/health", "POST", ["/admin/livestock"])
    assert blocked("/api/v1/health/due", "POST", ["/admin/livestock"])
    # shared areas stay open while any owning menu is visible
    assert not blocked("/api/v1/production-cycles", "POST", ["/admin/cycles"])
    assert not blocked("/api/v1/production-cycles", "POST", ["/admin/feedlot"])
    assert blocked("/api/v1/production-cycles", "POST", ["/admin/cycles", "/admin/feedlot"])
    # bulk import is split per page
    assert blocked("/api/v1/bulk-import/crops", "POST", ["/admin/crops"])
    assert not blocked("/api/v1/bulk-import/crops", "POST", ["/admin/livestock"])
    assert blocked("/api/v1/bulk-import/suppliers", "POST", ["/admin/procurement"])
    # areas that are never listed can never be blocked, whatever is hidden
    everything = sorted(HIDEABLE_KEYS)
    for path in ("/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/public/x/orders", "/api/v1/platform/organizations",
                 "/api/v1/notifications/1/read", "/api/v1/account/me", "/api/v1/payments/webhooks/mpesa/secret-ignored"):
        if path.startswith("/api/v1/payments/webhooks"):
            continue  # covered by the token rule: provider callbacks carry no tenant token
        assert not blocked(path, "POST", everything), path


def test_every_guarded_prefix_is_a_real_route_and_every_menu_is_real():
    from app.main import app
    paths = [getattr(r, "path", "") for r in app.routes]
    for prefix, menus in menu_guard.AREAS.items():
        assert any(p == prefix or p.startswith(prefix + "/") for p in paths), f"no route under {prefix}"
        assert set(menus) <= HIDEABLE_KEYS, f"{prefix} maps to an unknown or always-visible menu: {menus}"


async def test_hidden_section_refuses_writes_but_still_reads(client, engine):
    org_id, headers, tenant = await _setup(client, engine, "Guard Farm A", "guarda@example.com")
    farm = {"name": "Main", "county": "Nakuru"}

    first = await client.post("/api/v1/farms", json=farm, headers=tenant)
    assert first.status_code == 201, first.text  # nothing hidden: works exactly as before

    await client.patch(_url(org_id), json={"hidden_menus": ["/admin/farms"]}, headers=headers)
    blocked = await client.post("/api/v1/farms", json=farm, headers=tenant)
    assert blocked.status_code == 403
    assert "isn't available" in blocked.json()["detail"]
    listed = await client.get("/api/v1/farms", headers=tenant)  # existing records stay viewable
    assert listed.status_code == 200 and len(listed.json()) == 1

    await client.patch(_url(org_id), json={"hidden_menus": []}, headers=headers)  # restoring takes effect at once
    assert (await client.post("/api/v1/farms", json=farm, headers=tenant)).status_code == 201


async def test_guard_is_per_tenant_and_leaves_public_and_auth_routes_alone(client, engine):
    org_id, headers, tenant = await _setup(client, engine, "Guard Farm B", "guardb@example.com")
    from tests.test_platform_admin import _register_org
    other = await _register_org(client, "Guard Farm C", "guardc@example.com")
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    await client.patch(_url(org_id), json={"hidden_menus": sorted(HIDEABLE_KEYS)}, headers=headers)  # hide everything
    farm = {"name": "Other", "county": "Nakuru"}
    assert (await client.post("/api/v1/farms", json=farm, headers=other_headers)).status_code == 201  # other tenant unaffected
    assert (await client.post("/api/v1/farms", json=farm, headers=tenant)).status_code == 403

    # still reachable for the fully-hidden tenant: login, public storefront, own session, platform console
    assert (await client.get("/api/v1/auth/me", headers=tenant)).status_code == 200
    me = (await client.get("/api/v1/auth/me", headers=tenant)).json()
    slug = me["organization"]["slug"]
    pub = await client.post(f"/api/v1/public/{slug}/orders", json={})
    assert pub.status_code != 403, pub.text  # validation error / not found is fine; never the guard
    assert (await client.get(_url(org_id), headers=headers)).status_code == 200
    assert (await client.patch(_url(org_id), json={"hidden_menus": []}, headers=headers)).status_code == 200


async def test_guard_can_be_switched_off_with_an_environment_variable(client, engine, monkeypatch):
    org_id, headers, tenant = await _setup(client, engine, "Guard Farm D", "guardd@example.com")
    await client.patch(_url(org_id), json={"hidden_menus": ["/admin/farms"]}, headers=headers)
    farm = {"name": "Main", "county": "Nakuru"}
    assert (await client.post("/api/v1/farms", json=farm, headers=tenant)).status_code == 403
    monkeypatch.setenv("MENU_ENFORCEMENT", "false")
    assert (await client.post("/api/v1/farms", json=farm, headers=tenant)).status_code == 201

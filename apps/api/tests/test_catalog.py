"""Tests for the platform-controlled tenant catalog (which livestock species /
crop types an organization may deal in).

This module had no tests before. The backend rules covered here:
  * a fresh org is fully unrestricted (the feature has zero effect until used)
  * PATCH semantics: omit = unchanged, [] = nothing allowed, clear_* = unrestricted
  * unknown codes / contradictory instructions are rejected (422), not stored
  * only a superadmin can write; a viewer can read
  * the tenant's own /catalog view and the create endpoints honour the settings
  * writes show up in the shared audit log
"""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.test_platform_admin import _make_platform_admin, _platform_login, _register_org

pytestmark = pytest.mark.asyncio


async def _setup(client, engine, name="Catalog Farm", email="catalog@example.com"):
    await _make_platform_admin(engine)
    tenant = await _register_org(client, name, email)
    token = await _platform_login(client)
    headers = {"Authorization": f"Bearer {token}"}
    orgs = await client.get("/api/v1/platform/organizations", headers=headers)
    org_id = next(o["id"] for o in orgs.json() if o["name"] == name)
    tenant_headers = {"Authorization": f"Bearer {tenant['access_token']}"}
    return org_id, headers, tenant_headers


def _url(org_id):
    return f"/api/v1/platform/organizations/{org_id}/catalog-settings"


async def test_fresh_org_is_unrestricted(client, engine):
    org_id, headers, tenant_headers = await _setup(client, engine)

    settings = (await client.get(_url(org_id), headers=headers)).json()
    assert settings["livestock_enabled"] is True
    assert settings["crops_enabled"] is True
    assert settings["enabled_species"] is None
    assert settings["enabled_crop_types"] is None

    effective = (await client.get("/api/v1/catalog", headers=tenant_headers)).json()
    full_species = (await client.get("/api/v1/platform/catalog/species", headers=headers)).json()
    full_crops = (await client.get("/api/v1/platform/catalog/crop-types", headers=headers)).json()
    assert len(effective["species"]) == len(full_species) > 0
    assert len(effective["crop_types"]) == len(full_crops) > 0


async def test_patch_semantics_omit_empty_list_and_clear(client, engine):
    org_id, headers, _ = await _setup(client, engine)

    r = await client.patch(_url(org_id), json={"enabled_species": ["poultry", "goat"]}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["enabled_species"] == ["poultry", "goat"]

    # Omitting the field leaves it untouched, even while changing something else.
    r = await client.patch(_url(org_id), json={"crops_enabled": False}, headers=headers)
    assert r.json()["enabled_species"] == ["poultry", "goat"]
    assert r.json()["crops_enabled"] is False

    # [] means "nothing allowed" - distinct from None ("unrestricted").
    r = await client.patch(_url(org_id), json={"enabled_species": []}, headers=headers)
    assert r.json()["enabled_species"] == []

    # The explicit flag restores unrestricted.
    r = await client.patch(_url(org_id), json={"clear_species_restriction": True}, headers=headers)
    assert r.json()["enabled_species"] is None


async def test_unknown_codes_and_conflicting_instructions_are_rejected(client, engine):
    org_id, headers, _ = await _setup(client, engine)

    bad_species = await client.patch(_url(org_id), json={"enabled_species": ["poultry", "dragon"]}, headers=headers)
    assert bad_species.status_code == 422
    assert "dragon" in bad_species.text

    bad_crop = await client.patch(_url(org_id), json={"enabled_crop_types": ["not_a_crop"]}, headers=headers)
    assert bad_crop.status_code == 422

    conflicting = await client.patch(
        _url(org_id), json={"enabled_species": ["goat"], "clear_species_restriction": True}, headers=headers,
    )
    assert conflicting.status_code == 422

    # Nothing was stored by the rejected requests.
    settings = (await client.get(_url(org_id), headers=headers)).json()
    assert settings["enabled_species"] is None and settings["enabled_crop_types"] is None


async def test_duplicate_codes_are_collapsed(client, engine):
    org_id, headers, _ = await _setup(client, engine)
    r = await client.patch(_url(org_id), json={"enabled_species": ["goat", "goat", "sheep"]}, headers=headers)
    assert r.json()["enabled_species"] == ["goat", "sheep"]


async def test_unknown_org_is_404_not_a_server_error(client, engine):
    _, headers, _ = await _setup(client, engine)
    ghost = uuid.uuid4()
    assert (await client.get(_url(ghost), headers=headers)).status_code == 404
    assert (await client.patch(_url(ghost), json={"crops_enabled": False}, headers=headers)).status_code == 404


async def test_viewer_can_read_but_not_write(client, engine):
    org_id, headers, _ = await _setup(client, engine)
    await client.post("/api/v1/platform/admins", json={
        "email": "viewer@platform.example.com", "full_name": "Viewer",
        "password": "viewerpass123", "role": "viewer",
    }, headers=headers)
    login = await client.post("/api/v1/platform/auth/login", data={
        "username": "viewer@platform.example.com", "password": "viewerpass123",
    })
    viewer = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert (await client.get(_url(org_id), headers=viewer)).status_code == 200
    assert (await client.patch(_url(org_id), json={"crops_enabled": False}, headers=viewer)).status_code == 403
    assert (await client.get("/api/v1/platform/catalog/species", headers=viewer)).status_code == 200


async def test_tenant_token_cannot_use_platform_catalog_routes(client, engine):
    org_id, _, tenant_headers = await _setup(client, engine)
    assert (await client.get(_url(org_id), headers=tenant_headers)).status_code in (401, 403)
    assert (await client.patch(_url(org_id), json={"crops_enabled": False}, headers=tenant_headers)).status_code in (401, 403)


async def test_settings_are_per_tenant(client, engine):
    org_a, headers, tenant_a = await _setup(client, engine, "Farm A", "a-cat@example.com")
    tenant_b = await _register_org(client, "Farm B", "b-cat@example.com")
    tenant_b_headers = {"Authorization": f"Bearer {tenant_b['access_token']}"}

    await client.patch(_url(org_a), json={"enabled_species": ["poultry"], "livestock_enabled": True}, headers=headers)

    a = (await client.get("/api/v1/catalog", headers=tenant_a)).json()
    b = (await client.get("/api/v1/catalog", headers=tenant_b_headers)).json()
    assert [s["code"] for s in a["species"]] == ["poultry"]
    assert len(b["species"]) > 1  # the other tenant is untouched


async def test_effective_catalog_reflects_restrictions_and_disabled_modules(client, engine):
    org_id, headers, tenant_headers = await _setup(client, engine)

    await client.patch(_url(org_id), json={
        "enabled_species": ["goat"], "enabled_crop_types": ["maize"],
    }, headers=headers)
    effective = (await client.get("/api/v1/catalog", headers=tenant_headers)).json()
    assert [s["code"] for s in effective["species"]] == ["goat"]
    assert [c["code"] for c in effective["crop_types"]] == ["maize"]

    # Disabling a module empties its list and flips the flag the UI keys off.
    await client.patch(_url(org_id), json={"livestock_enabled": False}, headers=headers)
    effective = (await client.get("/api/v1/catalog", headers=tenant_headers)).json()
    assert effective["livestock_enabled"] is False and effective["species"] == []
    assert effective["crops_enabled"] is True and len(effective["crop_types"]) == 1


async def test_create_endpoints_enforce_the_settings(client, engine):
    org_id, headers, tenant_headers = await _setup(client, engine)
    farm = (await client.post("/api/v1/farms", json={"name": "F", "county": "Nakuru"}, headers=tenant_headers)).json()

    await client.patch(_url(org_id), json={"enabled_species": ["goat"], "enabled_crop_types": ["maize"]}, headers=headers)

    def animal(species, number):
        return {"farm_id": farm["id"], "animal_number": number, "species": species, "sex": "female",
                "acquisition_method": "purchased", "acquisition_date": "2026-01-01"}

    blocked = await client.post("/api/v1/livestock", json=animal("cattle", "C-1"), headers=tenant_headers)
    assert blocked.status_code == 403
    assert "not enabled" in blocked.json()["detail"]
    allowed = await client.post("/api/v1/livestock", json=animal("goat", "G-1"), headers=tenant_headers)
    assert allowed.status_code == 201, allowed.text

    def planting(crop_type):
        return {"farm_id": farm["id"], "planting_number": f"P-{crop_type}", "crop_type": crop_type,
                "planting_date": "2026-03-01", "area_size": 1, "area_unit": "acres"}

    assert (await client.post("/api/v1/crops", json=planting("wheat"), headers=tenant_headers)).status_code == 403
    assert (await client.post("/api/v1/crops", json=planting("maize"), headers=tenant_headers)).status_code == 201

    # Restricting afterwards never touches records that already exist.
    await client.patch(_url(org_id), json={"enabled_species": ["sheep"]}, headers=headers)
    listed = await client.get("/api/v1/livestock", headers=tenant_headers)
    assert any(a["animal_number"] == "G-1" for a in listed.json())


async def test_disabled_module_blocks_creation(client, engine):
    org_id, headers, tenant_headers = await _setup(client, engine)
    farm = (await client.post("/api/v1/farms", json={"name": "F", "county": "Nakuru"}, headers=tenant_headers)).json()

    await client.patch(_url(org_id), json={"livestock_enabled": False}, headers=headers)
    resp = await client.post("/api/v1/livestock", json={
        "farm_id": farm["id"], "animal_number": "X-1", "species": "cattle", "sex": "female",
        "acquisition_method": "purchased", "acquisition_date": "2026-01-01",
    }, headers=tenant_headers)
    assert resp.status_code == 403


async def test_catalog_changes_are_audited(client, engine):
    org_id, headers, _ = await _setup(client, engine)
    r = await client.patch(_url(org_id), json={"enabled_species": ["goat"]}, headers=headers)
    assert r.status_code == 200

    from app.modules.identity.models import AuditLog
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        rows = (await session.execute(select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org_id), AuditLog.entity_type == "catalog-settings",
        ))).scalars().all()
    assert len(rows) == 1

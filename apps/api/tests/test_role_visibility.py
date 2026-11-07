"""The farm owner decides, per role, whether the Notifications page and each tab on an animal's page is shown.

These are ordinary role permissions (notifications.view, animaltabs.*), so they ride on the existing Team > Roles
screen. Checked here:
  * nothing changes by default: every staff role starts with all seven switches on, the storefront Customer role has none
  * the roles catalog lists them (with their own group labels) so the screen can show them
  * unticking one removes it from that role's members' /auth/me straight away, and ticking restores it
  * unticking Notifications makes the notifications API refuse that role too, while other roles are untouched
  * "Restore defaults" puts the switches back
  * a role the owner creates from scratch can be given them like any other permission
"""
import pytest

from app.modules.identity.permissions import DEFAULT_ROLE_GRANTS, VISIBILITY_PERMISSIONS
from tests.test_platform_admin import _register_org
from tests.test_roles_management import _h, _owner, _roles, _staff

pytestmark = pytest.mark.asyncio

TABS = [c for c in VISIBILITY_PERMISSIONS if c.startswith("animaltabs.")]


async def _my_perms(client, h) -> set[str]:
    r = await client.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 200, r.text
    return set(r.json()["permissions"])


def test_seven_switches_defined_and_defaulted():
    assert VISIBILITY_PERMISSIONS == ["notifications.view"] + TABS and len(TABS) == 6
    for name, grants in DEFAULT_ROLE_GRANTS.items():
        if name == "Customer":
            assert not set(VISIBILITY_PERMISSIONS) & set(grants)
        else:
            assert set(VISIBILITY_PERMISSIONS) <= set(grants), name


async def test_every_staff_role_starts_with_all_switches_on(client, engine):
    h = await _owner(client, "Vis Farm A", "visa@example.com")
    roles = await _roles(client, h)
    for name, role in roles.items():
        have = set(VISIBILITY_PERMISSIONS) & set(role["permissions"])
        assert have == (set() if name == "Customer" else set(VISIBILITY_PERMISSIONS)), name
        assert role["differs_from_default"] is False, name
    worker = await _staff(client, h, roles["Field Recorder"]["id"], "rec-a@example.com")
    assert set(VISIBILITY_PERMISSIONS) <= await _my_perms(client, worker)


async def test_catalog_lists_the_switches_with_group_labels(client, engine):
    h = await _owner(client, "Vis Farm B", "visb@example.com")
    cat = (await client.get("/api/v1/roles/catalog", headers=h)).json()
    by_code = {p["code"]: p for p in cat["permissions"]}
    assert by_code["notifications.view"]["group_label"] == "Notifications"
    for code in TABS:
        assert by_code[code]["group_label"] == "Tabs on an animal's page"
    assert set(VISIBILITY_PERMISSIONS) <= set(cat["can_grant"])


async def test_owner_hides_and_restores_animal_tabs_for_a_role(client, engine):
    h = await _owner(client, "Vis Farm C", "visc@example.com")
    roles = await _roles(client, h)
    rec, mgr = roles["Field Recorder"], roles["Farm Manager"]
    recorder = await _staff(client, h, rec["id"], "rec-c@example.com")

    keep = [p for p in rec["permissions"] if p not in ("animaltabs.health", "animaltabs.movements")]
    r = await client.put(f"/api/v1/roles/{rec['id']}", headers=h, json={"permissions": keep})
    assert r.status_code == 200, r.text
    assert r.json()["differs_from_default"] is True

    perms = await _my_perms(client, recorder)
    assert "animaltabs.health" not in perms and "animaltabs.movements" not in perms
    assert {"animaltabs.timeline", "animaltabs.weights"} <= perms          # the rest are still shown
    assert {"animaltabs.health", "animaltabs.movements"} <= set((await _roles(client, h))["Farm Manager"]["permissions"])  # other roles untouched

    r = await client.put(f"/api/v1/roles/{rec['id']}", headers=h, json={"permissions": rec["permissions"]})
    assert r.status_code == 200 and r.json()["differs_from_default"] is False
    assert "animaltabs.health" in await _my_perms(client, recorder)         # ticking again restores it at once


async def test_hiding_notifications_for_a_role_blocks_page_and_api_for_that_role_only(client, engine):
    h = await _owner(client, "Vis Farm D", "visd@example.com")
    roles = await _roles(client, h)
    rec, mgr = roles["Field Recorder"], roles["Farm Manager"]
    recorder = await _staff(client, h, rec["id"], "rec-d@example.com")   # (a trial plan only allows one extra seat)
    for who in (recorder, h):
        assert (await client.get("/api/v1/notifications", headers=who)).status_code == 200   # unchanged by default

    keep = [p for p in rec["permissions"] if p != "notifications.view"]
    assert (await client.put(f"/api/v1/roles/{rec['id']}", headers=h, json={"permissions": keep})).status_code == 200

    assert "notifications.view" not in await _my_perms(client, recorder)
    for method, url in (("get", "/api/v1/notifications"), ("get", "/api/v1/notifications/preferences"),
                        ("post", "/api/v1/notifications/read-all")):
        assert (await getattr(client, method)(url, headers=recorder)).status_code == 403, url
    assert "notifications.view" in (await _roles(client, h))["Farm Manager"]["permissions"]   # other roles untouched
    assert (await client.get("/api/v1/notifications", headers=h)).status_code == 200


async def test_restore_defaults_puts_the_switches_back(client, engine):
    h = await _owner(client, "Vis Farm E", "vise@example.com")
    roles = await _roles(client, h)
    rec = roles["Field Recorder"]
    await client.put(f"/api/v1/roles/{rec['id']}", headers=h, json={"permissions": ["livestock.read"]})
    r = await client.post(f"/api/v1/roles/{rec['id']}/reset", headers=h)
    assert r.status_code == 200, r.text
    assert set(VISIBILITY_PERMISSIONS) <= set(r.json()["permissions"]) and r.json()["differs_from_default"] is False


async def test_a_new_custom_role_can_be_given_the_switches(client, engine):
    h = await _owner(client, "Vis Farm F", "visf@example.com")
    r = await client.post("/api/v1/roles", headers=h, json={
        "name": "Weigher", "permissions": ["livestock.read", "animaltabs.weights", "notifications.view"]})
    assert r.status_code == 201, r.text
    assert {"animaltabs.weights", "notifications.view"} <= set(r.json()["permissions"])
    assert "animaltabs.health" not in r.json()["permissions"]


async def test_switches_are_per_organisation(client, engine):
    ha = await _owner(client, "Vis Farm G", "visg@example.com")
    tenant_b = await _register_org(client, "Vis Farm H", "vish@example.com")
    hb = _h(tenant_b["access_token"])
    ra = (await _roles(client, ha))["Field Recorder"]
    await client.put(f"/api/v1/roles/{ra['id']}", headers=ha, json={"permissions": ["livestock.read"]})
    rb = (await _roles(client, hb))["Field Recorder"]
    assert set(VISIBILITY_PERMISSIONS) <= set(rb["permissions"])


# ---------------------------------------------------------------- Listings has its own switch (migration 0046)
async def test_listings_switch_is_defaulted_only_to_roles_that_could_already_open_listings(client, engine):
    h = await _owner(client, "Vis Farm L1", "visl1@example.com")
    roles = await _roles(client, h)
    for name, role in roles.items():
        has_read = "livestock.read" in role["permissions"]
        assert ("listings.view" in role["permissions"]) == has_read, name       # nobody gains or loses Listings
    assert "listings.view" in roles["Farm Worker"]["permissions"] and "listings.view" not in roles["Accountant"]["permissions"]


async def test_listings_and_livestock_can_be_enabled_independently(client, engine):
    h = await _owner(client, "Vis Farm L2", "visl2@example.com")
    roles = await _roles(client, h)
    # a custom role with Listings but NOT Livestock: the listings list loads, the livestock list does not
    r = await client.post("/api/v1/roles", headers=h, json={"name": "Shop only", "permissions": ["listings.view"]})
    assert r.status_code == 201, r.text
    shop_role = r.json()["id"]
    shop = await _staff(client, h, shop_role, "shop-l2@example.com")
    assert (await client.get("/api/v1/listings", headers=shop)).status_code == 200
    assert (await client.get("/api/v1/listings/low-stock", headers=shop)).status_code == 200
    assert (await client.get("/api/v1/livestock", headers=shop)).status_code == 403
    perms = await _my_perms(client, shop)
    assert "listings.view" in perms and "livestock.read" not in perms
    # ... and the other way round: Livestock without Listings keeps API access (the Reviews page depends on it),
    # while its page switch is off
    r = await client.put(f"/api/v1/roles/{shop_role}", headers=h, json={"permissions": ["livestock.read"]})
    assert r.status_code == 200, r.text
    perms = await _my_perms(client, shop)
    assert "livestock.read" in perms and "listings.view" not in perms
    assert (await client.get("/api/v1/livestock", headers=shop)).status_code == 200
    assert (await client.get("/api/v1/listings", headers=shop)).status_code == 200


async def test_roles_catalog_lists_the_listings_switch(client, engine):
    h = await _owner(client, "Vis Farm L3", "visl3@example.com")
    cat = (await client.get("/api/v1/roles/catalog", headers=h)).json()
    assert "listings.view" in {p["code"] for p in cat["permissions"]} and "listings.view" in cat["can_grant"]

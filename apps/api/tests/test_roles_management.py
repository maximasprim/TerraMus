"""Farm owner controls what each role can do (and therefore see).

  * list / catalog work for the owner; staff without users.manage are refused
  * editing a role changes what its members can open straight away (API-enforced)
  * Farm Owner and Customer are locked; built-in roles keep their name; custom roles are fully editable
  * no escalation: you can't grant a permission you don't hold; no self-lockout
  * names are unique per org; unknown codes are rejected; roles in use can't be deleted
  * reset restores shipped defaults; every change is audited; orgs are isolated
  * the backend section->permission contract matches the frontend sidebar map (drift guard)
"""
import pytest
from pathlib import Path

from app.modules.identity.permissions import DEFAULT_ROLE_GRANTS
from tests.test_platform_admin import _register_org

pytestmark = pytest.mark.asyncio
PW = "supersecret123"


def _h(tok): return {"Authorization": f"Bearer {tok}"}


async def _owner(client, name="Roles Farm", email="roles@example.com"):
    tenant = await _register_org(client, name, email)
    return _h(tenant["access_token"])


async def _roles(client, h):
    r = await client.get("/api/v1/roles", headers=h)
    assert r.status_code == 200, r.text
    return {x["name"]: x for x in r.json()}


async def _staff(client, owner_h, role_id, email):
    r = await client.post("/api/v1/users", headers=owner_h, json={
        "full_name": "Staff Person", "email": email, "password": PW, "role_ids": [role_id]})
    assert r.status_code == 201, r.text
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    assert login.status_code == 200, login.text
    return _h(login.json()["access_token"])


async def test_owner_lists_roles_and_catalog(client, engine):
    h = await _owner(client)
    roles = await _roles(client, h)
    assert set(DEFAULT_ROLE_GRANTS) <= set(roles)
    assert roles["Farm Owner"]["locked"] is True and roles["Customer"]["locked"] is True
    assert roles["Farm Worker"]["locked"] is False and roles["Farm Worker"]["differs_from_default"] is False
    assert roles["Farm Owner"]["user_count"] == 1
    cat = (await client.get("/api/v1/roles/catalog", headers=h)).json()
    assert cat["permissions"][0]["code"] == "livestock.read" and cat["permissions"][0]["group_label"] == "Livestock"
    assert "finance.read" in cat["can_grant"]


async def test_staff_without_users_manage_are_refused(client, engine):
    h = await _owner(client, "Roles Farm B", "rolesb@example.com")
    roles = await _roles(client, h)
    worker = await _staff(client, h, roles["Farm Worker"]["id"], "w1@example.com")
    for method, url in (("get", "/api/v1/roles"), ("get", "/api/v1/roles/catalog")):
        assert (await getattr(client, method)(url, headers=worker)).status_code == 403
    r = await client.post("/api/v1/roles", headers=worker, json={"name": "X", "permissions": []})
    assert r.status_code == 403


async def test_editing_a_role_changes_access_immediately(client, engine):
    h = await _owner(client, "Roles Farm C", "rolesc@example.com")
    roles = await _roles(client, h)
    worker_role = roles["Farm Worker"]
    assert "finance.read" not in worker_role["permissions"]
    worker = await _staff(client, h, worker_role["id"], "w2@example.com")
    me = (await client.get("/api/v1/auth/me", headers=worker)).json()
    assert "finance.read" not in me["permissions"]

    new = sorted(set(worker_role["permissions"]) | {"finance.read"})
    r = await client.put(f"/api/v1/roles/{worker_role['id']}", headers=h, json={"permissions": new})
    assert r.status_code == 200, r.text
    assert r.json()["differs_from_default"] is True
    assert "finance.read" in (await client.get("/api/v1/auth/me", headers=worker)).json()["permissions"]

    # and removing one takes it away again
    trimmed = [c for c in new if c != "livestock.read"]
    await client.put(f"/api/v1/roles/{worker_role['id']}", headers=h, json={"permissions": trimmed})
    assert "livestock.read" not in (await client.get("/api/v1/auth/me", headers=worker)).json()["permissions"]


async def test_reset_restores_defaults(client, engine):
    h = await _owner(client, "Roles Farm D", "rolesd@example.com")
    role = (await _roles(client, h))["Accountant"]
    await client.put(f"/api/v1/roles/{role['id']}", headers=h, json={"permissions": ["finance.read"]})
    r = await client.post(f"/api/v1/roles/{role['id']}/reset", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["permissions"] == role["default_permissions"] and r.json()["differs_from_default"] is False


async def test_locked_and_builtin_rules(client, engine):
    h = await _owner(client, "Roles Farm E", "rolese@example.com")
    roles = await _roles(client, h)
    for name in ("Farm Owner", "Customer"):
        assert (await client.put(f"/api/v1/roles/{roles[name]['id']}", headers=h, json={"permissions": []})).status_code == 403
        assert (await client.delete(f"/api/v1/roles/{roles[name]['id']}", headers=h)).status_code == 403
    fw = roles["Farm Worker"]["id"]
    assert (await client.put(f"/api/v1/roles/{fw}", headers=h, json={"name": "Renamed"})).status_code == 422
    assert (await client.delete(f"/api/v1/roles/{fw}", headers=h)).status_code == 403
    assert (await client.post(f"/api/v1/roles/{roles['Customer']['id']}/reset", headers=h)).status_code == 403


async def test_custom_role_lifecycle_and_names(client, engine):
    h = await _owner(client, "Roles Farm F", "rolesf@example.com")
    r = await client.post("/api/v1/roles", headers=h, json={
        "name": "  Dairy Lead ", "description": "Milk team", "permissions": ["dairy.read", "dairy.create", "dairy.read"]})
    assert r.status_code == 201, r.text
    role = r.json()
    assert role["name"] == "Dairy Lead" and role["permissions"] == ["dairy.create", "dairy.read"] and role["is_system"] is False
    # unique, case-insensitive, also against built-in names
    assert (await client.post("/api/v1/roles", headers=h, json={"name": "dairy lead", "permissions": []})).status_code == 409
    assert (await client.post("/api/v1/roles", headers=h, json={"name": "farm worker", "permissions": []})).status_code == 409
    # rename + edit
    r = await client.put(f"/api/v1/roles/{role['id']}", headers=h, json={"name": "Milk Lead", "permissions": ["dairy.read"]})
    assert r.status_code == 200 and r.json()["name"] == "Milk Lead" and r.json()["permissions"] == ["dairy.read"]
    # unknown permission
    assert (await client.put(f"/api/v1/roles/{role['id']}", headers=h, json={"permissions": ["nope.read"]})).status_code == 422
    # in use -> can't delete; free -> can
    await _staff(client, h, role["id"], "milk@example.com")
    assert (await client.delete(f"/api/v1/roles/{role['id']}", headers=h)).status_code == 409
    other = (await client.post("/api/v1/roles", headers=h, json={"name": "Temp", "permissions": []})).json()
    assert (await client.delete(f"/api/v1/roles/{other['id']}", headers=h)).status_code == 204
    assert "Temp" not in await _roles(client, h)


async def test_no_escalation_and_no_self_lockout(client, engine):
    h = await _owner(client, "Roles Farm G", "rolesg@example.com")
    roles = await _roles(client, h)
    # a "Role Admin" who can manage users/roles but holds little else
    admin_role = (await client.post("/api/v1/roles", headers=h, json={
        "name": "Role Admin", "permissions": ["users.manage", "livestock.read"]})).json()
    admin = await _staff(client, h, admin_role["id"], "radmin@example.com")

    # cannot grant what they don't hold (finance.read), on create or edit
    r = await client.post("/api/v1/roles", headers=admin, json={"name": "Sneaky", "permissions": ["finance.read"]})
    assert r.status_code == 403
    r = await client.put(f"/api/v1/roles/{roles['Farm Worker']['id']}", headers=admin,
                         json={"permissions": roles["Farm Worker"]["permissions"] + ["finance.read"]})
    assert r.status_code == 403
    # may grant what they hold, and may leave existing grants alone
    r = await client.put(f"/api/v1/roles/{roles['Farm Worker']['id']}", headers=admin,
                         json={"permissions": roles["Farm Worker"]["permissions"] + ["users.manage"]})
    assert r.status_code == 200, r.text
    # cannot strip their own access to this screen
    r = await client.put(f"/api/v1/roles/{admin_role['id']}", headers=admin, json={"permissions": ["livestock.read"]})
    assert r.status_code == 422
    # the owner still can (the owner's own access is the locked Farm Owner role)
    r = await client.put(f"/api/v1/roles/{admin_role['id']}", headers=h, json={"permissions": ["livestock.read"]})
    assert r.status_code == 200


async def test_audit_trail_and_isolation(client, engine):
    h = await _owner(client, "Roles Farm H", "rolesh@example.com")
    h2 = await _owner(client, "Roles Farm I", "rolesi@example.com")
    role = (await client.post("/api/v1/roles", headers=h, json={"name": "Auditor X", "permissions": ["audit.view"]})).json()
    await client.put(f"/api/v1/roles/{role['id']}", headers=h, json={"permissions": ["audit.view", "reports.view"]})
    await client.delete(f"/api/v1/roles/{role['id']}", headers=h)
    logs = (await client.get("/api/v1/audit-logs", headers=h)).json()
    actions = [l["action"] for l in logs]
    for a in ("role_created", "role_updated", "role_deleted"):
        assert a in actions, actions
    # other org can't see or touch this org's roles
    mine = await _roles(client, h)
    assert "Auditor X" not in await _roles(client, h2)
    fw = mine["Farm Worker"]["id"]
    assert (await client.put(f"/api/v1/roles/{fw}", headers=h2, json={"permissions": []})).status_code == 404
    assert (await client.delete(f"/api/v1/roles/{fw}", headers=h2)).status_code == 404


async def test_existing_roles_endpoint_unchanged(client, engine):
    h = await _owner(client, "Roles Farm J", "rolesj@example.com")
    r = await client.get("/api/v1/users/roles", headers=h)
    assert r.status_code == 200 and set(r.json()[0]) == {"id", "name"}


async def test_every_section_permission_is_a_real_code():
    import re
    from app.modules.identity.permissions import PERMISSIONS
    src = (Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "permissions.ts").read_text()
    codes = {c for c, _ in PERMISSIONS}
    used = set(re.findall(r'permission:\s*"([a-z_]+\.[a-z_]+)"', src))
    assert used and used <= codes, used - codes

"""Editing a team member: details, active switch, password reset, guards and audit trail."""
import pytest

pytestmark = pytest.mark.asyncio

PW = "supersecret123"


async def _owner(client, org="Edit Farm", email="editowner@example.com"):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org, "full_name": "Owner One", "email": email, "password": PW})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def _staff(client, owner_h, email="hand@example.com", name="Field Hand", phone="0700000001"):
    r = await client.post("/api/v1/users", headers=owner_h, json={
        "full_name": name, "email": email, "phone": phone, "password": PW})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _login(client, email, password=PW):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def test_edit_name_email_and_phone(client):
    owner = await _owner(client)
    uid = await _staff(client, owner)
    r = await client.patch(f"/api/v1/users/{uid}", headers=owner, json={
        "full_name": "  Jane Wanjiru ", "email": "Jane@Example.com", "phone": "0711222333"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["full_name"] == "Jane Wanjiru" and body["email"] == "jane@example.com" and body["phone"] == "0711222333"
    assert (await _login(client, "jane@example.com")).status_code == 200      # signs in with the new address
    assert (await _login(client, "hand@example.com")).status_code == 401      # the old one no longer works


async def test_omitted_fields_are_untouched_and_empty_phone_clears_it(client):
    owner = await _owner(client, "Partial Farm", "partial@example.com")
    uid = await _staff(client, owner, "p1@example.com")
    r = await client.patch(f"/api/v1/users/{uid}", headers=owner, json={"full_name": "New Name"})
    assert r.json()["phone"] == "0700000001" and r.json()["email"] == "p1@example.com"
    cleared = await client.patch(f"/api/v1/users/{uid}", headers=owner, json={"phone": ""})
    assert cleared.status_code == 200 and cleared.json()["phone"] is None


async def test_duplicate_email_is_rejected_case_insensitively(client):
    owner = await _owner(client, "Dup Farm", "dupowner@example.com")
    uid = await _staff(client, owner, "dup1@example.com")
    r = await client.patch(f"/api/v1/users/{uid}", headers=owner, json={"email": "DupOwner@example.com"})
    assert r.status_code == 409
    same = await client.patch(f"/api/v1/users/{uid}", headers=owner, json={"email": "dup1@example.com"})
    assert same.status_code == 200                                              # keeping their own address is fine


async def test_deactivate_blocks_sign_in_and_existing_sessions_then_reactivate(client):
    owner = await _owner(client, "Active Farm", "activeowner@example.com")
    uid = await _staff(client, owner, "act1@example.com")
    first = (await _login(client, "act1@example.com")).json()
    worker_h = {"Authorization": f"Bearer {first['access_token']}"}
    assert (await client.get("/api/v1/auth/me", headers=worker_h)).status_code == 200

    off = await client.patch(f"/api/v1/users/{uid}", headers=owner, json={"is_active": False})
    assert off.status_code == 200 and off.json()["is_active"] is False
    assert (await client.get("/api/v1/auth/me", headers=worker_h)).status_code == 401
    assert (await _login(client, "act1@example.com")).status_code == 401
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})).status_code == 401

    on = await client.patch(f"/api/v1/users/{uid}", headers=owner, json={"is_active": True})
    assert on.status_code == 200
    assert (await _login(client, "act1@example.com")).status_code == 200


async def test_cannot_deactivate_yourself(client):
    owner = await _owner(client, "Self Farm", "selfowner@example.com")
    me = (await client.get("/api/v1/auth/me", headers=owner)).json()["user"]["id"]
    r = await client.patch(f"/api/v1/users/{me}", headers=owner, json={"is_active": False})
    assert r.status_code == 400


async def test_new_password_replaces_old_and_signs_the_person_out(client):
    owner = await _owner(client, "Pw Farm", "pwowner@example.com")
    uid = await _staff(client, owner, "pw1@example.com")
    old = (await _login(client, "pw1@example.com")).json()
    r = await client.patch(f"/api/v1/users/{uid}", headers=owner, json={"new_password": "brand-new-pass-1"})
    assert r.status_code == 200
    assert (await _login(client, "pw1@example.com", PW)).status_code == 401
    assert (await _login(client, "pw1@example.com", "brand-new-pass-1")).status_code == 200
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": old["refresh_token"]})).status_code == 401


async def test_password_rules_and_no_resetting_your_own_here(client):
    owner = await _owner(client, "Rule Farm", "ruleowner@example.com")
    uid = await _staff(client, owner, "rule1@example.com")
    assert (await client.patch(f"/api/v1/users/{uid}", headers=owner, json={"new_password": "short"})).status_code == 422
    me = (await client.get("/api/v1/auth/me", headers=owner)).json()["user"]["id"]
    assert (await client.patch(f"/api/v1/users/{me}", headers=owner, json={"new_password": "brand-new-pass-1"})).status_code == 400


async def test_needs_users_manage_and_stays_inside_the_organisation(client):
    owner = await _owner(client, "Guard Farm", "guardowner@example.com")
    uid = await _staff(client, owner, "guard1@example.com")
    worker_h = {"Authorization": f"Bearer {(await _login(client, 'guard1@example.com')).json()['access_token']}"}
    assert (await client.patch(f"/api/v1/users/{uid}", headers=worker_h, json={"full_name": "Hacked"})).status_code == 403

    other = await _owner(client, "Other Farm", "otherowner@example.com")
    assert (await client.patch(f"/api/v1/users/{uid}", headers=other, json={"full_name": "Cross Tenant"})).status_code == 404


async def test_edit_is_audited_without_the_password(client):
    owner = await _owner(client, "Audit Edit Farm", "auditeditowner@example.com")
    uid = await _staff(client, owner, "ae1@example.com")
    await client.patch(f"/api/v1/users/{uid}", headers=owner, json={"full_name": "Renamed Person", "new_password": "brand-new-pass-1"})
    logs = (await client.get("/api/v1/audit-logs?action=user_updated", headers=owner)).json()
    assert len(logs) == 1
    entry = logs[0]
    assert entry["previous_value"] == {"full_name": "Field Hand"}
    assert entry["new_value"] == {"full_name": "Renamed Person", "password_reset": True}
    assert "brand-new-pass-1" not in str(entry)
    # a no-op edit leaves no extra audit row
    await client.patch(f"/api/v1/users/{uid}", headers=owner, json={"full_name": "Renamed Person"})
    assert len((await client.get("/api/v1/audit-logs?action=user_updated", headers=owner)).json()) == 1

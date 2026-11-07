"""Linking an employee record to a login account (and unlinking it again)."""
import pytest

pytestmark = pytest.mark.asyncio

PW = "supersecret123"


async def _owner(client, org, email):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org, "full_name": "Owner One", "email": email, "password": PW})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def _staff(client, h, email, name="Field Hand"):
    r = await client.post("/api/v1/users", headers=h, json={"full_name": name, "email": email, "password": PW})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _employee(client, h, name="James Mwangi", **extra):
    return await client.post("/api/v1/employees", headers=h, json={"full_name": name, **extra})


async def test_create_employee_with_a_login_account(client):
    h = await _owner(client, "Link Farm A", "la@example.com")
    uid = await _staff(client, h, "la1@example.com")
    r = await _employee(client, h, user_id=uid)
    assert r.status_code == 201, r.text
    assert r.json()["user_id"] == uid
    accounts = (await client.get("/api/v1/employees/login-accounts", headers=h)).json()
    linked = next(a for a in accounts if a["id"] == uid)
    assert linked["employee_id"] == r.json()["id"] and linked["employee_number"] == r.json()["employee_number"]


async def test_one_login_account_belongs_to_one_employee(client):
    h = await _owner(client, "Link Farm B", "lb@example.com")
    uid = await _staff(client, h, "lb1@example.com")
    first = await _employee(client, h, "First Person", user_id=uid)
    assert first.status_code == 201
    dup = await _employee(client, h, "Second Person", user_id=uid)
    assert dup.status_code == 409
    other = (await _employee(client, h, "Third Person")).json()
    assert (await client.patch(f"/api/v1/employees/{other['id']}", headers=h, json={"user_id": uid})).status_code == 409


async def test_link_later_keep_it_on_other_edits_and_unlink(client):
    h = await _owner(client, "Link Farm C", "lc@example.com")
    uid = await _staff(client, h, "lc1@example.com")
    emp = (await _employee(client, h)).json()
    assert emp["user_id"] is None

    linked = await client.patch(f"/api/v1/employees/{emp['id']}", headers=h, json={"user_id": uid})
    assert linked.status_code == 200 and linked.json()["user_id"] == uid

    edited = await client.patch(f"/api/v1/employees/{emp['id']}", headers=h, json={"job_title": "Herdsman"})
    assert edited.json()["user_id"] == uid and edited.json()["job_title"] == "Herdsman"      # untouched when omitted

    same = await client.patch(f"/api/v1/employees/{emp['id']}", headers=h, json={"user_id": uid})
    assert same.status_code == 200                                                          # re-saving the same link is fine

    unlinked = await client.patch(f"/api/v1/employees/{emp['id']}", headers=h, json={"user_id": None})
    assert unlinked.status_code == 200 and unlinked.json()["user_id"] is None
    accounts = (await client.get("/api/v1/employees/login-accounts", headers=h)).json()
    assert next(a for a in accounts if a["id"] == uid)["employee_id"] is None              # the account is free again


async def test_cannot_link_another_organisations_user_or_a_customer_account(client):
    h = await _owner(client, "Link Farm D", "ld@example.com")
    other = await _owner(client, "Link Farm E", "le@example.com")
    foreign_uid = await _staff(client, other, "le1@example.com")
    emp = (await _employee(client, h)).json()
    assert (await _employee(client, h, "Cross Tenant", user_id=foreign_uid)).status_code == 404
    assert (await client.patch(f"/api/v1/employees/{emp['id']}", headers=h, json={"user_id": foreign_uid})).status_code == 404

    slug = (await client.get("/api/v1/auth/me", headers=h)).json()["organization"]["slug"]
    reg = await client.post(f"/api/v1/public/{slug}/account/register", json={
        "full_name": "Alice Customer", "email": "alice@ld.example.com", "password": "customerpass123"})
    assert reg.status_code == 201, reg.text
    customer_h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    customer_id = (await client.get("/api/v1/auth/me", headers=customer_h)).json()["user"]["id"]      # the login account's own id
    r = await client.patch(f"/api/v1/employees/{emp['id']}", headers=h, json={"user_id": customer_id})
    assert r.status_code == 400
    accounts = (await client.get("/api/v1/employees/login-accounts", headers=h)).json()
    assert customer_id not in {a["id"] for a in accounts}                                   # customers never appear in the picker


async def test_login_accounts_list_needs_employees_manage_and_is_not_read_as_an_employee_id(client):
    h = await _owner(client, "Link Farm F", "lf@example.com")
    await _staff(client, h, "lf1@example.com", "Zed Worker")
    ok = await client.get("/api/v1/employees/login-accounts", headers=h)
    assert ok.status_code == 200
    names = [a["full_name"] for a in ok.json()]
    assert names == sorted(names) and "Zed Worker" in names and "Owner One" in names
    assert set(ok.json()[0]) == {"id", "full_name", "email", "is_active", "employee_id", "employee_number"}   # no roles, phone or hashes

    worker = (await client.post("/api/v1/auth/login", json={"email": "lf1@example.com", "password": PW})).json()
    worker_h = {"Authorization": f"Bearer {worker['access_token']}"}
    assert (await client.get("/api/v1/employees/login-accounts", headers=worker_h)).status_code == 403

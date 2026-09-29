import pytest

pytestmark = pytest.mark.asyncio


async def _register(client, org_name: str, email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org_name, "full_name": "Owner",
        "email": email, "password": "supersecret123",
    })
    token = reg.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_employee_create_and_number_sequence(client):
    headers = await _register(client, "Employee Farm A", "e1@example.com")

    e1 = await client.post("/api/v1/employees", headers=headers, json={
        "full_name": "James Mwangi", "job_title": "Herdsman", "department": "livestock",
        "employment_type": "full_time", "hire_date": "2024-01-15",
    })
    assert e1.status_code == 201
    assert e1.json()["employee_number"] == "EMP-000001"
    assert e1.json()["employment_status"] == "active"

    e2 = await client.post("/api/v1/employees", headers=headers, json={
        "full_name": "Grace Wanjiru", "job_title": "Milker", "department": "dairy",
    })
    assert e2.json()["employee_number"] == "EMP-000002"


async def test_employment_status_lifecycle(client):
    headers = await _register(client, "Employee Farm B", "e2@example.com")
    emp = await client.post("/api/v1/employees", headers=headers, json={"full_name": "Peter Otieno"})
    emp_id = emp.json()["id"]

    on_leave = await client.patch(f"/api/v1/employees/{emp_id}/status", headers=headers, json={
        "status": "on_leave", "reason": "Annual leave",
    })
    assert on_leave.status_code == 200
    assert on_leave.json()["employment_status"] == "on_leave"

    back = await client.patch(f"/api/v1/employees/{emp_id}/status", headers=headers, json={"status": "active"})
    assert back.status_code == 200

    terminated = await client.patch(f"/api/v1/employees/{emp_id}/status", headers=headers, json={
        "status": "terminated", "reason": "Contract ended", "effective_date": "2026-01-01",
    })
    assert terminated.status_code == 200
    assert terminated.json()["termination_date"] == "2026-01-01"

    # terminated is a terminal state.
    revive = await client.patch(f"/api/v1/employees/{emp_id}/status", headers=headers, json={"status": "active"})
    assert revive.status_code == 409

    detail = await client.get(f"/api/v1/employees/{emp_id}", headers=headers)
    history = detail.json()["status_history"]
    assert [e["to_status"] for e in history] == ["on_leave", "active", "terminated"]


async def test_work_shifts(client):
    headers = await _register(client, "Employee Farm C", "e3@example.com")
    emp = await client.post("/api/v1/employees", headers=headers, json={"full_name": "Mary Achieng"})
    emp_id = emp.json()["id"]

    shift = await client.post(f"/api/v1/employees/{emp_id}/shifts", headers=headers, json={
        "shift_date": "2026-09-06", "start_time": "06:00:00", "end_time": "14:00:00", "notes": "Morning milking",
    })
    assert shift.status_code == 201

    shifts = await client.get(f"/api/v1/employees/{emp_id}/shifts", headers=headers)
    assert len(shifts.json()) == 1
    assert shifts.json()[0]["notes"] == "Morning milking"


async def test_employee_linked_user_must_belong_to_same_org(client):
    headers_a = await _register(client, "Employee Farm D-A", "e4a@example.com")
    headers_b = await _register(client, "Employee Farm D-B", "e4b@example.com")

    me_b = await client.get("/api/v1/auth/me", headers=headers_b)
    user_b_id = me_b.json()["user"]["id"]

    resp = await client.post("/api/v1/employees", headers=headers_a, json={
        "full_name": "Cross Org", "user_id": user_b_id,
    })
    assert resp.status_code == 404


async def test_employee_tenant_isolation(client):
    headers_a = await _register(client, "Employee Farm E-A", "e5a@example.com")
    headers_b = await _register(client, "Employee Farm E-B", "e5b@example.com")

    emp = await client.post("/api/v1/employees", headers=headers_a, json={"full_name": "Secret Employee"})
    emp_id = emp.json()["id"]

    leak = await client.get(f"/api/v1/employees/{emp_id}", headers=headers_b)
    assert leak.status_code == 404


async def test_user_without_grant_cannot_manage_employees(client):
    """Same pattern as test_auth_and_rbac.test_permission_denied_without_grant:
    a user created with no role_ids has zero permissions, confirming
    employees.manage is actually enforced by the router dependency and not
    just declared in the permission catalog."""
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": "Employee Farm F", "full_name": "Owner", "email": "e6@example.com",
        "password": "supersecret123",
    })
    owner_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    await client.post("/api/v1/users", headers=owner_headers, json={
        "full_name": "Worker One", "email": "worker-e6@example.com", "password": "supersecret123",
    })
    worker_login = await client.post("/api/v1/auth/login", json={
        "email": "worker-e6@example.com", "password": "supersecret123",
    })
    worker_headers = {"Authorization": f"Bearer {worker_login.json()['access_token']}"}

    resp = await client.post("/api/v1/employees", headers=worker_headers, json={"full_name": "Should Fail"})
    assert resp.status_code == 403

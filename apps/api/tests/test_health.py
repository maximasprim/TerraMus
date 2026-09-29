import pytest

pytestmark = pytest.mark.asyncio


async def _setup_animal(client, org_name: str, email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org_name, "full_name": "Owner",
        "email": email, "password": "supersecret123",
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    farm = await client.post("/api/v1/farms", json={"name": "Main Farm"}, headers=headers)
    farm_id = farm.json()["id"]
    branch = await client.post(f"/api/v1/farms/{farm_id}/branches", json={"name": "Branch A"}, headers=headers)
    branch_id = branch.json()["id"]
    loc = await client.post(
        f"/api/v1/farms/{farm_id}/branches/{branch_id}/locations",
        json={"name": "Paddock 1", "location_type": "paddock"}, headers=headers,
    )
    loc_id = loc.json()["id"]

    animal = await client.post("/api/v1/livestock", headers=headers, json={
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "COW-H1",
        "species": "cattle", "sex": "female",
        "acquisition_date": "2026-01-01", "acquisition_method": "purchased",
        "acquisition_cost": "30000",
    })
    return headers, animal.json()["id"]


async def test_create_health_record_updates_status_and_timeline(client):
    headers, animal_id = await _setup_animal(client, "Health Farm A", "h1@example.com")

    resp = await client.post(f"/api/v1/livestock/{animal_id}/health", headers=headers, json={
        "record_type": "treatment", "title": "Mastitis treatment",
        "medication": "Antibiotic X", "dosage": "10ml",
        "performed_at": "2026-07-01T09:00:00Z", "follow_up_date": "2026-01-05",
    })
    assert resp.status_code == 201

    animal = (await client.get(f"/api/v1/livestock/{animal_id}", headers=headers)).json()
    assert animal["health_status"] == "under_treatment"

    timeline = (await client.get(f"/api/v1/livestock/{animal_id}/timeline", headers=headers)).json()
    assert any(e["event_type"] == "health:treatment" for e in timeline)


async def test_due_follow_ups_overdue_flag(client):
    headers, animal_id = await _setup_animal(client, "Health Farm B", "h2@example.com")

    await client.post(f"/api/v1/livestock/{animal_id}/health", headers=headers, json={
        "record_type": "vaccination", "title": "FMD Vaccine",
        "performed_at": "2026-01-01T09:00:00Z", "follow_up_date": "2020-01-01",  # deep in the past
    })

    due = (await client.get("/api/v1/health/due?within_days=14", headers=headers)).json()
    assert len(due) == 1
    assert due[0]["is_overdue"] is True


async def test_complete_follow_up_removes_from_due_list(client):
    headers, animal_id = await _setup_animal(client, "Health Farm C", "h3@example.com")

    created = await client.post(f"/api/v1/livestock/{animal_id}/health", headers=headers, json={
        "record_type": "deworming", "title": "Routine deworming",
        "performed_at": "2026-01-01T09:00:00Z", "follow_up_date": "2020-01-01",
    })
    record_id = created.json()["id"]

    before = (await client.get("/api/v1/health/due?within_days=14", headers=headers)).json()
    assert len(before) == 1

    complete = await client.post(f"/api/v1/health/records/{record_id}/complete-follow-up", headers=headers)
    assert complete.status_code == 200
    assert complete.json()["follow_up_completed"] is True

    after = (await client.get("/api/v1/health/due?within_days=14", headers=headers)).json()
    assert len(after) == 0


async def test_health_tenant_isolation(client):
    headers_a, animal_id = await _setup_animal(client, "Health Farm D", "h4a@example.com")
    headers_b, _ = await _setup_animal(client, "Health Farm E", "h4b@example.com")

    leak = await client.get(f"/api/v1/livestock/{animal_id}/health", headers=headers_b)
    assert leak.status_code == 404  # animal itself isn't visible to Org B


async def test_health_create_requires_permission(client):
    headers, animal_id = await _setup_animal(client, "Health Farm F", "h5@example.com")

    # Create a role-less worker (mirrors test_auth_and_rbac pattern)
    await client.post("/api/v1/users", headers=headers, json={
        "full_name": "Worker", "email": "h5worker@example.com", "password": "supersecret123",
    })
    login = await client.post("/api/v1/auth/login", json={
        "email": "h5worker@example.com", "password": "supersecret123",
    })
    worker_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    denied = await client.post(f"/api/v1/livestock/{animal_id}/health", headers=worker_headers, json={
        "record_type": "examination", "title": "Checkup",
    })
    assert denied.status_code == 403

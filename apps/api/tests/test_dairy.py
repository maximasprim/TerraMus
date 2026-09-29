import pytest

pytestmark = pytest.mark.asyncio


async def _setup_cow(client, org_name: str, email: str):
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

    cow = await client.post("/api/v1/livestock", headers=headers, json={
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "COW-1",
        "species": "cattle", "sex": "female",
        "acquisition_date": "2024-01-01", "acquisition_method": "purchased", "acquisition_cost": "50000",
    })
    return headers, cow.json()["id"]


async def test_cannot_start_second_active_cycle(client):
    headers, cow_id = await _setup_cow(client, "Dairy Farm A", "d1@example.com")
    first = await client.post(f"/api/v1/livestock/{cow_id}/dairy/lactation-cycles", headers=headers, json={
        "start_date": "2026-07-01",
    })
    assert first.status_code == 201
    second = await client.post(f"/api/v1/livestock/{cow_id}/dairy/lactation-cycles", headers=headers, json={
        "start_date": "2026-07-02",
    })
    assert second.status_code == 409


async def test_duplicate_session_same_day_rejected(client):
    headers, cow_id = await _setup_cow(client, "Dairy Farm B", "d2@example.com")
    r1 = await client.post(f"/api/v1/livestock/{cow_id}/dairy/milk", headers=headers, json={
        "production_date": "2026-08-10", "session": "morning", "quantity_liters": "12.5",
    })
    assert r1.status_code == 201
    r2 = await client.post(f"/api/v1/livestock/{cow_id}/dairy/milk", headers=headers, json={
        "production_date": "2026-08-10", "session": "morning", "quantity_liters": "5",
    })
    assert r2.status_code == 409


async def test_herd_summary_totals_and_top_producers(client):
    headers, cow_id = await _setup_cow(client, "Dairy Farm C", "d3@example.com")
    await client.post(f"/api/v1/livestock/{cow_id}/dairy/milk", headers=headers, json={
        "production_date": "2026-08-10", "session": "morning", "quantity_liters": "12.5",
    })
    await client.post(f"/api/v1/livestock/{cow_id}/dairy/milk", headers=headers, json={
        "production_date": "2026-08-10", "session": "evening", "quantity_liters": "10.0",
    })
    summary = (await client.get(
        "/api/v1/dairy/summary?for_date=2026-08-10", headers=headers,
    )).json()
    assert summary["total_liters"] == "22.50"
    assert summary["cows_milked"] == 1
    assert summary["top_producers"][0]["animal_id"] == cow_id


async def test_dairy_tenant_isolation(client):
    headers_a, cow_id_a = await _setup_cow(client, "Dairy Iso A", "d4a@example.com")
    headers_b, _ = await _setup_cow(client, "Dairy Iso B", "d4b@example.com")

    leak = await client.get(f"/api/v1/livestock/{cow_id_a}/dairy/milk", headers=headers_b)
    assert leak.status_code == 404

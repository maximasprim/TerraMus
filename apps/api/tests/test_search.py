import pytest

pytestmark = pytest.mark.asyncio


async def _register(client, org_name: str, email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org_name, "full_name": "Owner",
        "email": email, "password": "supersecret123",
    })
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def test_search_finds_animal_by_ear_tag(client):
    headers = await _register(client, "Search Farm A", "s1@example.com")
    farm = await client.post("/api/v1/farms", json={"name": "Main Farm"}, headers=headers)
    farm_id = farm.json()["id"]
    branch = await client.post(f"/api/v1/farms/{farm_id}/branches", json={"name": "B"}, headers=headers)
    branch_id = branch.json()["id"]
    loc = await client.post(
        f"/api/v1/farms/{farm_id}/branches/{branch_id}/locations",
        json={"name": "L", "location_type": "paddock"}, headers=headers,
    )
    loc_id = loc.json()["id"]
    await client.post("/api/v1/livestock", headers=headers, json={
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "SEARCH-COW-1",
        "ear_tag": "TAG-99887", "species": "cattle", "sex": "female",
        "acquisition_date": "2024-01-01", "acquisition_method": "purchased", "acquisition_cost": "40000",
    })

    resp = await client.get("/api/v1/search", params={"q": "99887"}, headers=headers)
    assert resp.status_code == 200
    results = resp.json()
    assert any(r["type"] == "animal" and r["label"] == "SEARCH-COW-1" for r in results)


async def test_search_finds_supplier_and_employee(client):
    headers = await _register(client, "Search Farm B", "s2@example.com")
    await client.post("/api/v1/procurement/suppliers", headers=headers, json={"name": "Nairobi Feeds Co"})
    await client.post("/api/v1/employees", headers=headers, json={"full_name": "Nairobi Otieno"})

    resp = await client.get("/api/v1/search", params={"q": "Nairobi"}, headers=headers)
    types_found = {r["type"] for r in resp.json()}
    assert "supplier" in types_found
    assert "employee" in types_found


async def test_search_respects_tenant_isolation(client):
    headers_a = await _register(client, "Search Farm C-A", "s3a@example.com")
    headers_b = await _register(client, "Search Farm C-B", "s3b@example.com")

    await client.post("/api/v1/procurement/suppliers", headers=headers_a, json={"name": "OnlyInOrgA Traders"})

    leak = await client.get("/api/v1/search", params={"q": "OnlyInOrgA"}, headers=headers_b)
    assert leak.json() == []

    found = await client.get("/api/v1/search", params={"q": "OnlyInOrgA"}, headers=headers_a)
    assert len(found.json()) == 1


async def test_search_requires_permission(client):
    headers = await _register(client, "Search Farm D", "s4@example.com")
    await client.post("/api/v1/users", headers=headers, json={
        "full_name": "No Perms", "email": "noperm-s4@example.com", "password": "supersecret123",
    })
    login = await client.post("/api/v1/auth/login", json={
        "email": "noperm-s4@example.com", "password": "supersecret123",
    })
    worker_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get("/api/v1/search", params={"q": "anything"}, headers=worker_headers)
    assert resp.status_code == 403

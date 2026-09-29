import pytest

pytestmark = pytest.mark.asyncio


async def _setup_dam_sire(client, org_name: str, email: str):
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

    dam = await client.post("/api/v1/livestock", headers=headers, json={
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "DAM-1",
        "species": "cattle", "sex": "female",
        "acquisition_date": "2024-01-01", "acquisition_method": "purchased", "acquisition_cost": "50000",
    })
    sire = await client.post("/api/v1/livestock", headers=headers, json={
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "SIRE-1",
        "species": "cattle", "sex": "male",
        "acquisition_date": "2024-01-01", "acquisition_method": "purchased", "acquisition_cost": "60000",
    })
    return headers, dam.json()["id"], sire.json()["id"]


async def test_breeding_wrong_sex_rejected(client):
    headers, dam_id, sire_id = await _setup_dam_sire(client, "Breeding Sex Farm", "b1@example.com")

    # dam_id must be female - pass the sire's id instead
    resp = await client.post("/api/v1/breeding", headers=headers, json={
        "dam_id": sire_id, "method": "natural", "mating_date": "2026-01-01",
    })
    assert resp.status_code == 400


async def test_full_breeding_to_delivery_flow(client):
    headers, dam_id, sire_id = await _setup_dam_sire(client, "Breeding Flow Farm", "b2@example.com")

    bred = await client.post("/api/v1/breeding", headers=headers, json={
        "dam_id": dam_id, "sire_id": sire_id, "method": "natural",
        "mating_date": "2026-01-01", "expected_delivery_date": "2026-10-01",
    })
    assert bred.status_code == 201
    record_id = bred.json()["id"]

    dam = (await client.get(f"/api/v1/livestock/{dam_id}", headers=headers)).json()
    assert dam["reproductive_status"] == "bred"

    check = await client.post(f"/api/v1/breeding/{record_id}/pregnancy-checks", headers=headers, json={
        "check_date": "2026-02-01", "result": "confirmed",
    })
    assert check.status_code == 200
    assert check.json()["pregnancy_status"] == "confirmed_pregnant"

    dam = (await client.get(f"/api/v1/livestock/{dam_id}", headers=headers)).json()
    assert dam["reproductive_status"] == "pregnant"

    delivery = await client.post(f"/api/v1/breeding/{record_id}/delivery", headers=headers, json={
        "actual_delivery_date": "2026-10-05", "offspring_count": 1,
        "create_offspring_animals": True, "offspring_sex": ["female"],
    })
    assert delivery.status_code == 200
    assert delivery.json()["pregnancy_status"] == "delivered"

    dam = (await client.get(f"/api/v1/livestock/{dam_id}", headers=headers)).json()
    assert dam["reproductive_status"] == "lactating"

    animals = (await client.get("/api/v1/livestock", headers=headers)).json()
    calves = [a for a in animals if a["dam_id"] == dam_id and a["id"] != dam_id]
    assert len(calves) == 1
    assert calves[0]["sire_id"] == sire_id
    assert calves[0]["category"] == "calf"


async def test_cannot_deliver_twice(client):
    headers, dam_id, sire_id = await _setup_dam_sire(client, "Breeding Twice Farm", "b3@example.com")
    bred = await client.post("/api/v1/breeding", headers=headers, json={
        "dam_id": dam_id, "method": "natural", "mating_date": "2026-01-01",
    })
    record_id = bred.json()["id"]
    await client.post(f"/api/v1/breeding/{record_id}/pregnancy-checks", headers=headers, json={
        "check_date": "2026-02-01", "result": "confirmed",
    })
    first = await client.post(f"/api/v1/breeding/{record_id}/delivery", headers=headers, json={
        "actual_delivery_date": "2026-10-05", "offspring_count": 1, "create_offspring_animals": False,
    })
    assert first.status_code == 200

    second = await client.post(f"/api/v1/breeding/{record_id}/delivery", headers=headers, json={
        "actual_delivery_date": "2026-10-06", "offspring_count": 1, "create_offspring_animals": False,
    })
    assert second.status_code == 409


async def test_breeding_tenant_isolation(client):
    headers_a, dam_id_a, _ = await _setup_dam_sire(client, "Breeding Iso A", "b4a@example.com")
    headers_b, _, _ = await _setup_dam_sire(client, "Breeding Iso B", "b4b@example.com")

    bred = await client.post("/api/v1/breeding", headers=headers_a, json={
        "dam_id": dam_id_a, "method": "natural", "mating_date": "2026-01-01",
    })
    record_id = bred.json()["id"]

    leak = await client.get(f"/api/v1/breeding/{record_id}", headers=headers_b)
    assert leak.status_code == 404

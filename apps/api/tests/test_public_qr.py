import pytest

pytestmark = pytest.mark.asyncio


async def _setup_animal(client, org_name: str, email: str, list_for_sale: bool = True):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org_name, "full_name": "Owner",
        "email": email, "password": "supersecret123",
    })
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    org_slug = (await client.get("/api/v1/auth/me", headers=headers)).json()["organization"]["slug"]

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
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "QRPUB-COW",
        "species": "cattle", "breed": "Holstein", "sex": "female",
        "acquisition_date": "2024-01-01", "acquisition_method": "purchased", "acquisition_cost": "40000",
    })
    animal_id = animal.json()["id"]

    slug = None
    if list_for_sale:
        await client.post(f"/api/v1/livestock/{animal_id}/status", headers=headers, json={"status": "for_sale"})
        listing = await client.post("/api/v1/listings", headers=headers, json={
            "animal_id": animal_id, "title": "Holstein Cow", "pricing_type": "fixed", "price": "60000",
        })
        slug = listing.json()["slug"]

    return headers, org_slug, animal_id, slug


async def test_qr_profile_is_public_and_narrow(client):
    """Spec §38: no auth required, and only the allowlisted fields - never
    acquisition_cost, current_value, or other internal detail."""
    _, org_slug, animal_id, slug = await _setup_animal(client, "QR Public Farm A", "qrpub1@example.com")

    resp = await client.get(f"/api/v1/public/{org_slug}/animals/{animal_id}/qr-profile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["animal_number"] == "QRPUB-COW"
    assert body["species"] == "cattle"
    assert body["is_for_sale"] is True
    assert body["listing_slug"] == slug
    assert "acquisition_cost" not in body
    assert "current_value" not in body


async def test_qr_profile_for_animal_not_listed_for_sale(client):
    _, org_slug, animal_id, _ = await _setup_animal(client, "QR Public Farm B", "qrpub2@example.com", list_for_sale=False)

    resp = await client.get(f"/api/v1/public/{org_slug}/animals/{animal_id}/qr-profile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_for_sale"] is False
    assert body["listing_slug"] is None


async def test_qr_profile_tenant_isolation(client):
    _, org_slug_a, animal_id, _ = await _setup_animal(client, "QR Public Farm C-A", "qrpub3a@example.com")

    reg_b = await client.post("/api/v1/auth/register", json={
        "organization_name": "QR Public Farm C-B", "full_name": "Owner",
        "email": "qrpub3b@example.com", "password": "supersecret123",
    })
    headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}
    org_slug_b = (await client.get("/api/v1/auth/me", headers=headers_b)).json()["organization"]["slug"]

    leak = await client.get(f"/api/v1/public/{org_slug_b}/animals/{animal_id}/qr-profile")
    assert leak.status_code == 404

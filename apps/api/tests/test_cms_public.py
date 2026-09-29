import pytest

pytestmark = pytest.mark.asyncio


async def _setup_org(client, org_name: str, email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org_name, "full_name": "Owner",
        "email": email, "password": "supersecret123",
    })
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    return headers, me["organization"]["slug"]


async def _setup_animal_and_listing(client, headers, price="90000"):
    farm = await client.post("/api/v1/farms", json={"name": "Main Farm", "county": "Nakuru"}, headers=headers)
    farm_id = farm.json()["id"]
    branch = await client.post(f"/api/v1/farms/{farm_id}/branches", json={"name": "Branch A"}, headers=headers)
    branch_id = branch.json()["id"]
    loc = await client.post(
        f"/api/v1/farms/{farm_id}/branches/{branch_id}/locations",
        json={"name": "Paddock 1", "location_type": "paddock"}, headers=headers,
    )
    loc_id = loc.json()["id"]

    animal = await client.post("/api/v1/livestock", headers=headers, json={
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "HOLSTEIN-PUB",
        "species": "cattle", "breed": "Holstein", "sex": "female",
        "acquisition_date": "2024-01-01", "acquisition_method": "purchased",
        "acquisition_cost": "40000", "current_value": "75000",
    })
    animal_id = animal.json()["id"]
    await client.post(f"/api/v1/livestock/{animal_id}/status", headers=headers, json={"status": "for_sale"})
    listing = await client.post("/api/v1/listings", headers=headers, json={
        "animal_id": animal_id, "title": "Healthy Holstein Cow", "pricing_type": "fixed", "price": price,
    })
    return animal_id, listing.json()


async def test_public_endpoints_require_no_auth(client):
    headers, org_slug = await _setup_org(client, "CMS Farm A", "cms1@example.com")
    resp = await client.get(f"/api/v1/public/{org_slug}/profile")
    assert resp.status_code == 200  # no Authorization header sent at all


async def test_only_published_content_is_public(client):
    headers, org_slug = await _setup_org(client, "CMS Farm B", "cms2@example.com")
    await client.post("/api/v1/cms/testimonials", headers=headers, json={
        "customer_name": "Published Alice", "quote": "Great!", "is_published": True,
    })
    await client.post("/api/v1/cms/testimonials", headers=headers, json={
        "customer_name": "Draft Ghost", "quote": "not approved", "is_published": False,
    })

    public = (await client.get(f"/api/v1/public/{org_slug}/testimonials")).json()
    assert len(public) == 1
    assert public[0]["customer_name"] == "Published Alice"

    staff_view = (await client.get("/api/v1/cms/testimonials", headers=headers)).json()
    assert len(staff_view) == 2  # staff sees both


async def test_public_listing_never_leaks_internal_cost_fields(client):
    headers, org_slug = await _setup_org(client, "CMS Farm C", "cms3@example.com")
    await _setup_animal_and_listing(client, headers)

    public = (await client.get(f"/api/v1/public/{org_slug}/listings")).json()
    assert len(public) == 1
    listing = public[0]
    # Only the allowlisted public fields should ever appear.
    forbidden_keys = {"acquisition_cost", "current_value", "supplier", "previous_owner", "notes", "location_id"}
    assert not forbidden_keys & set(listing.keys())
    assert listing["price"] == "90000.00"  # price itself is fine to show - it's the sale price


async def test_listing_deactivates_when_animal_reserved(client):
    """Regression test for the bug found during Phase 7 live testing: nothing
    previously deactivated a Listing when its animal left 'for_sale', so the
    public catalog could show an animal that was actually already spoken for."""
    headers, org_slug = await _setup_org(client, "CMS Farm D", "cms4@example.com")
    animal_id, listing = await _setup_animal_and_listing(client, headers)

    before = (await client.get(f"/api/v1/public/{org_slug}/listings")).json()
    assert len(before) == 1

    customer = await client.post("/api/v1/customers", headers=headers, json={"name": "Alice"})
    await client.post("/api/v1/reservations", headers=headers, json={
        "animal_id": animal_id, "customer_id": customer.json()["id"],
        "reservation_date": "2026-08-13", "expiry_date": "2026-08-20",
    })

    after = (await client.get(f"/api/v1/public/{org_slug}/listings")).json()
    assert len(after) == 0


async def test_listing_deactivates_when_ordered_directly(client):
    headers, org_slug = await _setup_org(client, "CMS Farm E", "cms5@example.com")
    animal_id, listing = await _setup_animal_and_listing(client, headers)

    customer = await client.post("/api/v1/customers", headers=headers, json={"name": "Bob"})
    await client.post("/api/v1/orders", headers=headers, json={
        "customer_id": customer.json()["id"], "items": [{"animal_id": animal_id, "price": "90000"}],
    })

    after = (await client.get(f"/api/v1/public/{org_slug}/listings")).json()
    assert len(after) == 0


async def test_public_listing_detail_by_slug(client):
    headers, org_slug = await _setup_org(client, "CMS Farm F", "cms6@example.com")
    _, listing = await _setup_animal_and_listing(client, headers)

    detail = await client.get(f"/api/v1/public/{org_slug}/listings/{listing['slug']}")
    assert detail.status_code == 200
    assert detail.json()["breed"] == "Holstein"


async def test_nonexistent_org_slug_404s(client):
    resp = await client.get("/api/v1/public/does-not-exist-at-all/profile")
    assert resp.status_code == 404


async def test_cms_requires_permission(client):
    headers, org_slug = await _setup_org(client, "CMS Farm G", "cms7@example.com")
    await client.post("/api/v1/users", headers=headers, json={
        "full_name": "Worker", "email": "cms7worker@example.com", "password": "supersecret123",
    })
    login = await client.post("/api/v1/auth/login", json={
        "email": "cms7worker@example.com", "password": "supersecret123",
    })
    worker_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    denied = await client.post("/api/v1/cms/blog", headers=worker_headers, json={
        "title": "Unauthorized post", "body": "should not work",
    })
    assert denied.status_code == 403


async def test_cms_tenant_isolation(client):
    headers_a, org_slug_a = await _setup_org(client, "CMS Iso A", "cms8a@example.com")
    headers_b, _ = await _setup_org(client, "CMS Iso B", "cms8b@example.com")

    await client.post("/api/v1/cms/testimonials", headers=headers_a, json={
        "customer_name": "Org A Customer", "quote": "hi", "is_published": True,
    })

    public_a = (await client.get(f"/api/v1/public/{org_slug_a}/testimonials")).json()
    assert len(public_a) == 1

    staff_b_view = (await client.get("/api/v1/cms/testimonials", headers=headers_b)).json()
    assert len(staff_b_view) == 0  # Org B's staff sees none of Org A's content

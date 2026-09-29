import hashlib
import hmac
import json

import pytest

from app.core.config import get_settings

pytestmark = pytest.mark.asyncio
settings = get_settings()


def _sign(body: bytes) -> str:
    return hmac.new(settings.MOCK_PAYMENT_SECRET.encode(), body, hashlib.sha256).hexdigest()


async def _setup_listing(client, org_name: str, email: str, price: str = "85000"):
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
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "GUEST-COW",
        "species": "cattle", "breed": "Holstein", "sex": "female",
        "acquisition_date": "2024-01-01", "acquisition_method": "purchased", "acquisition_cost": "40000",
    })
    animal_id = animal.json()["id"]
    await client.post(f"/api/v1/livestock/{animal_id}/status", headers=headers, json={"status": "for_sale"})

    listing = await client.post("/api/v1/listings", headers=headers, json={
        "animal_id": animal_id, "title": "Healthy Holstein Cow", "pricing_type": "fixed", "price": price,
    })
    return headers, org_slug, animal_id, listing.json()["slug"]


async def test_guest_can_check_out_with_no_auth(client):
    headers, org_slug, animal_id, slug = await _setup_listing(client, "Guest Farm A", "gc1@example.com")

    order = await client.post(f"/api/v1/public/{org_slug}/orders", json={
        "customer_name": "Jane Guest", "customer_email": "jane@gc1.example.com",
        "items": [{"listing_slug": slug}],
    })
    assert order.status_code == 201
    body = order.json()
    assert body["status"] == "pending"
    assert body["total_amount"] == "85000.00"

    animal = (await client.get(f"/api/v1/livestock/{animal_id}", headers=headers)).json()
    assert animal["status"] == "reserved"

    listings = (await client.get(f"/api/v1/public/{org_slug}/listings")).json()
    assert len(listings) == 0  # deactivated, same fix as Phase 7


async def test_guest_checkout_creates_real_customer_record(client):
    headers, org_slug, _, slug = await _setup_listing(client, "Guest Farm B", "gc2@example.com")

    await client.post(f"/api/v1/public/{org_slug}/orders", json={
        "customer_name": "Jane Guest", "customer_email": "jane@gc2.example.com",
        "items": [{"listing_slug": slug}],
    })

    customers = (await client.get("/api/v1/customers", headers=headers)).json()
    assert len(customers) == 1
    assert customers[0]["email"] == "jane@gc2.example.com"


async def test_guest_order_lookup_requires_matching_email(client):
    _, org_slug, _, slug = await _setup_listing(client, "Guest Farm C", "gc3@example.com")
    order = await client.post(f"/api/v1/public/{org_slug}/orders", json={
        "customer_name": "Jane Guest", "customer_email": "jane@gc3.example.com",
        "items": [{"listing_slug": slug}],
    })
    order_id = order.json()["order_id"]

    wrong = await client.get(f"/api/v1/public/{org_slug}/orders/{order_id}", params={"email": "wrong@example.com"})
    assert wrong.status_code == 404

    right = await client.get(f"/api/v1/public/{org_slug}/orders/{order_id}", params={"email": "jane@gc3.example.com"})
    assert right.status_code == 200


async def test_second_guest_cannot_order_reserved_animal(client):
    _, org_slug, _, slug = await _setup_listing(client, "Guest Farm D", "gc4@example.com")
    await client.post(f"/api/v1/public/{org_slug}/orders", json={
        "customer_name": "Jane Guest", "customer_email": "jane@gc4.example.com",
        "items": [{"listing_slug": slug}],
    })

    second = await client.post(f"/api/v1/public/{org_slug}/orders", json={
        "customer_name": "Bob Guest", "customer_email": "bob@gc4.example.com",
        "items": [{"listing_slug": slug}],
    })
    assert second.status_code == 404  # listing no longer active/found


async def test_guest_payment_flow_marks_order_paid(client):
    headers, org_slug, animal_id, slug = await _setup_listing(client, "Guest Farm E", "gc5@example.com")
    order = await client.post(f"/api/v1/public/{org_slug}/orders", json={
        "customer_name": "Jane Guest", "customer_email": "jane@gc5.example.com",
        "items": [{"listing_slug": slug}],
    })
    order_id = order.json()["order_id"]

    await client.post(f"/api/v1/orders/{order_id}/status", headers=headers, json={"status": "payment_pending"})

    payment = await client.post(f"/api/v1/public/{org_slug}/orders/{order_id}/pay/mock", json={
        "phone_or_token": "254700111222", "email": "jane@gc5.example.com",
    })
    assert payment.status_code == 201
    ref = payment.json()["provider_reference"]

    body = json.dumps({"event_id": "evt-guest-1", "provider_reference": ref, "status": "successful"}).encode()
    webhook = await client.post("/api/v1/payments/webhooks/mock", content=body, headers={
        "Content-Type": "application/json", "X-Mock-Signature": _sign(body),
    })
    assert webhook.json()["status"] == "processed"

    animal = (await client.get(f"/api/v1/livestock/{animal_id}", headers=headers)).json()
    assert animal["status"] == "sold"


async def test_guest_payment_requires_matching_email(client):
    _, org_slug, _, slug = await _setup_listing(client, "Guest Farm F", "gc6@example.com")
    order = await client.post(f"/api/v1/public/{org_slug}/orders", json={
        "customer_name": "Jane Guest", "customer_email": "jane@gc6.example.com",
        "items": [{"listing_slug": slug}],
    })
    order_id = order.json()["order_id"]

    denied = await client.post(f"/api/v1/public/{org_slug}/orders/{order_id}/pay/mock", json={
        "phone_or_token": "254700111222", "email": "attacker@example.com",
    })
    assert denied.status_code == 404


async def test_price_on_request_listing_rejects_direct_checkout(client):
    _, org_slug, _, slug = await _setup_listing(client, "Guest Farm G", "gc7@example.com")
    # Re-list with price_on_request by creating a fresh animal/listing.
    headers = None
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": "POR Farm", "full_name": "Owner",
        "email": "por@example.com", "password": "supersecret123",
    })
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    org_slug2 = (await client.get("/api/v1/auth/me", headers=headers)).json()["organization"]["slug"]
    farm = await client.post("/api/v1/farms", json={"name": "Farm"}, headers=headers)
    farm_id = farm.json()["id"]
    branch = await client.post(f"/api/v1/farms/{farm_id}/branches", json={"name": "B"}, headers=headers)
    branch_id = branch.json()["id"]
    loc = await client.post(
        f"/api/v1/farms/{farm_id}/branches/{branch_id}/locations",
        json={"name": "L", "location_type": "paddock"}, headers=headers,
    )
    loc_id = loc.json()["id"]
    animal = await client.post("/api/v1/livestock", headers=headers, json={
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "POR-COW",
        "species": "cattle", "sex": "female", "acquisition_date": "2024-01-01",
        "acquisition_method": "purchased", "acquisition_cost": "40000",
    })
    animal_id = animal.json()["id"]
    await client.post(f"/api/v1/livestock/{animal_id}/status", headers=headers, json={"status": "for_sale"})
    listing = await client.post("/api/v1/listings", headers=headers, json={
        "animal_id": animal_id, "title": "Prize Bull", "pricing_type": "price_on_request",
    })
    por_slug = listing.json()["slug"]

    resp = await client.post(f"/api/v1/public/{org_slug2}/orders", json={
        "customer_name": "Jane Guest", "customer_email": "jane@por.example.com",
        "items": [{"listing_slug": por_slug}],
    })
    assert resp.status_code == 400

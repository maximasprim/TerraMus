import asyncio
import pytest

pytestmark = pytest.mark.asyncio


async def _setup_animal_for_sale(client, org_name: str, email: str):
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
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "COW-SALE-1",
        "species": "cattle", "sex": "female",
        "acquisition_date": "2024-01-01", "acquisition_method": "purchased", "acquisition_cost": "40000",
    })
    animal_id = animal.json()["id"]
    await client.post(f"/api/v1/livestock/{animal_id}/status", headers=headers, json={"status": "for_sale"})
    return headers, animal_id


async def _make_customer(client, headers, name: str, email: str):
    resp = await client.post("/api/v1/customers", headers=headers, json={"name": name, "email": email})
    return resp.json()["id"]


async def test_duplicate_active_listing_rejected(client):
    headers, animal_id = await _setup_animal_for_sale(client, "Commerce Farm A", "c1@example.com")
    first = await client.post("/api/v1/listings", headers=headers, json={
        "animal_id": animal_id, "title": "Nice Cow", "pricing_type": "fixed", "price": "80000",
    })
    assert first.status_code == 201
    second = await client.post("/api/v1/listings", headers=headers, json={
        "animal_id": animal_id, "title": "Nice Cow Again", "pricing_type": "fixed", "price": "75000",
    })
    assert second.status_code == 409


async def test_reservation_blocks_second_customer(client):
    headers, animal_id = await _setup_animal_for_sale(client, "Commerce Farm B", "c2@example.com")
    alice_id = await _make_customer(client, headers, "Alice", "alice@c2.example.com")
    bob_id = await _make_customer(client, headers, "Bob", "bob@c2.example.com")

    r1 = await client.post("/api/v1/reservations", headers=headers, json={
        "animal_id": animal_id, "customer_id": alice_id,
        "reservation_date": "2026-08-10", "expiry_date": "2026-08-17",
    })
    assert r1.status_code == 201

    r2 = await client.post("/api/v1/reservations", headers=headers, json={
        "animal_id": animal_id, "customer_id": bob_id,
        "reservation_date": "2026-08-10", "expiry_date": "2026-08-17",
    })
    assert r2.status_code == 409


async def test_concurrent_reservations_only_one_wins(client):
    """The actual point of the row lock: fire two reservation requests at the
    same animal genuinely concurrently and confirm exactly one succeeds."""
    headers, animal_id = await _setup_animal_for_sale(client, "Commerce Farm Concurrency", "cconcurrent@example.com")
    alice_id = await _make_customer(client, headers, "Alice", "alice@cc.example.com")
    bob_id = await _make_customer(client, headers, "Bob", "bob@cc.example.com")

    async def reserve(customer_id):
        return await client.post("/api/v1/reservations", headers=headers, json={
            "animal_id": animal_id, "customer_id": customer_id,
            "reservation_date": "2026-08-10", "expiry_date": "2026-08-17",
        })

    results = await asyncio.gather(reserve(alice_id), reserve(bob_id), return_exceptions=True)
    statuses = sorted(r.status_code for r in results if not isinstance(r, Exception))
    assert statuses == [201, 409]

    animal = (await client.get(f"/api/v1/livestock/{animal_id}", headers=headers)).json()
    assert animal["status"] == "reserved"


async def test_order_blocked_when_reserved_by_other_customer(client):
    headers, animal_id = await _setup_animal_for_sale(client, "Commerce Farm C", "c3@example.com")
    alice_id = await _make_customer(client, headers, "Alice", "alice@c3.example.com")
    bob_id = await _make_customer(client, headers, "Bob", "bob@c3.example.com")

    await client.post("/api/v1/reservations", headers=headers, json={
        "animal_id": animal_id, "customer_id": alice_id,
        "reservation_date": "2026-08-10", "expiry_date": "2026-08-17",
    })

    order = await client.post("/api/v1/orders", headers=headers, json={
        "customer_id": bob_id, "items": [{"animal_id": animal_id, "price": "80000"}],
    })
    assert order.status_code == 409


async def test_full_order_lifecycle_marks_animal_sold(client):
    headers, animal_id = await _setup_animal_for_sale(client, "Commerce Farm D", "c4@example.com")
    alice_id = await _make_customer(client, headers, "Alice", "alice@c4.example.com")

    order = await client.post("/api/v1/orders", headers=headers, json={
        "customer_id": alice_id, "items": [{"animal_id": animal_id, "price": "80000"}],
    })
    assert order.status_code == 201
    order_id = order.json()["id"]

    animal = (await client.get(f"/api/v1/livestock/{animal_id}", headers=headers)).json()
    assert animal["status"] == "reserved"

    await client.post(f"/api/v1/orders/{order_id}/status", headers=headers, json={"status": "payment_pending"})
    paid = await client.post(f"/api/v1/orders/{order_id}/status", headers=headers, json={"status": "paid"})
    assert paid.status_code == 200

    animal = (await client.get(f"/api/v1/livestock/{animal_id}", headers=headers)).json()
    assert animal["status"] == "sold"

    # Terminal-ish guard: can't go backwards from paid to pending.
    backwards = await client.post(f"/api/v1/orders/{order_id}/status", headers=headers, json={"status": "pending"})
    assert backwards.status_code == 409


async def test_cancelling_order_releases_animal(client):
    headers, animal_id = await _setup_animal_for_sale(client, "Commerce Farm E", "c5@example.com")
    alice_id = await _make_customer(client, headers, "Alice", "alice@c5.example.com")

    order = await client.post("/api/v1/orders", headers=headers, json={
        "customer_id": alice_id, "items": [{"animal_id": animal_id, "price": "80000"}],
    })
    order_id = order.json()["id"]

    cancel = await client.post(f"/api/v1/orders/{order_id}/status", headers=headers, json={"status": "cancelled"})
    assert cancel.status_code == 200

    animal = (await client.get(f"/api/v1/livestock/{animal_id}", headers=headers)).json()
    assert animal["status"] == "for_sale"


async def test_commerce_tenant_isolation(client):
    headers_a, animal_id_a = await _setup_animal_for_sale(client, "Commerce Iso A", "c6a@example.com")
    headers_b, _ = await _setup_animal_for_sale(client, "Commerce Iso B", "c6b@example.com")

    listing = await client.post("/api/v1/listings", headers=headers_a, json={
        "animal_id": animal_id_a, "title": "Cow", "pricing_type": "fixed", "price": "80000",
    })
    listing_id = listing.json()["id"]

    leak = await client.get(f"/api/v1/listings/{listing_id}", headers=headers_b)
    assert leak.status_code == 404


async def test_update_listing_price_and_description(client):
    headers, animal_id = await _setup_animal_for_sale(client, "Edit Listing Farm", "editlisting@example.com")
    listing = await client.post("/api/v1/listings", headers=headers, json={
        "animal_id": animal_id, "title": "Original Title", "pricing_type": "fixed", "price": "50000",
    })
    listing_id = listing.json()["id"]
    original_slug = listing.json()["slug"]

    updated = await client.patch(f"/api/v1/listings/{listing_id}", headers=headers, json={
        "price": "55000", "description": "Now includes vaccination records", "featured": True,
    })
    assert updated.status_code == 200
    body = updated.json()
    assert body["price"] == "55000.00"
    assert body["description"] == "Now includes vaccination records"
    assert body["featured"] is True
    assert body["title"] == "Original Title"  # untouched field preserved
    assert body["slug"] == original_slug  # editing never changes the SEO slug


async def test_list_reservations(client):
    headers, animal_id = await _setup_animal_for_sale(client, "Reservation List Farm", "reslist@example.com")
    customer = await client.post("/api/v1/customers", headers=headers, json={"name": "Reserver"})
    await client.post("/api/v1/reservations", headers=headers, json={
        "animal_id": animal_id, "customer_id": customer.json()["id"],
        "reservation_date": "2026-01-01", "expiry_date": "2026-01-10",
    })
    resp = await client.get("/api/v1/reservations", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["status"] == "active"

    filtered = await client.get("/api/v1/reservations", headers=headers, params={"status": "cancelled"})
    assert filtered.json() == []

import pytest

pytestmark = pytest.mark.asyncio


async def _setup_listing(client, org_name: str, email: str, price: str = "85000"):
    """Same helper as tests/test_guest_checkout.py - kept in sync deliberately
    rather than importing across test modules, matching how test files in
    this codebase don't share fixtures beyond conftest.py's client/db setup."""
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
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "ACCT-COW",
        "species": "cattle", "breed": "Holstein", "sex": "female",
        "acquisition_date": "2024-01-01", "acquisition_method": "purchased", "acquisition_cost": "40000",
    })
    animal_id = animal.json()["id"]
    await client.post(f"/api/v1/livestock/{animal_id}/status", headers=headers, json={"status": "for_sale"})

    listing = await client.post("/api/v1/listings", headers=headers, json={
        "animal_id": animal_id, "title": "Healthy Holstein Cow", "pricing_type": "fixed", "price": price,
    })
    return headers, org_slug, animal_id, listing.json()["slug"]


async def test_register_then_login_via_existing_auth_endpoint(client):
    """No separate customer-login endpoint was built - a customer account
    logs in through the exact same POST /api/v1/auth/login every staff user
    uses, since authenticate() doesn't care about role (see
    docs/architecture.md Phase 15 note)."""
    _, org_slug, _, _ = await _setup_listing(client, "Account Farm A", "acc1@example.com")

    reg = await client.post(f"/api/v1/public/{org_slug}/account/register", json={
        "full_name": "Alice Customer", "email": "alice@acc1.example.com", "password": "customerpass123",
    })
    assert reg.status_code == 201
    assert "access_token" in reg.json()

    login = await client.post("/api/v1/auth/login", json={
        "email": "alice@acc1.example.com", "password": "customerpass123",
    })
    assert login.status_code == 200
    customer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    me = await client.get("/api/v1/account/me", headers=customer_headers)
    assert me.status_code == 200
    assert me.json()["full_name"] == "Alice Customer"
    assert me.json()["email"] == "alice@acc1.example.com"


async def test_registering_with_email_already_used_for_guest_checkout_links_history(client):
    """Spec §69's own phrasing: 'Allow account creation after purchase.'
    A customer who already ordered as a guest and later registers with the
    same email should see that order in their account, not a fresh blank
    profile - proves find_or_create_by_contact is really being reused."""
    headers, org_slug, _, slug = await _setup_listing(client, "Account Farm B", "acc2@example.com")

    guest_order = await client.post(f"/api/v1/public/{org_slug}/orders", json={
        "customer_name": "Bob Guest", "customer_email": "bob@acc2.example.com",
        "items": [{"listing_slug": slug}],
    })
    assert guest_order.status_code == 201
    order_id = guest_order.json()["order_id"]

    reg = await client.post(f"/api/v1/public/{org_slug}/account/register", json={
        "full_name": "Bob Guest", "email": "bob@acc2.example.com", "password": "customerpass123",
    })
    customer_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    orders = await client.get("/api/v1/account/orders", headers=customer_headers)
    assert orders.status_code == 200
    assert len(orders.json()) == 1
    assert orders.json()[0]["id"] == order_id

    detail = await client.get(f"/api/v1/account/orders/{order_id}", headers=customer_headers)
    assert detail.status_code == 200

    # Still only one Customer CRM record - not a duplicate.
    customers = (await client.get("/api/v1/customers", headers=headers)).json()
    assert len(customers) == 1


async def test_duplicate_email_registration_rejected(client):
    _, org_slug, _, _ = await _setup_listing(client, "Account Farm C", "acc3@example.com")
    first = await client.post(f"/api/v1/public/{org_slug}/account/register", json={
        "full_name": "Carol Customer", "email": "carol@acc3.example.com", "password": "customerpass123",
    })
    assert first.status_code == 201
    second = await client.post(f"/api/v1/public/{org_slug}/account/register", json={
        "full_name": "Carol Again", "email": "carol@acc3.example.com", "password": "differentpass123",
    })
    assert second.status_code == 409


async def test_customer_cannot_see_another_customers_orders(client):
    _, org_slug, _, slug = await _setup_listing(client, "Account Farm D", "acc4@example.com")

    order = await client.post(f"/api/v1/public/{org_slug}/orders", json={
        "customer_name": "Dana Guest", "customer_email": "dana@acc4.example.com",
        "items": [{"listing_slug": slug}],
    })
    order_id = order.json()["order_id"]

    reg = await client.post(f"/api/v1/public/{org_slug}/account/register", json={
        "full_name": "Eve Customer", "email": "eve@acc4.example.com", "password": "customerpass123",
    })
    eve_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    leak = await client.get(f"/api/v1/account/orders/{order_id}", headers=eve_headers)
    assert leak.status_code == 404

    eve_orders = await client.get("/api/v1/account/orders", headers=eve_headers)
    assert eve_orders.json() == []


async def test_staff_account_cannot_use_customer_portal(client):
    """A staff (Farm Owner) user has customer_id=None - the /account/*
    endpoints must reject it rather than silently returning nothing useful."""
    headers, org_slug, _, _ = await _setup_listing(client, "Account Farm E", "acc5@example.com")

    resp = await client.get("/api/v1/account/me", headers=headers)
    assert resp.status_code == 403


async def test_customer_account_has_no_staff_permissions(client):
    """The Customer role grants zero RBAC permissions (identity/permissions.py)
    - confirms a customer login can't reach staff endpoints just because it
    has a valid token."""
    _, org_slug, _, _ = await _setup_listing(client, "Account Farm F", "acc6@example.com")
    reg = await client.post(f"/api/v1/public/{org_slug}/account/register", json={
        "full_name": "Frank Customer", "email": "frank@acc6.example.com", "password": "customerpass123",
    })
    customer_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    resp = await client.get("/api/v1/employees", headers=customer_headers)
    assert resp.status_code == 403


async def test_order_detail_surfaces_invoice_and_payments(client):
    """Spec §16: 'payments, invoices' - closed this session (previously
    order status/items only, per docs/architecture.md's Phase 15 note)."""
    headers, org_slug, _, slug = await _setup_listing(client, "Account Farm G", "acc7@example.com")

    guest_order = await client.post(f"/api/v1/public/{org_slug}/orders", json={
        "customer_name": "Grace Guest", "customer_email": "grace@acc7.example.com",
        "items": [{"listing_slug": slug}],
    })
    order_id = guest_order.json()["order_id"]

    import hashlib
    import hmac
    import json as json_module
    from app.core.config import get_settings
    settings = get_settings()

    payment = await client.post(f"/api/v1/public/{org_slug}/orders/{order_id}/pay", json={
        "phone_or_token": "254700000000", "email": "grace@acc7.example.com",
    })
    ref = payment.json()["provider_reference"]
    body = json_module.dumps({"event_id": "evt-acct-invoice", "provider_reference": ref, "status": "successful"}).encode()
    signature = hmac.new(settings.MOCK_PAYMENT_SECRET.encode(), body, hashlib.sha256).hexdigest()
    await client.post("/api/v1/payments/webhooks/mock", content=body, headers={
        "Content-Type": "application/json", "X-Mock-Signature": signature,
    })

    reg = await client.post(f"/api/v1/public/{org_slug}/account/register", json={
        "full_name": "Grace Guest", "email": "grace@acc7.example.com", "password": "customerpass123",
    })
    customer_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    detail = await client.get(f"/api/v1/account/orders/{order_id}", headers=customer_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["invoice"] is not None
    assert body["invoice"]["invoice_number"].startswith("INV-")
    assert len(body["payments"]) == 1
    assert body["payments"][0]["status"] == "successful"

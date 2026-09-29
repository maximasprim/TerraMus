import pytest

pytestmark = pytest.mark.asyncio


async def test_register_login_me(client):
    resp = await client.post("/api/v1/auth/register", json={
        "organization_name": "Green Valley Farm",
        "full_name": "Jane Owner",
        "email": "jane@example.com",
        "password": "supersecret123",
    })
    assert resp.status_code == 201
    tokens = resp.json()
    assert "access_token" in tokens and "refresh_token" in tokens

    me = await client.get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {tokens['access_token']}"
    })
    assert me.status_code == 200
    body = me.json()
    assert body["organization"]["name"] == "Green Valley Farm"
    assert "farm.manage" in body["permissions"]  # Farm Owner gets full grant


async def test_tenant_isolation_on_farms(client):
    # Org A
    r1 = await client.post("/api/v1/auth/register", json={
        "organization_name": "Farm A", "full_name": "Owner A",
        "email": "a@example.com", "password": "supersecret123",
    })
    token_a = r1.json()["access_token"]

    # Org B
    r2 = await client.post("/api/v1/auth/register", json={
        "organization_name": "Farm B", "full_name": "Owner B",
        "email": "b@example.com", "password": "supersecret123",
    })
    token_b = r2.json()["access_token"]

    created = await client.post(
        "/api/v1/farms",
        json={"name": "A's Main Farm", "county": "Nakuru"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    farm_id = created.json()["id"]

    # Org B must not see Org A's farm
    leak_check = await client.get(
        f"/api/v1/farms/{farm_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert leak_check.status_code == 404


async def test_permission_denied_without_grant(client):
    r = await client.post("/api/v1/auth/register", json={
        "organization_name": "Farm C", "full_name": "Owner C",
        "email": "c@example.com", "password": "supersecret123",
    })
    token = r.json()["access_token"]

    # Create a Farm Worker (limited permissions) and confirm they can't manage users
    worker_creation = await client.post(
        "/api/v1/users",
        json={"full_name": "Worker One", "email": "worker@example.com", "password": "supersecret123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert worker_creation.status_code == 201

    login = await client.post("/api/v1/auth/login", json={
        "email": "worker@example.com", "password": "supersecret123",
    })
    worker_token = login.json()["access_token"]

    denied = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {worker_token}"})
    assert denied.status_code == 403


async def test_update_user_roles_grants_and_revokes_permissions(client):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": "Role Update Farm", "full_name": "Owner",
        "email": "roleupdate@example.com", "password": "supersecret123",
    })
    owner_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    worker = await client.post("/api/v1/users", headers=owner_headers, json={
        "full_name": "Worker", "email": "roleworker@example.com", "password": "supersecret123",
    })
    worker_id = worker.json()["id"]

    login1 = await client.post("/api/v1/auth/login", json={
        "email": "roleworker@example.com", "password": "supersecret123",
    })
    worker_headers = {"Authorization": f"Bearer {login1.json()['access_token']}"}

    denied = await client.get("/api/v1/users", headers=worker_headers)
    assert denied.status_code == 403

    owner_users = (await client.get("/api/v1/users", headers=owner_headers)).json()
    owner_role_id = next(u for u in owner_users if u["email"] == "roleupdate@example.com")["roles"][0]["id"]

    update = await client.patch(
        f"/api/v1/users/{worker_id}/roles", headers=owner_headers, json={"role_ids": [owner_role_id]},
    )
    assert update.status_code == 200
    assert update.json()["roles"][0]["id"] == owner_role_id

    login2 = await client.post("/api/v1/auth/login", json={
        "email": "roleworker@example.com", "password": "supersecret123",
    })
    worker_headers2 = {"Authorization": f"Bearer {login2.json()['access_token']}"}
    now_allowed = await client.get("/api/v1/users", headers=worker_headers2)
    assert now_allowed.status_code == 200

    # Revoke all roles again - should immediately lose access.
    revoke = await client.patch(f"/api/v1/users/{worker_id}/roles", headers=owner_headers, json={"role_ids": []})
    assert revoke.status_code == 200
    assert revoke.json()["roles"] == []

    login3 = await client.post("/api/v1/auth/login", json={
        "email": "roleworker@example.com", "password": "supersecret123",
    })
    worker_headers3 = {"Authorization": f"Bearer {login3.json()['access_token']}"}
    denied_again = await client.get("/api/v1/users", headers=worker_headers3)
    assert denied_again.status_code == 403


async def test_role_update_creates_audit_log_entry(client):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": "Audit Farm", "full_name": "Owner",
        "email": "auditlog@example.com", "password": "supersecret123",
    })
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    worker = await client.post("/api/v1/users", headers=headers, json={
        "full_name": "Worker", "email": "auditlogworker@example.com", "password": "supersecret123",
    })
    worker_id = worker.json()["id"]

    users = (await client.get("/api/v1/users", headers=headers)).json()
    owner_role_id = next(u for u in users if u["email"] == "auditlog@example.com")["roles"][0]["id"]

    await client.patch(f"/api/v1/users/{worker_id}/roles", headers=headers, json={"role_ids": [owner_role_id]})

    logs = (await client.get("/api/v1/audit-logs", headers=headers)).json()
    assert len(logs) == 1
    assert logs[0]["action"] == "user_roles_changed"
    assert logs[0]["entity_type"] == "user"
    assert logs[0]["entity_id"] == worker_id
    assert logs[0]["previous_value"] == {"role_ids": []}
    assert logs[0]["new_value"] == {"role_ids": [owner_role_id]}


async def test_audit_logs_require_audit_view_permission(client):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": "Audit Perm Farm", "full_name": "Owner",
        "email": "auditperm@example.com", "password": "supersecret123",
    })
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    await client.post("/api/v1/users", headers=headers, json={
        "full_name": "Worker", "email": "auditpermworker@example.com", "password": "supersecret123",
    })
    login = await client.post("/api/v1/auth/login", json={
        "email": "auditpermworker@example.com", "password": "supersecret123",
    })
    worker_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    denied = await client.get("/api/v1/audit-logs", headers=worker_headers)
    assert denied.status_code == 403


async def test_role_update_rejects_roles_from_other_org(client):
    reg_a = await client.post("/api/v1/auth/register", json={
        "organization_name": "Cross Org A", "full_name": "Owner A",
        "email": "crossa@example.com", "password": "supersecret123",
    })
    headers_a = {"Authorization": f"Bearer {reg_a.json()['access_token']}"}
    reg_b = await client.post("/api/v1/auth/register", json={
        "organization_name": "Cross Org B", "full_name": "Owner B",
        "email": "crossb@example.com", "password": "supersecret123",
    })
    headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}

    users_b = (await client.get("/api/v1/users", headers=headers_b)).json()
    org_b_role_id = users_b[0]["roles"][0]["id"]

    worker_a = await client.post("/api/v1/users", headers=headers_a, json={
        "full_name": "Worker A", "email": "workera@example.com", "password": "supersecret123",
    })
    worker_a_id = worker_a.json()["id"]

    # Attempting to assign an Org B role to an Org A user should silently
    # drop it (tenant-scoped query), not cross-contaminate roles.
    resp = await client.patch(
        f"/api/v1/users/{worker_a_id}/roles", headers=headers_a, json={"role_ids": [org_b_role_id]},
    )
    assert resp.status_code == 200
    assert resp.json()["roles"] == []


async def test_organization_settings_defaults_and_update(client):
    """Spec §56/§57/§60 - configurable currency/prefixes/tax/units, added
    this session. Defaults must match what every counter function/invoice
    generator previously hard-coded, so existing behavior doesn't shift for
    an org that never touches these settings."""
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": "Settings Farm", "full_name": "Owner",
        "email": "settings1@example.com", "password": "supersecret123",
    })
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    defaults = await client.get("/api/v1/organization/settings", headers=headers)
    assert defaults.status_code == 200
    body = defaults.json()
    assert body["currency"] == "KES"
    assert body["timezone"] == "Africa/Nairobi"
    assert body["invoice_prefix"] == "INV"
    assert body["po_prefix"] == "PO"
    assert body["employee_prefix"] == "EMP"
    assert body["asset_prefix"] == "AST"
    assert body["tax_rate"] == "0.00"
    assert body["default_weight_unit"] == "kg"
    assert body["default_volume_unit"] == "L"

    updated = await client.patch("/api/v1/organization/settings", headers=headers, json={
        "invoice_prefix": "RCPT", "tax_rate": "16", "currency": "USD",
    })
    assert updated.status_code == 200
    body = updated.json()
    assert body["invoice_prefix"] == "RCPT"
    assert body["tax_rate"] == "16.00"
    assert body["currency"] == "USD"
    assert body["po_prefix"] == "PO"  # untouched field preserved


async def test_configured_tax_rate_applied_to_new_invoices(client):
    """Spec §57: 'Do not hard-code tax rates.' Confirms the org's tax_rate
    actually reaches invoice generation, not just the settings record."""
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": "Tax Farm", "full_name": "Owner",
        "email": "settings2@example.com", "password": "supersecret123",
    })
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    await client.patch("/api/v1/organization/settings", headers=headers, json={"tax_rate": "16"})

    farm = await client.post("/api/v1/farms", json={"name": "Main Farm"}, headers=headers)
    farm_id = farm.json()["id"]
    branch = await client.post(f"/api/v1/farms/{farm_id}/branches", json={"name": "B"}, headers=headers)
    branch_id = branch.json()["id"]
    loc = await client.post(
        f"/api/v1/farms/{farm_id}/branches/{branch_id}/locations",
        json={"name": "L", "location_type": "paddock"}, headers=headers,
    )
    loc_id = loc.json()["id"]
    animal = await client.post("/api/v1/livestock", headers=headers, json={
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "TAX-COW",
        "species": "cattle", "sex": "female", "acquisition_date": "2024-01-01",
        "acquisition_method": "purchased", "acquisition_cost": "40000",
    })
    animal_id = animal.json()["id"]
    await client.post(f"/api/v1/livestock/{animal_id}/status", headers=headers, json={"status": "for_sale"})

    customer = await client.post("/api/v1/customers", headers=headers, json={"name": "Tax Test Buyer"})
    order = await client.post("/api/v1/orders", headers=headers, json={
        "customer_id": customer.json()["id"], "items": [{"animal_id": animal_id, "price": "10000"}],
    })
    order_id = order.json()["id"]
    await client.post(f"/api/v1/orders/{order_id}/status", headers=headers, json={"status": "payment_pending"})

    import hashlib
    import hmac
    import json as json_module
    from app.core.config import get_settings
    settings = get_settings()

    payment = await client.post("/api/v1/payments/mock", headers=headers, json={
        "order_id": order_id, "phone_or_token": "254700000000",
    })
    ref = payment.json()["provider_reference"]
    body = json_module.dumps({"event_id": "evt-tax-test", "provider_reference": ref, "status": "successful"}).encode()
    signature = hmac.new(settings.MOCK_PAYMENT_SECRET.encode(), body, hashlib.sha256).hexdigest()
    await client.post("/api/v1/payments/webhooks/mock", content=body, headers={
        "Content-Type": "application/json", "X-Mock-Signature": signature,
    })

    invoice = await client.get(f"/api/v1/finance/orders/{order_id}/invoice", headers=headers)
    assert invoice.status_code == 200
    assert invoice.json()["tax_amount"] == "1600.00"  # 16% of 10000
    assert invoice.json()["total"] == "11600.00"


async def test_list_roles(client):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": "Roles Farm", "full_name": "Owner",
        "email": "roles1@example.com", "password": "supersecret123",
    })
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    resp = await client.get("/api/v1/users/roles", headers=headers)
    assert resp.status_code == 200
    names = {r["name"] for r in resp.json()}
    assert "Farm Owner" in names
    assert "Veterinarian" in names

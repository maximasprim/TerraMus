import pytest

pytestmark = pytest.mark.asyncio


async def _register(client, org_name: str, email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org_name, "full_name": "Owner",
        "email": email, "password": "supersecret123",
    })
    token = reg.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _make_supplier(client, headers, name: str = "Acme Feeds Ltd"):
    resp = await client.post("/api/v1/procurement/suppliers", headers=headers, json={"name": name})
    return resp.json()["id"]


async def test_purchase_order_lifecycle_happy_path(client):
    headers = await _register(client, "Procurement Farm A", "p1@example.com")
    supplier_id = await _make_supplier(client, headers)

    item = await client.post("/api/v1/inventory/items", headers=headers, json={
        "name": "Dairy Meal", "category": "feed", "unit": "kg", "reorder_level": "20",
    })
    item_id = item.json()["id"]

    po = await client.post("/api/v1/procurement/purchase-orders", headers=headers, json={
        "supplier_id": supplier_id,
        "items": [{"inventory_item_id": item_id, "description": "Dairy Meal 50kg bags", "quantity": "10", "unit_cost": "45"}],
    })
    assert po.status_code == 201
    po_body = po.json()
    assert po_body["status"] == "requested"
    assert po_body["total_amount"] == "450.00"
    po_id = po_body["id"]
    assert po_body["po_number"].startswith("PO-")

    for target in ("approved", "ordered", "received"):
        resp = await client.patch(
            f"/api/v1/procurement/purchase-orders/{po_id}/status", headers=headers, json={"status": target},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == target

    # Spec §9/§26 - receiving goods against a PO must create a real stock
    # movement, not just flip a status flag.
    movements = (await client.get(f"/api/v1/inventory/items/{item_id}/movements", headers=headers)).json()
    assert len(movements) == 1
    assert movements[0]["movement_type"] == "purchase"
    assert movements[0]["quantity"] == "10.00"
    assert movements[0]["reference"] == po_body["po_number"]

    stock = (await client.get("/api/v1/inventory/items", headers=headers)).json()
    assert stock[0]["current_stock"] == "10.00"

    detail = await client.get(f"/api/v1/procurement/purchase-orders/{po_id}", headers=headers)
    history = detail.json()["status_history"]
    assert [e["to_status"] for e in history] == ["requested", "approved", "ordered", "received"]


async def test_invalid_status_transition_rejected(client):
    headers = await _register(client, "Procurement Farm B", "p2@example.com")
    supplier_id = await _make_supplier(client, headers)

    po = await client.post("/api/v1/procurement/purchase-orders", headers=headers, json={
        "supplier_id": supplier_id,
        "items": [{"description": "Fencing wire", "quantity": "5", "unit_cost": "1200"}],
    })
    po_id = po.json()["id"]

    # Can't skip straight from 'requested' to 'received'.
    resp = await client.patch(
        f"/api/v1/procurement/purchase-orders/{po_id}/status", headers=headers, json={"status": "received"},
    )
    assert resp.status_code == 409

    # A terminal state (rejected) can't transition further.
    reject = await client.patch(
        f"/api/v1/procurement/purchase-orders/{po_id}/status", headers=headers, json={"status": "rejected"},
    )
    assert reject.status_code == 200
    dead = await client.patch(
        f"/api/v1/procurement/purchase-orders/{po_id}/status", headers=headers, json={"status": "approved"},
    )
    assert dead.status_code == 409


async def test_po_line_without_inventory_link_receives_without_stock_movement(client):
    """Not every PO line is a tracked inventory item (spec §9 example: a
    one-off service charge) - receiving it must not blow up looking for a
    stock item that was never referenced."""
    headers = await _register(client, "Procurement Farm C", "p3@example.com")
    supplier_id = await _make_supplier(client, headers)

    po = await client.post("/api/v1/procurement/purchase-orders", headers=headers, json={
        "supplier_id": supplier_id,
        "items": [{"description": "Tractor servicing", "quantity": "1", "unit_cost": "8000"}],
    })
    po_id = po.json()["id"]

    for target in ("approved", "ordered", "received"):
        resp = await client.patch(
            f"/api/v1/procurement/purchase-orders/{po_id}/status", headers=headers, json={"status": target},
        )
        assert resp.status_code == 200, resp.text


async def test_procurement_tenant_isolation(client):
    headers_a = await _register(client, "Procurement Iso A", "p4a@example.com")
    headers_b = await _register(client, "Procurement Iso B", "p4b@example.com")

    supplier_id = await _make_supplier(client, headers_a, "Secret Supplier")

    leak = await client.get(f"/api/v1/procurement/suppliers/{supplier_id}", headers=headers_b)
    assert leak.status_code == 404

    # A PO can't reference a supplier from a different organization.
    cross_org_po = await client.post("/api/v1/procurement/purchase-orders", headers=headers_b, json={
        "supplier_id": supplier_id,
        "items": [{"description": "Feed", "quantity": "1", "unit_cost": "100"}],
    })
    assert cross_org_po.status_code == 404

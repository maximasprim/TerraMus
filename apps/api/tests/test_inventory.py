import pytest

pytestmark = pytest.mark.asyncio


async def _register(client, org_name: str, email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org_name, "full_name": "Owner",
        "email": email, "password": "supersecret123",
    })
    token = reg.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_negative_stock_blocked_by_default(client):
    headers = await _register(client, "Inventory Farm A", "i1@example.com")
    item = await client.post("/api/v1/inventory/items", headers=headers, json={
        "name": "Dairy Meal", "category": "feed", "unit": "kg", "reorder_level": "50",
    })
    item_id = item.json()["id"]

    purchase = await client.post(f"/api/v1/inventory/items/{item_id}/movements", headers=headers, json={
        "movement_type": "purchase", "quantity": "200", "unit_cost": "45",
    })
    assert purchase.status_code == 201

    consume = await client.post(f"/api/v1/inventory/items/{item_id}/movements", headers=headers, json={
        "movement_type": "consumption", "quantity": "180", "unit_cost": "45",
    })
    assert consume.status_code == 201

    items = (await client.get("/api/v1/inventory/items", headers=headers)).json()
    assert items[0]["current_stock"] == "20.00"

    overdraw = await client.post(f"/api/v1/inventory/items/{item_id}/movements", headers=headers, json={
        "movement_type": "consumption", "quantity": "50",
    })
    assert overdraw.status_code == 409


async def test_negative_stock_allowed_when_configured(client):
    headers = await _register(client, "Inventory Farm B", "i2@example.com")
    item = await client.post("/api/v1/inventory/items", headers=headers, json={
        "name": "Salt Lick", "category": "supply", "unit": "unit",
        "reorder_level": "0", "allow_negative_stock": True,
    })
    item_id = item.json()["id"]

    consume = await client.post(f"/api/v1/inventory/items/{item_id}/movements", headers=headers, json={
        "movement_type": "consumption", "quantity": "5",
    })
    assert consume.status_code == 201  # allowed even though balance goes to -5

    items = (await client.get("/api/v1/inventory/items", headers=headers)).json()
    assert items[0]["current_stock"] == "-5.00"


async def test_low_stock_alert_appears_at_or_below_reorder_level(client):
    headers = await _register(client, "Inventory Farm C", "i3@example.com")
    item = await client.post("/api/v1/inventory/items", headers=headers, json={
        "name": "Mineral Supplement", "category": "supply", "unit": "kg", "reorder_level": "10",
    })
    item_id = item.json()["id"]
    await client.post(f"/api/v1/inventory/items/{item_id}/movements", headers=headers, json={
        "movement_type": "opening_balance", "quantity": "10",
    })

    low = (await client.get("/api/v1/inventory/low-stock", headers=headers)).json()
    assert len(low) == 1
    assert low[0]["item_id"] == item_id


async def test_ledger_is_append_only_current_stock_always_summed(client):
    """Business rule spec §14/§52: never overwrite quantities, always sum the ledger."""
    headers = await _register(client, "Inventory Farm D", "i4@example.com")
    item = await client.post("/api/v1/inventory/items", headers=headers, json={
        "name": "Hay", "category": "feed", "unit": "bag", "reorder_level": "5",
    })
    item_id = item.json()["id"]

    for qty in ("10", "5", "-3"):  # opening, purchase, then an adjustment
        mtype = "adjustment" if qty.startswith("-") else ("opening_balance" if qty == "10" else "purchase")
        await client.post(f"/api/v1/inventory/items/{item_id}/movements", headers=headers, json={
            "movement_type": mtype, "quantity": qty,
        })

    movements = (await client.get(f"/api/v1/inventory/items/{item_id}/movements", headers=headers)).json()
    assert len(movements) == 3

    items = (await client.get("/api/v1/inventory/items", headers=headers)).json()
    assert items[0]["current_stock"] == "12.00"  # 10 + 5 - 3


async def test_inventory_tenant_isolation(client):
    headers_a = await _register(client, "Inventory Iso A", "i5a@example.com")
    headers_b = await _register(client, "Inventory Iso B", "i5b@example.com")

    item = await client.post("/api/v1/inventory/items", headers=headers_a, json={
        "name": "Secret Feed", "category": "feed", "unit": "kg", "reorder_level": "0",
    })
    item_id = item.json()["id"]

    leak = await client.get(f"/api/v1/inventory/items/{item_id}/movements", headers=headers_b)
    assert leak.status_code == 404


async def test_fifo_costing_blends_across_purchase_layers(client):
    """Spec §14 'inventory valuation' (this session). Two purchase batches
    at different prices; a consumption spanning both must be costed as a
    blend of the two, oldest-purchased-first - not just the latest price."""
    headers = await _register(client, "FIFO Farm A", "fifo1@example.com")
    item = await client.post("/api/v1/inventory/items", headers=headers, json={
        "name": "Dairy Meal", "category": "feed", "unit": "kg", "reorder_level": "0",
    })
    item_id = item.json()["id"]

    await client.post(f"/api/v1/inventory/items/{item_id}/movements", headers=headers, json={
        "movement_type": "purchase", "quantity": "100", "unit_cost": "40", "moved_at": "2026-01-01T00:00:00Z",
    })
    await client.post(f"/api/v1/inventory/items/{item_id}/movements", headers=headers, json={
        "movement_type": "purchase", "quantity": "100", "unit_cost": "60", "moved_at": "2026-02-01T00:00:00Z",
    })

    # Consume 150kg with NO unit_cost supplied - should draw all 100kg from
    # the Jan batch (@40) plus 50kg from the Feb batch (@60):
    # (100*40 + 50*60) / 150 = 46.6666... -> stored as 46.67 (unit_cost is a
    # NUMERIC(12,2) column; see service.fifo_unit_cost_for_consumption).
    consume = await client.post(f"/api/v1/inventory/items/{item_id}/movements", headers=headers, json={
        "movement_type": "consumption", "quantity": "150", "moved_at": "2026-03-01T00:00:00Z",
    })
    assert consume.status_code == 201
    assert consume.json()["unit_cost"] == "46.67"

    # Remaining 50kg is entirely from the Feb batch (@60).
    valuation = (await client.get("/api/v1/inventory/valuation", headers=headers)).json()
    row = next(r for r in valuation if r["item_id"] == item_id)
    assert row["quantity_on_hand"] == "50.00"
    assert row["priced_quantity"] == "50.00"
    assert row["avg_unit_cost"] == "60.0000"
    assert row["total_value"] == "3000.00"


async def test_fifo_consumption_without_any_purchase_history_leaves_unit_cost_null(client):
    """No priced layer exists at all -> FIFO can't invent a cost, so
    unit_cost stays null exactly as it did before this session's change."""
    headers = await _register(client, "FIFO Farm B", "fifo2@example.com")
    item = await client.post("/api/v1/inventory/items", headers=headers, json={
        "name": "Salt Lick", "category": "supply", "unit": "unit",
        "reorder_level": "0", "allow_negative_stock": True,
    })
    item_id = item.json()["id"]

    consume = await client.post(f"/api/v1/inventory/items/{item_id}/movements", headers=headers, json={
        "movement_type": "consumption", "quantity": "5",
    })
    assert consume.status_code == 201
    assert consume.json()["unit_cost"] is None


async def test_explicit_unit_cost_overrides_fifo_estimate(client):
    headers = await _register(client, "FIFO Farm C", "fifo3@example.com")
    item = await client.post("/api/v1/inventory/items", headers=headers, json={
        "name": "Dairy Meal", "category": "feed", "unit": "kg", "reorder_level": "0",
    })
    item_id = item.json()["id"]
    await client.post(f"/api/v1/inventory/items/{item_id}/movements", headers=headers, json={
        "movement_type": "purchase", "quantity": "100", "unit_cost": "40",
    })
    # Caller explicitly states the real invoiced cost, which must win over
    # the FIFO estimate (which would have been 40).
    consume = await client.post(f"/api/v1/inventory/items/{item_id}/movements", headers=headers, json={
        "movement_type": "consumption", "quantity": "10", "unit_cost": "999",
    })
    assert consume.json()["unit_cost"] == "999.00"


async def test_valuation_reports_zero_for_item_with_no_movements(client):
    headers = await _register(client, "FIFO Farm D", "fifo4@example.com")
    await client.post("/api/v1/inventory/items", headers=headers, json={
        "name": "Unused Item", "category": "supply", "unit": "unit", "reorder_level": "0",
    })
    valuation = (await client.get("/api/v1/inventory/valuation", headers=headers)).json()
    assert valuation[0]["quantity_on_hand"] == "0.00"
    assert valuation[0]["priced_quantity"] == "0.00"
    assert valuation[0]["avg_unit_cost"] is None
    assert valuation[0]["total_value"] == "0.00"

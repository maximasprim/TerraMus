import pytest

pytestmark = pytest.mark.asyncio


async def _register(client, org_name: str, email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org_name, "full_name": "Owner",
        "email": email, "password": "supersecret123",
    })
    token = reg.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_asset_create_and_number_sequence(client):
    headers = await _register(client, "Asset Farm A", "a1@example.com")

    a1 = await client.post("/api/v1/assets", headers=headers, json={
        "name": "Massey Ferguson 375", "asset_type": "tractor", "serial_number": "MF-1234",
        "acquisition_date": "2024-01-01", "acquisition_cost": "1500000",
        "useful_life_years": 10, "salvage_value": "150000",
    })
    assert a1.status_code == 201
    body = a1.json()
    assert body["asset_number"] == "AST-000001"
    assert body["status"] == "in_use"
    assert body["condition"] == "good"
    # Fresh asset: negligible depreciation, current_value should be very
    # close to (not exactly, since "today" isn't the acquisition date in a
    # deterministic test run) acquisition_cost, and never above it.
    assert float(body["current_value"]) <= float(body["acquisition_cost"])

    a2 = await client.post("/api/v1/assets", headers=headers, json={
        "name": "Fence Line North", "asset_type": "fence",
    })
    assert a2.json()["asset_number"] == "AST-000002"
    # No acquisition_cost given -> no depreciation inputs -> current_value is None.
    assert a2.json()["current_value"] is None
    assert a2.json()["total_maintenance_cost"] == "0.00"


async def test_depreciation_never_goes_below_salvage_value(client):
    """An asset acquired long enough ago (beyond its useful life) should
    floor at salvage_value, not go negative."""
    headers = await _register(client, "Asset Farm B", "a2@example.com")
    asset = await client.post("/api/v1/assets", headers=headers, json={
        "name": "Old Water Pump", "asset_type": "pump",
        "acquisition_date": "2000-01-01", "acquisition_cost": "50000",
        "useful_life_years": 5, "salvage_value": "5000",
    })
    assert float(asset.json()["current_value"]) == 5000.00


async def test_maintenance_records_roll_up_and_clear_under_maintenance_status(client):
    headers = await _register(client, "Asset Farm C", "a3@example.com")
    asset = await client.post("/api/v1/assets", headers=headers, json={
        "name": "Milking Machine 1", "asset_type": "milking_equipment",
    })
    asset_id = asset.json()["id"]

    await client.patch(f"/api/v1/assets/{asset_id}", headers=headers, json={"status": "under_maintenance"})

    rec1 = await client.post(f"/api/v1/assets/{asset_id}/maintenance", headers=headers, json={
        "maintenance_type": "inspection", "maintenance_date": "2026-01-01", "description": "Routine check", "cost": "500",
    })
    assert rec1.status_code == 201
    # An inspection alone doesn't imply the repair is done.
    still_under_maintenance = await client.get(f"/api/v1/assets/{asset_id}", headers=headers)
    assert still_under_maintenance.json()["status"] == "under_maintenance"

    rec2 = await client.post(f"/api/v1/assets/{asset_id}/maintenance", headers=headers, json={
        "maintenance_type": "repair", "maintenance_date": "2026-01-02", "description": "Replaced pump seal", "cost": "2500",
    })
    assert rec2.status_code == 201

    detail = await client.get(f"/api/v1/assets/{asset_id}", headers=headers)
    body = detail.json()
    assert body["status"] == "in_use"  # repair completed -> back in service
    assert body["total_maintenance_cost"] == "3000.00"
    assert len(body["maintenance_records"]) == 2


async def test_asset_tenant_isolation(client):
    headers_a = await _register(client, "Asset Farm D-A", "a4a@example.com")
    headers_b = await _register(client, "Asset Farm D-B", "a4b@example.com")

    asset = await client.post("/api/v1/assets", headers=headers_a, json={
        "name": "Secret Tractor", "asset_type": "tractor",
    })
    asset_id = asset.json()["id"]

    leak = await client.get(f"/api/v1/assets/{asset_id}", headers=headers_b)
    assert leak.status_code == 404

    leak_maintenance = await client.post(f"/api/v1/assets/{asset_id}/maintenance", headers=headers_b, json={
        "maintenance_type": "service", "maintenance_date": "2026-01-01", "description": "Should fail",
    })
    assert leak_maintenance.status_code == 404

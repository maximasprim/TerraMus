import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio


async def _seed_full_flow(client):
    """Drives real API calls to populate at least one row in every
    append-only table this test checks, across all phases."""
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": "Append Only Farm", "full_name": "Owner",
        "email": "appendonly@example.com", "password": "supersecret123",
    })
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

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
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "AO-DAM",
        "species": "cattle", "sex": "female", "acquisition_date": "2024-01-01",
        "acquisition_method": "purchased", "acquisition_cost": "40000", "current_weight": "200",
    })  # -> animal_events (acquired), weight_records (initial weight)
    dam_id = dam.json()["id"]

    await client.post(f"/api/v1/livestock/{dam_id}/weights", headers=headers, json={"weight_kg": "210"})

    loc2 = await client.post(
        f"/api/v1/farms/{farm_id}/branches/{branch_id}/locations",
        json={"name": "Paddock 2", "location_type": "paddock"}, headers=headers,
    )
    await client.post(f"/api/v1/livestock/{dam_id}/movements", headers=headers, json={
        "to_location_id": loc2.json()["id"],
    })  # -> movements

    bred = await client.post("/api/v1/breeding", headers=headers, json={
        "dam_id": dam_id, "method": "natural", "mating_date": "2026-01-01",
    })
    await client.post(f"/api/v1/breeding/{bred.json()['id']}/pregnancy-checks", headers=headers, json={
        "check_date": "2026-02-01", "result": "confirmed",
    })  # -> pregnancy_checks

    await client.post(f"/api/v1/livestock/{dam_id}/dairy/milk", headers=headers, json={
        "production_date": "2026-08-10", "session": "morning", "quantity_liters": "10",
    })  # -> milk_production_records

    item = await client.post("/api/v1/inventory/items", headers=headers, json={
        "name": "Hay", "category": "feed", "unit": "bag", "reorder_level": "0",
    })
    await client.post(f"/api/v1/inventory/items/{item.json()['id']}/movements", headers=headers, json={
        "movement_type": "opening_balance", "quantity": "10",
    })  # -> stock_movements

    await client.post(f"/api/v1/livestock/{dam_id}/status", headers=headers, json={"status": "for_sale"})
    customer = await client.post("/api/v1/customers", headers=headers, json={"name": "Alice"})
    order = await client.post("/api/v1/orders", headers=headers, json={
        "customer_id": customer.json()["id"], "items": [{"animal_id": dam_id, "price": "50000"}],
    })  # -> order_status_events (pending)


@pytest.mark.parametrize("table,set_clause", [
    ("animal_events", "event_type = 'tampered'"),
    ("weight_records", "weight_kg = 999"),
    ("movements", "reason = 'tampered'"),
    ("pregnancy_checks", "result = 'inconclusive'"),
    ("milk_production_records", "quantity_liters = 999"),
    ("stock_movements", "quantity = 999"),
    ("order_status_events", "to_status = 'cancelled'"),
])
async def test_append_only_tables_reject_updates(client, engine, table, set_clause):
    """Confirms the DB-level append-only trigger (not just application-layer
    discipline) actually rejects UPDATE on populated historical-fact tables
    across all phases - not just that the tables exist."""
    await _seed_full_flow(client)

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        count = (await session.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar_one()
        assert count > 0, f"{table} has no rows - seeding didn't populate it, test would be vacuous"

        with pytest.raises(DBAPIError, match="append-only"):
            await session.execute(text(f"UPDATE {table} SET {set_clause}"))

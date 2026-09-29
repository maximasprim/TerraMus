import pytest

pytestmark = pytest.mark.asyncio


async def _register(client, org_name: str, email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org_name, "full_name": "Owner",
        "email": email, "password": "supersecret123",
    })
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def test_customer_import_preview_then_confirm(client):
    headers = await _register(client, "Import Farm A", "imp1@example.com")
    csv_bytes = (
        b"name,phone,email,customer_type\n"
        b"Alice Trader,0700000001,alice@example.com,individual\n"
        b"Bob Butchery,0700000002,bob@example.com,butcher\n"
    )

    preview = await client.post(
        "/api/v1/bulk-import/customers", headers=headers,
        files={"file": ("customers.csv", csv_bytes, "text/csv")},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["dry_run"] is True
    assert body["total_rows"] == 2
    assert body["valid_rows"] == 2
    assert body["imported"] == 0  # preview never writes

    still_empty = await client.get("/api/v1/customers", headers=headers)
    assert still_empty.json() == []

    confirm = await client.post(
        "/api/v1/bulk-import/customers", headers=headers, params={"dry_run": "false"},
        files={"file": ("customers.csv", csv_bytes, "text/csv")},
    )
    assert confirm.json()["imported"] == 2

    after = await client.get("/api/v1/customers", headers=headers)
    assert len(after.json()) == 2


async def test_bad_rows_reported_without_blocking_good_rows(client):
    """Spec §73: 'Never blindly import invalid records' - but one bad row
    must not sink the whole file either."""
    headers = await _register(client, "Import Farm B", "imp2@example.com")
    csv_bytes = (
        b"name,customer_type\n"
        b"Good Customer,individual\n"
        b",individual\n"  # missing required name
        b"Bad Type Customer,not_a_real_type\n"  # invalid customer_type pattern
    )

    result = await client.post(
        "/api/v1/bulk-import/customers", headers=headers, params={"dry_run": "false"},
        files={"file": ("customers.csv", csv_bytes, "text/csv")},
    )
    body = result.json()
    assert body["total_rows"] == 3
    assert body["valid_rows"] == 1
    assert body["imported"] == 1
    assert len(body["errors"]) == 2
    assert body["errors"][0]["row"] == 3  # header is row 1, first data row is row 2
    assert body["errors"][1]["row"] == 4

    customers = (await client.get("/api/v1/customers", headers=headers)).json()
    assert len(customers) == 1
    assert customers[0]["name"] == "Good Customer"


async def test_supplier_and_inventory_import(client):
    headers = await _register(client, "Import Farm C", "imp3@example.com")

    suppliers_csv = b"name,phone\nGreen Valley Feeds,0711111111\n"
    resp = await client.post(
        "/api/v1/bulk-import/suppliers", headers=headers, params={"dry_run": "false"},
        files={"file": ("suppliers.csv", suppliers_csv, "text/csv")},
    )
    assert resp.json()["imported"] == 1

    items_csv = b"name,category,unit,reorder_level\nDairy Meal,feed,kg,50\n"
    resp2 = await client.post(
        "/api/v1/bulk-import/inventory-items", headers=headers, params={"dry_run": "false"},
        files={"file": ("items.csv", items_csv, "text/csv")},
    )
    assert resp2.json()["imported"] == 1
    items = (await client.get("/api/v1/inventory/items", headers=headers)).json()
    assert items[0]["reorder_level"] == "50.00"


async def test_livestock_import_applies_farm_id_to_every_row(client):
    headers = await _register(client, "Import Farm D", "imp4@example.com")
    farm = await client.post("/api/v1/farms", json={"name": "Main Farm"}, headers=headers)
    farm_id = farm.json()["id"]

    csv_bytes = (
        b"animal_number,species,sex,acquisition_date,acquisition_method,acquisition_cost\n"
        b"BULK-001,cattle,female,2024-01-01,purchased,40000\n"
        b"BULK-002,cattle,male,2024-01-02,purchased,35000\n"
    )
    resp = await client.post(
        "/api/v1/bulk-import/livestock", headers=headers, params={"farm_id": farm_id, "dry_run": "false"},
        files={"file": ("animals.csv", csv_bytes, "text/csv")},
    )
    assert resp.json()["imported"] == 2

    animals = (await client.get("/api/v1/livestock", headers=headers)).json()
    assert {a["animal_number"] for a in animals} == {"BULK-001", "BULK-002"}
    assert all(a["farm_id"] == farm_id for a in animals)


async def test_bulk_import_tenant_isolation(client):
    headers_a = await _register(client, "Import Farm E-A", "imp5a@example.com")
    headers_b = await _register(client, "Import Farm E-B", "imp5b@example.com")

    csv_bytes = b"name\nOrg A Customer\n"
    await client.post(
        "/api/v1/bulk-import/customers", headers=headers_a, params={"dry_run": "false"},
        files={"file": ("c.csv", csv_bytes, "text/csv")},
    )

    b_customers = (await client.get("/api/v1/customers", headers=headers_b)).json()
    assert b_customers == []

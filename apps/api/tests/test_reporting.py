import pytest

pytestmark = pytest.mark.asyncio


async def _setup_animal(client, org_name: str, email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org_name, "full_name": "Owner",
        "email": email, "password": "supersecret123",
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

    animal = await client.post("/api/v1/livestock", headers=headers, json={
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "COW-RPT",
        "species": "cattle", "sex": "female", "acquisition_date": "2024-01-01",
        "acquisition_method": "purchased", "acquisition_cost": "40000",
    })
    return headers, animal.json()["id"]


async def test_health_and_feed_costs_flow_into_finance_ledger(client):
    """Regression test for the bug found during Phase 6 live testing: the
    profitability report pulls costs directly from health_records/
    stock_movements, but the finance ledger only reflected acquisition cost
    until HealthRecordCreated/InventorySpend handlers were added."""
    headers, animal_id = await _setup_animal(client, "Ledger Consistency Farm", "r1@example.com")

    await client.post(f"/api/v1/livestock/{animal_id}/health", headers=headers, json={
        "record_type": "treatment", "title": "Checkup", "cost": "1500",
        "performed_at": "2026-08-10T09:00:00Z",
    })
    item = await client.post("/api/v1/inventory/items", headers=headers, json={
        "name": "Feed", "category": "feed", "unit": "kg", "reorder_level": "5",
    })
    item_id = item.json()["id"]
    await client.post(f"/api/v1/inventory/items/{item_id}/movements", headers=headers, json={
        "movement_type": "opening_balance", "quantity": "100",
    })
    await client.post(f"/api/v1/inventory/items/{item_id}/movements", headers=headers, json={
        "movement_type": "consumption", "quantity": "20", "unit_cost": "50", "animal_id": animal_id,
    })

    txns = (await client.get("/api/v1/finance/transactions", headers=headers)).json()
    categories = {t["category"]: t["amount"] for t in txns}
    assert categories["livestock_acquisition"] == "40000.00"
    assert categories["veterinary"] == "1500.00"
    assert categories["feed"] == "1000.00"

    report = (await client.get("/api/v1/reports/profitability", headers=headers)).json()
    detail = report["animals"][0]
    assert detail["total_investment"] == "42500.0000"

    dashboard = (await client.get("/api/v1/reports/dashboard", headers=headers)).json()
    assert dashboard["monthly_expenses"] == "42500.00"  # matches the report, not just acquisition


async def test_profitability_actual_vs_expected(client):
    headers, animal_id = await _setup_animal(client, "Profitability Farm", "r2@example.com")

    # Before any sale: expected profit only, is_actual False, if expected_sale_price is set.
    await client.patch(f"/api/v1/livestock/{animal_id}", headers=headers, json={
        "expected_sale_price": "70000",
    })
    report_before = (await client.get("/api/v1/reports/profitability", headers=headers)).json()
    before = report_before["animals"][0]
    assert before["is_actual"] is False
    assert before["profit"] == "30000.00"  # 70000 - 40000 acquisition

    # Sell it through to paid.
    await client.post(f"/api/v1/livestock/{animal_id}/status", headers=headers, json={"status": "for_sale"})
    customer = await client.post("/api/v1/customers", headers=headers, json={"name": "Alice"})
    order = await client.post("/api/v1/orders", headers=headers, json={
        "customer_id": customer.json()["id"], "items": [{"animal_id": animal_id, "price": "90000"}],
    })
    order_id = order.json()["id"]
    await client.post(f"/api/v1/orders/{order_id}/status", headers=headers, json={"status": "payment_pending"})
    await client.post(f"/api/v1/orders/{order_id}/status", headers=headers, json={"status": "paid"})

    report_after = (await client.get("/api/v1/reports/profitability", headers=headers)).json()
    after = report_after["animals"][0]
    assert after["is_actual"] is True
    assert after["sale_price"] == "90000.00"
    assert after["profit"] == "50000.00"  # 90000 - 40000 acquisition (real sale, not the earlier estimate)


async def test_dashboard_excludes_sold_animals_from_herd_value(client):
    headers, animal_id = await _setup_animal(client, "Herd Value Farm", "r3@example.com")
    await client.patch(f"/api/v1/livestock/{animal_id}", headers=headers, json={"current_value": "50000"})

    before = (await client.get("/api/v1/reports/dashboard", headers=headers)).json()
    assert before["herd_value"] == "50000.00"
    assert before["active_animals"] == 1

    await client.post(f"/api/v1/livestock/{animal_id}/status", headers=headers, json={"status": "for_sale"})
    customer = await client.post("/api/v1/customers", headers=headers, json={"name": "Alice"})
    order = await client.post("/api/v1/orders", headers=headers, json={
        "customer_id": customer.json()["id"], "items": [{"animal_id": animal_id, "price": "60000"}],
    })
    order_id = order.json()["id"]
    await client.post(f"/api/v1/orders/{order_id}/status", headers=headers, json={"status": "payment_pending"})
    await client.post(f"/api/v1/orders/{order_id}/status", headers=headers, json={"status": "paid"})

    after = (await client.get("/api/v1/reports/dashboard", headers=headers)).json()
    assert after["active_animals"] == 0
    assert after["herd_value"] == "0"  # sold animal correctly excluded from active herd value


async def test_csv_export_contains_animal(client):
    headers, animal_id = await _setup_animal(client, "CSV Farm", "r4@example.com")
    resp = await client.get("/api/v1/reports/export/livestock.csv", headers=headers)
    assert resp.status_code == 200
    assert "COW-RPT" in resp.text
    assert resp.headers["content-type"].startswith("text/csv")


async def test_pdf_export_returns_a_pdf(client):
    """Spec §44 PDF export (this session) - see finance/pdf.py's docstring
    for the reportlab dependency's verification-status caveat."""
    headers, animal_id = await _setup_animal(client, "PDF Farm", "r4b@example.com")
    resp = await client.get("/api/v1/reports/export/livestock.pdf", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


async def test_reporting_tenant_isolation(client):
    headers_a, _ = await _setup_animal(client, "Report Iso A", "r5a@example.com")
    headers_b, _ = await _setup_animal(client, "Report Iso B", "r5b@example.com")

    dash_a = (await client.get("/api/v1/reports/dashboard", headers=headers_a)).json()
    dash_b = (await client.get("/api/v1/reports/dashboard", headers=headers_b)).json()
    assert dash_a["total_animals"] == 1
    assert dash_b["total_animals"] == 1  # each org sees only its own animal, not 2

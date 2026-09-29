import pytest

pytestmark = pytest.mark.asyncio


async def _register(client, org_name: str, email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org_name, "full_name": "Owner",
        "email": email, "password": "supersecret123",
    })
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def test_manual_transaction_and_summary_math(client):
    headers = await _register(client, "Finance Farm A", "f1@example.com")

    await client.post("/api/v1/finance/transactions", headers=headers, json={
        "transaction_type": "income", "category": "milk_sale",
        "amount": "500", "transaction_date": "2026-08-12",
    })
    await client.post("/api/v1/finance/transactions", headers=headers, json={
        "transaction_type": "expense", "category": "feed",
        "amount": "200", "transaction_date": "2026-08-12",
    })
    await client.post("/api/v1/finance/transactions", headers=headers, json={
        "transaction_type": "expense", "category": "veterinary",
        "amount": "100", "transaction_date": "2026-08-12",
    })

    summary = (await client.get(
        "/api/v1/finance/summary?start_date=2026-08-12&end_date=2026-08-12", headers=headers,
    )).json()
    assert summary["total_income"] == "500.00"
    assert summary["total_expense"] == "300.00"
    assert summary["net_income"] == "200.00"
    assert summary["expense_by_category"]["feed"] == "200.00"
    assert summary["expense_by_category"]["veterinary"] == "100.00"


async def test_summary_date_range_excludes_out_of_range_transactions(client):
    headers = await _register(client, "Finance Farm B", "f2@example.com")
    await client.post("/api/v1/finance/transactions", headers=headers, json={
        "transaction_type": "income", "category": "milk_sale",
        "amount": "500", "transaction_date": "2020-01-01",  # deliberately out of range
    })
    summary = (await client.get(
        "/api/v1/finance/summary?start_date=2026-08-01&end_date=2026-08-31", headers=headers,
    )).json()
    assert summary["total_income"] == "0"


async def test_finance_tenant_isolation(client):
    headers_a = await _register(client, "Finance Iso A", "f3a@example.com")
    headers_b = await _register(client, "Finance Iso B", "f3b@example.com")

    await client.post("/api/v1/finance/transactions", headers=headers_a, json={
        "transaction_type": "income", "category": "milk_sale",
        "amount": "500", "transaction_date": "2026-08-12",
    })

    txns_b = (await client.get("/api/v1/finance/transactions", headers=headers_b)).json()
    assert len(txns_b) == 0  # Org B sees none of Org A's transactions

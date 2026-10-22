from datetime import date, timedelta

import pytest

from app.modules.receivables.models import AccountEntry
from app.modules.receivables.service import age_buckets, fifo_open_items

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------- pure FIFO logic
def _e(kind, amount, d, n=0):
    from datetime import datetime, timezone
    return AccountEntry(entry_type=kind, amount=amount, entry_date=d, created_at=datetime(2026, 1, 1, 0, 0, n, tzinfo=timezone.utc))


def test_payments_clear_oldest_charges_first_and_ageing_buckets():
    jan, mar, jun = date(2026, 1, 10), date(2026, 3, 10), date(2026, 6, 10)
    entries = [_e("charge", 1000, jan, 1), _e("charge", 2000, mar, 2), _e("charge", 500, jun, 3), _e("payment", 1500, jun, 4)]
    items, credit = fifo_open_items(entries)
    assert [round(i["outstanding"]) for i in items] == [0, 1500, 500] and credit == 0
    ag = age_buckets(items, date(2026, 6, 30))
    assert ag["0-30"] == 500 and ag["90+"] == 1500           # March charge is ~112 days old; June is 20 days old
    items, credit = fifo_open_items([_e("charge", 100, jan), _e("payment", 150, jan)])
    assert items[0]["outstanding"] == 0 and credit == 50     # overpayment -> credit on account


# ------------------------------------------------------------------------ helpers
async def _setup(client, email="rc@example.com"):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": "Credit Farm", "full_name": "Owner One", "email": email, "password": "supersecret123"})
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    farm = (await client.post("/api/v1/farms", json={"name": "Segera"}, headers=h)).json()["id"]
    cust = (await client.post("/api/v1/customers", json={"name": "Kamau Butchery", "phone": "0712345678"}, headers=h)).json()["id"]
    b = (await client.post("/api/v1/feedlot/intake-batches", headers=h, json={
        "delivered_on": "2026-01-10", "farm_id": farm, "head_purchased": 2, "purchase_cost": "100000"})).json()
    await client.post(f"/api/v1/feedlot/intake-batches/{b['id']}/animals", headers=h, json={
        "animals": [{"animal_number": "C01", "entry_weight_kg": 200}, {"animal_number": "C02", "entry_weight_kg": 210}]})
    items = (await client.get("/api/v1/livestock", headers=h)).json()
    items = items["items"] if isinstance(items, dict) else items
    ids = {a["animal_number"]: a["id"] for a in items}
    return h, farm, cust, ids


async def test_credit_sale_creates_charge_not_income_then_part_payments_post_income(client):
    h, farm, cust, ids = await _setup(client)
    sale = await client.post(f"/api/v1/feedlot/animals/{ids['C01']}/sale", headers=h, json={
        "exit_date": "2026-06-01", "exit_weight_kg": 300, "price_per_kg": 330, "customer_id": cust, "salesperson": "Wanjiku"})
    assert sale.status_code == 201 and sale.json()["amount"] == 99000.0
    st = (await client.get(f"/api/v1/receivables/customers/{cust}/statement?as_of=2026-06-30", headers=h)).json()
    assert st["balance"] == 99000.0 and st["charged"] == 99000.0 and st["open_items"][0]["reference_type"] == "feedlot_sale"
    fin = (await client.get("/api/v1/finance/transactions?category=livestock_sale", headers=h)).json()
    assert fin == []                                           # credit sale: no income until cash arrives

    pay = (await client.post("/api/v1/receivables/payments", headers=h, json={
        "customer_id": cust, "amount": 40000, "entry_date": "2026-06-10", "method": "mpesa", "receipt_ref": "SFG1234XYZ",
        "reference_type": "feedlot_sale", "reference_id": st["open_items"][0]["reference_id"]})).json()
    assert pay["balance_before"] == 99000.0 and pay["balance_after"] == 59000.0
    fin = (await client.get("/api/v1/finance/transactions?category=livestock_sale", headers=h)).json()
    assert len(fin) == 1 and float(fin[0]["amount"]) == 40000.0
    assert fin[0]["activity"] == "feedlot" and fin[0]["farm_id"] == farm      # dimensions inherited from the sale
    over = (await client.post("/api/v1/receivables/payments", headers=h, json={
        "customer_id": cust, "amount": 70000, "entry_date": "2026-06-20", "method": "bank"})).json()
    assert over["balance_after"] == -11000.0 and "credit" in over["warning"]


async def test_balances_ageing_writeoff_rules_and_salesperson_report(client):
    h, farm, cust, ids = await _setup(client, "rc2@example.com")
    old = (date.today() - timedelta(days=100)).isoformat()
    await client.post("/api/v1/receivables/charges", headers=h, json={
        "customer_id": cust, "amount": 5000, "entry_date": old, "description": "Old debt", "salesperson": "Otieno"})
    await client.post(f"/api/v1/feedlot/animals/{ids['C02']}/sale", headers=h, json={
        "exit_date": date.today().isoformat(), "exit_weight_kg": 250, "price_per_kg": 300, "customer_id": cust, "salesperson": "Wanjiku"})
    bal = (await client.get("/api/v1/receivables/balances", headers=h)).json()
    assert bal["customers_owing"] == 1 and bal["total_outstanding"] == 80000.0
    assert bal["ageing"]["90+"] == 5000.0 and bal["ageing"]["0-30"] == 75000.0
    assert bal["customers"][0]["days_outstanding"] == 100
    too_much = await client.post("/api/v1/receivables/writeoffs", headers=h, json={
        "customer_id": cust, "amount": 999999, "entry_date": date.today().isoformat(), "description": "bad debt"})
    assert too_much.status_code == 422
    ok = await client.post("/api/v1/receivables/writeoffs", headers=h, json={
        "customer_id": cust, "amount": 5000, "entry_date": date.today().isoformat(), "description": "Customer relocated"})
    assert ok.status_code == 201
    assert (await client.get("/api/v1/receivables/balances", headers=h)).json()["total_outstanding"] == 75000.0
    assert (await client.post("/api/v1/receivables/writeoffs", headers=h, json={
        "customer_id": cust, "amount": 1, "entry_date": old, "description": "x"})).status_code == 422    # reason too short
    rep = (await client.get(f"/api/v1/receivables/sales-by-salesperson?start_date=2020-01-01&end_date=2099-01-01", headers=h)).json()
    by = {r["salesperson"]: r for r in rep}
    assert by["Wanjiku"]["amount"] == 75000.0 and by["Otieno"]["amount"] == 5000.0


async def test_cash_sale_without_customer_posts_income_immediately(client):
    h, farm, cust, ids = await _setup(client, "rc3@example.com")
    r = await client.post(f"/api/v1/feedlot/animals/{ids['C01']}/sale", headers=h, json={
        "exit_date": "2026-06-01", "exit_weight_kg": 300, "price_per_kg": 330})
    assert r.status_code == 201
    fin = (await client.get("/api/v1/finance/transactions?category=livestock_sale", headers=h)).json()
    assert len(fin) == 1 and float(fin[0]["amount"]) == 99000.0 and fin[0]["activity"] == "feedlot"


async def test_finance_dimensions_new_categories_and_backward_compatibility(client):
    h, farm, cust, ids = await _setup(client, "rc4@example.com")
    # old-style payload (no farm/activity) still works
    old = await client.post("/api/v1/finance/transactions", headers=h, json={
        "transaction_type": "expense", "category": "feed", "amount": 1000, "transaction_date": "2026-05-01"})
    assert old.status_code == 201 and old.json()["farm_id"] is None and old.json()["activity"] is None
    for cat, typ, act, amt in [("fuel", "expense", "crops", 3000), ("seed", "expense", "crops", 2000), ("crop_sale", "income", "crops", 20000),
                               ("training_revenue", "income", "training", 15000), ("fodder_sale", "income", "fodder", 8000)]:
        r = await client.post("/api/v1/finance/transactions", headers=h, json={
            "transaction_type": typ, "category": cat, "amount": amt, "transaction_date": "2026-05-10", "farm_id": farm, "activity": act})
        assert r.status_code == 201, r.text
    assert (await client.post("/api/v1/finance/transactions", headers=h, json={
        "transaction_type": "expense", "category": "fuel", "amount": 5, "transaction_date": "2026-05-10", "activity": "spaceflight"})).status_code == 422
    p = (await client.get(f"/api/v1/finance/profitability?start_date=2026-05-01&end_date=2026-05-31", headers=h)).json()
    acts = {a["activity"]: a for a in p["by_activity"]}
    assert acts["crops"]["income"] == 20000.0 and acts["crops"]["expense"] == 5000.0 and acts["crops"]["net"] == 15000.0
    assert acts["training"]["net"] == 15000.0 and acts["unassigned"]["expense"] == 1000.0
    assert p["totals"]["income"] == 43000.0 and p["totals"]["expense"] == 6000.0
    by_farm = {f["farm_name"]: f for f in p["by_farm"]}
    assert by_farm["Segera"]["income"] == 43000.0 and "Unassigned (no sub-farm recorded)" in by_farm
    one = (await client.get(f"/api/v1/finance/profitability?start_date=2026-05-01&end_date=2026-05-31&activity=crops", headers=h)).json()
    assert one["totals"]["net"] == 15000.0 and len(one["by_activity"]) == 1
    only_farm = (await client.get(f"/api/v1/finance/transactions?farm_id={farm}", headers=h)).json()
    assert len(only_farm) == 5
    # the pre-existing summary endpoint is unchanged
    s = (await client.get("/api/v1/finance/summary?start_date=2026-05-01&end_date=2026-05-31", headers=h)).json()
    assert float(s["total_income"]) == 43000.0


async def test_receivables_tenant_isolation_and_validation(client):
    h1, farm1, cust1, _ = await _setup(client, "rc5@example.com")
    h2, *_ = await _setup(client, "rc6@example.com")
    assert (await client.get(f"/api/v1/receivables/customers/{cust1}/statement", headers=h2)).status_code == 404
    assert (await client.post("/api/v1/receivables/payments", headers=h2, json={
        "customer_id": cust1, "amount": 10, "entry_date": "2026-01-01"})).status_code == 404
    assert (await client.post("/api/v1/receivables/payments", headers=h1, json={
        "customer_id": cust1, "amount": -5, "entry_date": "2026-01-01"})).status_code == 422
    assert (await client.get("/api/v1/receivables/balances", headers=h2)).json()["customers_owing"] == 0

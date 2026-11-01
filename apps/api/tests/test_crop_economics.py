"""Crops sold outside the web shop, costs per planting, and profit per planting - in Finance, stock, reports.

Rules under test: every ledger posting happens at most once (checked in code AND enforced by unique indexes);
a wrong entry is voided and reversed, never edited; imports are idempotent; stock never goes out of step
with what was sold off the web; web crop orders count as crop income."""
import hashlib
import hmac
import io
import json
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings

pytestmark = pytest.mark.asyncio
H = lambda tok: {"Authorization": f"Bearer {tok}"}


async def _org(client, name="Crop Money Farm", email="cropmoney@example.com"):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": name, "full_name": "Owner One", "email": email, "password": "supersecret123"})
    h = H(reg.json()["access_token"])
    farm = (await client.post("/api/v1/farms", json={"name": "Main"}, headers=h)).json()["id"]
    return h, farm


async def _planting(client, h, farm, number="P-1", cost="5000", harvest=1000, unit="kg"):
    r = await client.post("/api/v1/crops", headers=h, json={
        "farm_id": farm, "planting_number": number, "crop_type": "maize", "planting_date": "2026-03-01",
        "acquisition_cost": cost, "yield_unit": unit})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    if harvest:
        hr = await client.post(f"/api/v1/crops/{pid}/harvests", headers=h, json={"quantity": harvest, "unit": unit})
        assert hr.status_code == 201, hr.text
    return pid


async def _sell(client, h, pid, **kw):
    body = {"sale_date": date.today().isoformat(), "quantity": "200", "unit_price": "50", **kw}
    return await client.post(f"/api/v1/crops/{pid}/sales", headers=h, json=body)


async def _one(engine, sql, **p):
    async with engine.connect() as c:
        return (await c.execute(text(sql), p)).one()


INCOME = "SELECT count(*), coalesce(sum(amount),0) FROM finance_transactions WHERE category='crop_sale' AND reference_type='crop_sale'"
REVERSALS = "SELECT count(*), coalesce(sum(amount),0) FROM finance_transactions WHERE reference_type IN ('crop_sale_void','crop_cost_void')"
COSTS_LEDGER = "SELECT count(*), coalesce(sum(amount),0) FROM finance_transactions WHERE reference_type='crop_cost'"


async def test_direct_sale_is_recorded_posted_to_finance_and_drives_profit_and_stock(client, engine):
    h, farm = await _org(client)
    pid = await _planting(client, h, farm)
    r = await _sell(client, h, pid, buyer_name="Wakulima Traders")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ledger"] == "income_posted" and body["stock_warning"] is None
    assert float(body["sale"]["amount"]) == 10000.0 and body["sale"]["in_finance"] is True and body["sale"]["unit"] == "kg"
    assert tuple(await _one(engine, INCOME)) == (1, 10000)
    row = await _one(engine, "SELECT activity, farm_id FROM finance_transactions WHERE reference_type='crop_sale'")
    assert row[0] == "crops" and str(row[1]) == farm

    e = (await client.get(f"/api/v1/crops/{pid}/economics", headers=h)).json()["summary"]
    assert float(e["revenue_direct"]) == 10000.0 and float(e["revenue_web"]) == 0.0
    assert float(e["total_investment"]) == 5000.0 and float(e["profit"]) == 5000.0
    assert float(e["quantity_harvested"]) == 1000.0 and float(e["stock_on_hand"]) == 800.0
    assert float(e["avg_price_per_unit"]) == 50.0 and float(e["cost_per_unit"]) == 5.0

    old = (await client.get(f"/api/v1/crops/{pid}/profitability", headers=h)).json()     # the pre-existing endpoint
    assert float(old["total_revenue"]) == 10000.0 and float(old["total_harvested_value"]) == 10000.0 and float(old["profit"]) == 5000.0


async def test_total_amount_can_be_given_instead_of_a_price_and_validation_holds(client, engine):
    h, farm = await _org(client)
    pid = await _planting(client, h, farm)
    ok = await client.post(f"/api/v1/crops/{pid}/sales", headers=h, json={
        "sale_date": date.today().isoformat(), "quantity": "100", "amount": "9000"})
    assert ok.status_code == 201 and float(ok.json()["sale"]["unit_price"]) == 90.0
    assert (await client.post(f"/api/v1/crops/{pid}/sales", headers=h, json={
        "sale_date": date.today().isoformat(), "quantity": "100"})).status_code == 422            # no price or total
    assert (await _sell(client, h, pid, quantity="0")).status_code == 422
    assert (await _sell(client, h, pid, unit="bags")).status_code == 422                        # harvests are in kg
    assert (await _sell(client, h, "00000000-0000-0000-0000-000000000000")).status_code == 404
    h2, _ = await _org(client, "Other Crop Farm", "othercrop@example.com")
    assert (await _sell(client, h2, pid)).status_code == 404                                    # another tenant's planting


async def test_selling_more_than_harvested_is_recorded_with_a_warning_not_refused(client, engine):
    h, farm = await _org(client)
    pid = await _planting(client, h, farm, harvest=100)
    r = await _sell(client, h, pid, quantity="150")
    assert r.status_code == 201 and "record the missing harvest" in r.json()["stock_warning"]
    e = (await client.get(f"/api/v1/crops/{pid}/economics", headers=h)).json()["summary"]
    assert float(e["stock_on_hand"]) == -50.0                                                    # honest, so it can be fixed


async def test_stock_sold_off_the_web_cannot_be_sold_again_online(client, engine):
    h, farm = await _org(client)
    pid = await _planting(client, h, farm)                                                       # 1000 kg harvested
    assert (await _sell(client, h, pid, quantity="800")).status_code == 201                      # 800 kg sold off the web
    cust = (await client.post("/api/v1/customers", headers=h, json={"name": "Online Buyer", "email": "ob@example.com"})).json()["id"]
    too_much = await client.post("/api/v1/orders", headers=h, json={
        "customer_id": cust, "items": [{"crop_planting_id": pid, "quantity": "300", "price": "60"}]})
    assert too_much.status_code == 409 and "200" in too_much.text                                # only 200 kg left for the shop
    fits = await client.post("/api/v1/orders", headers=h, json={
        "customer_id": cust, "items": [{"crop_planting_id": pid, "quantity": "200", "price": "60"}]})
    assert fits.status_code == 201, fits.text


async def test_voiding_a_sale_reverses_finance_restores_stock_and_cannot_repeat(client, engine):
    h, farm = await _org(client)
    pid = await _planting(client, h, farm)
    sale = (await _sell(client, h, pid)).json()["sale"]
    v = await client.post(f"/api/v1/crops/sales/{sale['id']}/void", headers=h, json={"reason": "Typed the wrong quantity"})
    assert v.status_code == 200 and v.json()["voided_at"] and v.json()["void_reason"] == "Typed the wrong quantity"
    assert tuple(await _one(engine, REVERSALS)) == (1, -10000)                                   # reversed, not deleted
    net = (await _one(engine, "SELECT coalesce(sum(amount),0) FROM finance_transactions WHERE category='crop_sale'"))[0]
    assert float(net) == 0.0                                                                     # books net to zero
    e = (await client.get(f"/api/v1/crops/{pid}/economics", headers=h)).json()
    assert float(e["summary"]["revenue_direct"]) == 0.0 and float(e["summary"]["stock_on_hand"]) == 1000.0
    assert e["direct_sales"][0]["voided_at"] is not None                                         # history is kept
    assert (await client.post(f"/api/v1/crops/sales/{sale['id']}/void", headers=h, json={"reason": "again please"})).status_code == 409
    assert tuple(await _one(engine, REVERSALS)) == (1, -10000)                                   # still one reversal
    assert (await client.post(f"/api/v1/crops/sales/{sale['id']}/void", headers=h, json={"reason": "x"})).status_code == 422


async def test_sale_on_credit_is_charged_to_the_customer_and_must_be_corrected_there(client, engine):
    h, farm = await _org(client)
    pid = await _planting(client, h, farm)
    cust = (await client.post("/api/v1/customers", headers=h, json={"name": "Co-op Buyer", "email": "coop@example.com"})).json()["id"]
    r = await _sell(client, h, pid, customer_id=cust)
    assert r.status_code == 201 and r.json()["ledger"] == "charged_to_customer_account"
    assert tuple(await _one(engine, INCOME)) == (0, 0)                                           # no income until they pay
    charge = await _one(engine, "SELECT count(*), coalesce(sum(amount),0) FROM account_entries WHERE reference_type='crop_sale' AND entry_type='charge'")
    assert tuple(charge) == (1, 10000)
    e = (await client.get(f"/api/v1/crops/{pid}/economics", headers=h)).json()["summary"]
    assert float(e["revenue_direct"]) == 10000.0                                                 # the sale happened: it is revenue
    blocked = await client.post(f"/api/v1/crops/sales/{r.json()['sale']['id']}/void", headers=h, json={"reason": "wrong buyer"})
    assert blocked.status_code == 409 and "customer's account" in blocked.text


async def test_costs_are_recorded_posted_voided_and_roll_into_profit(client, engine):
    h, farm = await _org(client)
    pid = await _planting(client, h, farm)
    await _sell(client, h, pid)
    for cat, amt in (("fertilizer", "1500"), ("labour", "2500"), ("fuel", "700")):
        r = await client.post(f"/api/v1/crops/{pid}/costs", headers=h, json={"cost_date": "2026-04-01", "category": cat, "amount": amt})
        assert r.status_code == 201 and r.json()["in_finance"] is True
    assert tuple(await _one(engine, COSTS_LEDGER)) == (3, 4700)
    row = await _one(engine, "SELECT category, activity FROM finance_transactions WHERE reference_type='crop_cost' AND category='labour'")
    assert tuple(row) == ("labour", "crops")
    e = (await client.get(f"/api/v1/crops/{pid}/economics", headers=h)).json()["summary"]
    assert (float(e["input_cost"]), float(e["labour_cost"]), float(e["other_cost"])) == (1500.0, 2500.0, 700.0)
    assert float(e["total_investment"]) == 9700.0 and float(e["profit"]) == 300.0                # 10000 - (5000 + 4700)
    assert (await client.post(f"/api/v1/crops/{pid}/costs", headers=h, json={"cost_date": "2026-04-01", "category": "spaceship", "amount": "5"})).status_code == 422

    costs = (await client.get(f"/api/v1/crops/{pid}/costs", headers=h)).json()
    fuel = next(c for c in costs if c["category"] == "fuel")
    assert (await client.post(f"/api/v1/crops/costs/{fuel['id']}/void", headers=h, json={"reason": "Not for this plot"})).status_code == 200
    assert tuple(await _one(engine, REVERSALS)) == (1, -700)
    e = (await client.get(f"/api/v1/crops/{pid}/economics", headers=h)).json()["summary"]
    assert float(e["total_investment"]) == 9000.0 and float(e["profit"]) == 1000.0


async def test_database_refuses_a_second_posting_for_the_same_sale(client, engine):
    h, farm = await _org(client)
    pid = await _planting(client, h, farm)
    await _sell(client, h, pid)
    with pytest.raises(IntegrityError):
        async with engine.begin() as c:
            await c.execute(text(
                "INSERT INTO finance_transactions (id, organization_id, transaction_type, category, amount, currency, reference_type, "
                "reference_id, transaction_date, created_at) SELECT gen_random_uuid(), organization_id, 'income', 'crop_sale', 1, 'KES', "
                "reference_type, reference_id, transaction_date, now() FROM finance_transactions WHERE reference_type='crop_sale' LIMIT 1"))


CSV_SALES = (
    "Plot,Date,Qty,Unit,Price,Buyer,Notes\n"
    "P-1,2026-05-01,100,kg,55,Mama Mboga,market day\n"
    "P-1,02/05/2026,50,kg,60,,\n"
    "P-1,2026-05-03,10,kg,50,Local shop,\n"
    "P-1,2026-05-03,10,kg,50,Local shop,\n"          # an identical second row is a real second sale, not a duplicate
)


async def _import(client, h, kind, content, name="rows.csv", dry=False, post=True):
    return await client.post(f"/api/v1/crops/{kind}/import?dry_run={str(dry).lower()}&post_to_finance={str(post).lower()}",
                             headers=h, files={"file": (name, content if isinstance(content, bytes) else content.encode(), "text/csv")})


async def test_sales_import_previews_applies_once_and_never_duplicates(client, engine):
    h, farm = await _org(client)
    pid = await _planting(client, h, farm)
    dry = (await _import(client, h, "sales", CSV_SALES, dry=True)).json()
    assert dry["ok"] and dry["rows"] == 4 and dry["created"] == 4 and dry["already_imported"] == 0
    assert tuple(await _one(engine, INCOME)) == (0, 0)                                           # a preview saves nothing

    real = (await _import(client, h, "sales", CSV_SALES)).json()
    assert real["ok"] and real["created"] == 4 and real["posted_to_finance"] == 4
    assert tuple(await _one(engine, INCOME)) == (4, 100 * 55 + 50 * 60 + 10 * 50 + 10 * 50)

    again = (await _import(client, h, "sales", CSV_SALES)).json()                                # same file again
    assert again["ok"] and again["created"] == 0 and again["already_imported"] == 4 and again["posted_to_finance"] == 0
    assert tuple(await _one(engine, INCOME)) == (4, 9500)
    assert (await _one(engine, "SELECT count(*) FROM crop_sales"))[0] == 4

    more = (await _import(client, h, "sales", CSV_SALES + "P-1,2026-05-09,5,kg,50,,\n")).json()  # a new row appended later
    assert more["created"] == 1 and more["already_imported"] == 4
    assert (await _one(engine, "SELECT count(*) FROM crop_sales"))[0] == 5


async def test_sales_import_reads_excel_and_refuses_the_whole_file_on_any_error(client, engine):
    import openpyxl
    h, farm = await _org(client)
    pid = await _planting(client, h, farm)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Planting Number", "Sale Date", "Quantity", "Unit Price"])
    ws.append(["P-1", date(2026, 5, 1), 40, 70])
    buf = io.BytesIO()
    wb.save(buf)
    ok = (await _import(client, h, "sales", buf.getvalue(), name="sales.xlsx")).json()
    assert ok["ok"] and ok["created"] == 1 and (await _one(engine, "SELECT amount FROM crop_sales"))[0] == 2800

    bad = "planting_number,date,quantity,unit_price\nP-1,2026-05-02,10,50\nNOPE,2026-05-02,10,50\nP-1,not-a-date,10,50\nP-1,2026-05-02,10,\n"
    res = (await _import(client, h, "sales", bad)).json()
    assert res["ok"] is False and {e["row"] for e in res["errors"]} == {3, 4, 5}
    assert (await _one(engine, "SELECT count(*) FROM crop_sales"))[0] == 1                      # nothing from the bad file landed
    assert (await _import(client, h, "sales", b"x" * (5 * 1024 * 1024 + 10))).status_code == 413


async def test_costs_import_understands_common_wording_and_is_idempotent(client, engine):
    h, farm = await _org(client)
    pid = await _planting(client, h, farm)
    csv_costs = "Plot,Date,Type,Cost,Item\nP-1,2026-04-02,Fertiliser,2000,CAN 50kg\nP-1,2026-04-03,Labor,1500,weeding\nP-1,2026-04-04,Pesticide,800,\n"
    r = (await _import(client, h, "costs", csv_costs)).json()
    assert r["ok"] and r["created"] == 3 and r["posted_to_finance"] == 3
    cats = {row[0] for row in (await (await engine.connect()).execute(text("SELECT category FROM crop_costs")))}
    assert cats == {"fertilizer", "labour", "chemicals"}
    again = (await _import(client, h, "costs", csv_costs)).json()
    assert again["created"] == 0 and again["already_imported"] == 3
    assert tuple(await _one(engine, COSTS_LEDGER)) == (3, 4300)


async def test_catch_up_books_what_never_reached_finance_once_and_guards_hand_typed_entries(client, engine):
    h, farm = await _org(client)
    pid = await _planting(client, h, farm, cost="5000")
    await _import(client, h, "sales", CSV_SALES, post=False)
    await _import(client, h, "costs", "plot,date,category,amount\nP-1,2026-04-02,labour,1000\n", post=False)
    assert tuple(await _one(engine, INCOME)) == (0, 0)

    prev = (await client.post("/api/v1/crops/ledger-sync", headers=h)).json()                     # default = preview
    assert prev["dry_run"] and prev["sales"]["missing"] == 4 and prev["costs"]["missing"] == 1 and prev["plantings"]["missing"] == 1
    assert prev["needs_confirmation"] is False and tuple(await _one(engine, INCOME)) == (0, 0)

    done = (await client.post("/api/v1/crops/ledger-sync?dry_run=false", headers=h)).json()
    assert (done["sales"]["posted"], done["costs"]["posted"], done["plantings"]["posted"]) == (4, 1, 1)
    assert tuple(await _one(engine, INCOME)) == (4, 9500)
    seed = await _one(engine, "SELECT category, amount FROM finance_transactions WHERE reference_type='crop_planting'")
    assert (seed[0], float(seed[1])) == ("seed", 5000.0)                                           # the planting's own purchase cost

    repeat = (await client.post("/api/v1/crops/ledger-sync?dry_run=false", headers=h)).json()
    assert (repeat["sales"]["posted"], repeat["costs"]["posted"], repeat["plantings"]["posted"]) == (0, 0, 0)
    assert tuple(await _one(engine, INCOME)) == (4, 9500)

    # hand-typed entries in Finance block a blind post
    h2, farm2 = await _org(client, "Typed Farm", "typed@example.com")
    pid2 = await _planting(client, h2, farm2)
    await _import(client, h2, "sales", CSV_SALES, post=False)
    typed = await client.post("/api/v1/finance/transactions", headers=h2, json={
        "transaction_type": "income", "category": "crop_sale", "amount": "9000", "transaction_date": "2026-05-01", "activity": "crops"})
    assert typed.status_code == 201
    p = (await client.post("/api/v1/crops/ledger-sync", headers=h2)).json()
    assert p["needs_confirmation"] is True and p["overlap"]["manual_sales"]["count"] == 1
    blocked = await client.post("/api/v1/crops/ledger-sync?dry_run=false", headers=h2)
    assert blocked.status_code == 409 and "twice" in blocked.text
    ok = await client.post("/api/v1/crops/ledger-sync?dry_run=false&confirm_overlap=true", headers=h2)
    assert ok.status_code == 200 and ok.json()["sales"]["posted"] == 4


async def test_sales_panel_and_crop_report_include_direct_sales_and_ignore_voided_ones(client, engine):
    h, farm = await _org(client)
    pid = await _planting(client, h, farm)
    a = (await _sell(client, h, pid)).json()["sale"]
    b = (await _sell(client, h, pid, quantity="100")).json()["sale"]                              # 5000
    await client.post(f"/api/v1/crops/sales/{a['id']}/void", headers=h, json={"reason": "duplicate entry"})
    sales = (await client.get("/api/v1/reports/analytics?months=3", headers=h)).json()["sales"]
    assert sales["crop_sales"] == 1 and float(sales["crop_sales_revenue"]) == 5000.0
    assert float(sales["combined_revenue"]) == 5000.0 and sales["total_orders"] == 0 and float(sales["total_revenue"]) == 0.0
    assert sum(m["crop_sales"] for m in sales["monthly"]) == 1

    rep = (await client.get("/api/v1/reports/profitability/crops", headers=h)).json()
    assert rep["totals"]["plantings"] == 1 and float(rep["totals"]["revenue_direct"]) == 5000.0
    row = rep["plantings"][0]
    assert row["planting_number"] == "P-1" and float(row["profit"]) == 0.0 and float(row["total_investment"]) == 5000.0


async def test_web_crop_order_counts_as_crop_income_and_adds_to_planting_revenue(client, engine):
    settings = get_settings()
    h, farm = await _org(client)
    pid = await _planting(client, h, farm)
    await _sell(client, h, pid, quantity="300")                                                    # 300 off the web, 5000... 15000
    cust = (await client.post("/api/v1/customers", headers=h, json={"name": "Web Buyer", "email": "wb@example.com"})).json()["id"]
    order = await client.post("/api/v1/orders", headers=h, json={
        "customer_id": cust, "items": [{"crop_planting_id": pid, "quantity": "100", "price": "80"}]})
    assert order.status_code == 201, order.text
    oid = order.json()["id"]
    await client.post(f"/api/v1/orders/{oid}/status", headers=h, json={"status": "payment_pending"})
    pay = await client.post("/api/v1/payments/mock", headers=h, json={"order_id": oid, "phone_or_token": "254700000000"})
    body = json.dumps({"event_id": "evt-crop", "provider_reference": pay.json()["provider_reference"], "status": "successful"}).encode()
    sig = hmac.new(settings.MOCK_PAYMENT_SECRET.encode(), body, hashlib.sha256).hexdigest()
    await client.post("/api/v1/payments/webhooks/mock", content=body, headers={"Content-Type": "application/json", "X-Mock-Signature": sig})

    row = await _one(engine, "SELECT category, activity, amount FROM finance_transactions WHERE reference_type='order'")
    assert (row[0], row[1], float(row[2])) == ("crop_sale", "crops", 8000.0)                       # not livestock_sale
    e = (await client.get(f"/api/v1/crops/{pid}/economics", headers=h)).json()
    assert float(e["summary"]["revenue_web"]) == 8000.0 and float(e["summary"]["revenue_direct"]) == 15000.0
    assert float(e["summary"]["total_revenue"]) == 23000.0 and float(e["summary"]["stock_on_hand"]) == 600.0
    assert len(e["web_sales"]) == 1 and float(e["web_sales"][0]["amount"]) == 8000.0


async def test_plain_planting_endpoints_are_unchanged_for_farms_that_never_use_the_new_features(client, engine):
    h, farm = await _org(client)
    pid = await _planting(client, h, farm, harvest=0)
    old = (await client.get(f"/api/v1/crops/{pid}/profitability", headers=h)).json()
    assert float(old["total_investment"]) == 5000.0 and old["total_harvested_value"] is None
    assert (float(old["input_cost"]), float(old["labor_cost"]), float(old["other_cost"])) == (0.0, 0.0, 0.0)
    assert float(old["total_revenue"]) == 0.0 and float(old["profit"]) == -5000.0


async def test_crop_money_endpoints_are_permissioned_and_tenant_isolated(client, engine):
    h, farm = await _org(client)
    pid = await _planting(client, h, farm)
    sale = (await _sell(client, h, pid)).json()["sale"]
    h2, _ = await _org(client, "Rival Crop Farm", "rival@example.com")
    assert (await client.get(f"/api/v1/crops/{pid}/economics", headers=h2)).status_code == 404
    assert (await client.get(f"/api/v1/crops/{pid}/sales", headers=h2)).status_code == 404
    assert (await client.post(f"/api/v1/crops/sales/{sale['id']}/void", headers=h2, json={"reason": "not yours"})).status_code == 404
    assert (await client.post("/api/v1/crops/ledger-sync", headers=h2)).json()["sales"]["missing"] == 0
    assert (await client.post("/api/v1/crops/ledger-sync")).status_code in (401, 403)
    assert (await client.get("/api/v1/reports/profitability/crops", headers=h2)).json()["plantings"] == []


async def test_crop_sale_on_credit_shows_in_the_customers_balance_and_is_counted_once_in_sales_reports(client, engine):
    h, farm = await _org(client)
    pid = await _planting(client, h, farm)
    cust = (await client.post("/api/v1/customers", headers=h, json={"name": "Credit Buyer", "email": "cb@example.com"})).json()["id"]
    assert (await _sell(client, h, pid, customer_id=cust)).status_code == 201
    bal = (await client.get("/api/v1/receivables/balances", headers=h)).json()
    assert bal["customers_owing"] == 1 and float(bal["total_outstanding"]) == 10000.0
    stmt = (await client.get(f"/api/v1/receivables/customers/{cust}/statement", headers=h)).json()
    assert float(stmt["balance"]) == 10000.0
    today = date.today().isoformat()
    by_person = (await client.get(f"/api/v1/receivables/sales-by-salesperson?start_date={today}&end_date={today}", headers=h)).json()
    assert sum(r["sales"] for r in by_person) == 1 and sum(r["amount"] for r in by_person) == 10000.0


async def test_a_sale_voided_before_it_reached_finance_is_never_posted_by_the_catch_up(client, engine):
    h, farm = await _org(client)
    pid = await _planting(client, h, farm, cost="0")
    a = (await _sell(client, h, pid, post_to_finance=False)).json()["sale"]
    await _sell(client, h, pid, quantity="100", post_to_finance=False)
    v = await client.post(f"/api/v1/crops/sales/{a['id']}/void", headers=h, json={"reason": "entered twice by mistake"})
    assert v.status_code == 200
    assert tuple(await _one(engine, REVERSALS)) == (0, 0)                      # nothing in the ledger, so nothing to reverse
    prev = (await client.post("/api/v1/crops/ledger-sync", headers=h)).json()
    assert prev["sales"]["missing"] == 1 and prev["sales"]["missing_amount"] == 5000.0   # only the live sale
    done = (await client.post("/api/v1/crops/ledger-sync?dry_run=false", headers=h)).json()
    assert done["sales"]["posted"] == 1 and tuple(await _one(engine, INCOME)) == (1, 5000)

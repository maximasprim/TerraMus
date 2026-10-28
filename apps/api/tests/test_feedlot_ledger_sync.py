"""Feedlot sales and purchases must reach Finance, the dashboard and the reports - exactly once.

The finance ledger is append-only, so a duplicate can never be undone. These tests cover the
three layers that prevent one: keyed postings, database unique indexes, and the overlap guard
on the catch-up for data imported before this existed."""
import pathlib
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.asyncio
FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sahara_oasis_bulls_wg_sample.xlsx"
H = lambda tok: {"Authorization": f"Bearer {tok}"}


async def _org(client, engine, name="Ledger Farm", email="ledger@example.com"):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": name, "full_name": "Owner One", "email": email, "password": "supersecret123"})
    h = H(reg.json()["access_token"])
    await client.post("/api/v1/farms", json={"name": "Main"}, headers=h)
    async with engine.begin() as c:      # the Free plan caps animals; a 130-head feedlot needs more
        await c.execute(text("UPDATE subscription_tiers SET max_animals = NULL"))
    return h


async def _import(client, h, *, post=True, dry_run=False):
    with open(FIXTURE, "rb") as f:
        r = await client.post(
            f"/api/v1/feedlot/worksheet/import?dry_run={str(dry_run).lower()}&post_to_finance={str(post).lower()}",
            headers=h, files={"file": (FIXTURE.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    return r.json()


async def _one(engine, sql, **params):
    async with engine.connect() as c:
        return (await c.execute(text(sql), params)).one()


SALES_SQL = "SELECT count(*), coalesce(sum(amount),0) FROM finance_transactions WHERE reference_type='feedlot_sale'"
BUY_SQL = ("SELECT count(*), coalesce(sum(amount),0) FROM finance_transactions "
           "WHERE reference_type='animal' AND category='livestock_acquisition'")
EXITS_SQL = "SELECT count(*), coalesce(sum(amount),0) FROM feedlot_exits WHERE exit_type='sold' AND amount > 0"
ANIMALS_SQL = "SELECT count(*), coalesce(sum(a.acquisition_cost),0) FROM feedlot_animals f JOIN animals a ON a.id=f.animal_id WHERE a.acquisition_cost > 0"


async def test_import_books_every_sale_and_purchase_in_finance_once_and_reimport_adds_nothing(client, engine):
    h = await _org(client, engine)
    dry = await _import(client, h, dry_run=True)
    assert dry["created"]["finance_sales"] == 108 and dry["created"]["finance_purchases"] == 131
    assert tuple(await _one(engine, SALES_SQL)) == (0, 0)             # a preview books nothing

    real = await _import(client, h)
    assert real["created"]["finance_sales"] == 108 and real["created"]["finance_purchases"] == 131
    n_sales, amt_sales = await _one(engine, SALES_SQL)
    n_exits, amt_exits = await _one(engine, EXITS_SQL)
    assert (n_sales, float(amt_sales)) == (n_exits, float(amt_exits)) and n_sales == 108
    n_buy, amt_buy = await _one(engine, BUY_SQL)
    n_animals, amt_animals = await _one(engine, ANIMALS_SQL)
    assert (n_buy, float(amt_buy)) == (n_animals, float(amt_animals)) and n_buy == 131

    again = await _import(client, h)                                   # same workbook again
    assert again["created"].get("finance_sales", 0) == 0 and again["created"].get("finance_purchases", 0) == 0
    assert tuple(await _one(engine, SALES_SQL)) == (n_sales, amt_sales)
    assert tuple(await _one(engine, BUY_SQL)) == (n_buy, amt_buy)


async def test_postings_use_the_real_dates_not_today(client, engine):
    h = await _org(client, engine)
    await _import(client, h)
    first, last = await _one(engine, "SELECT min(transaction_date), max(transaction_date) FROM finance_transactions "
                                     "WHERE reference_type IN ('feedlot_sale','animal')")
    assert first == date(2025, 12, 11) and last < date.today()          # delivery of batch 1 ... last sale
    mismatched = (await _one(engine, "SELECT count(*) FROM finance_transactions t JOIN feedlot_exits e ON e.id=t.reference_id "
                                     "WHERE t.reference_type='feedlot_sale' AND t.transaction_date <> e.exit_date"))[0]
    assert mismatched == 0


async def test_finance_dashboard_and_reports_all_see_imported_money(client, engine):
    h = await _org(client, engine)
    await _import(client, h)
    _, amt_sales = await _one(engine, SALES_SQL)
    _, amt_buy = await _one(engine, BUY_SQL)

    s = (await client.get("/api/v1/finance/summary?start_date=2025-01-01&end_date=2030-12-31", headers=h)).json()
    assert float(s["total_income"]) == pytest.approx(float(amt_sales)) and float(s["total_expense"]) == pytest.approx(float(amt_buy))

    tx = (await client.get("/api/v1/finance/transactions?activity=feedlot&limit=500", headers=h)).json()
    assert {t["category"] for t in tx} == {"livestock_sale", "livestock_acquisition"}

    a = (await client.get("/api/v1/reports/analytics?months=24", headers=h)).json()
    window_start = date.today().replace(day=1)
    for _ in range(23):
        window_start = (window_start.replace(day=1) - __import__("datetime").timedelta(days=1)).replace(day=1)
    exp_head, exp_amt = await _one(engine, "SELECT count(*), coalesce(sum(amount),0) FROM feedlot_exits "
                                           "WHERE exit_type='sold' AND amount>0 AND exit_date >= :s", s=window_start)
    sales = a["sales"]
    assert sales["feedlot_head"] == exp_head and float(sales["feedlot_revenue"]) == pytest.approx(float(exp_amt))
    assert sales["total_orders"] == 0 and float(sales["total_revenue"]) == 0.0      # web numbers unchanged
    assert float(sales["combined_revenue"]) == pytest.approx(float(sales["feedlot_revenue"]))
    assert sum(m["feedlot_head"] for m in sales["monthly"]) == exp_head


async def test_database_refuses_a_duplicate_posting_even_if_the_code_were_bypassed(client, engine):
    h = await _org(client, engine)
    await _import(client, h)
    with pytest.raises(IntegrityError):
        async with engine.begin() as c:
            await c.execute(text(
                "INSERT INTO finance_transactions (id, organization_id, transaction_type, category, amount, currency, "
                "reference_type, reference_id, transaction_date, created_at) "
                "SELECT gen_random_uuid(), organization_id, 'income', 'livestock_sale', 1, 'KES', reference_type, "
                "reference_id, transaction_date, now() FROM finance_transactions WHERE reference_type='feedlot_sale' LIMIT 1"))
    with pytest.raises(IntegrityError):
        async with engine.begin() as c:
            await c.execute(text(
                "INSERT INTO finance_transactions (id, organization_id, transaction_type, category, amount, currency, "
                "reference_type, reference_id, transaction_date, created_at) "
                "SELECT gen_random_uuid(), organization_id, 'expense', 'livestock_acquisition', 1, 'KES', reference_type, "
                "reference_id, transaction_date, now() FROM finance_transactions WHERE reference_type='animal' "
                "AND category='livestock_acquisition' LIMIT 1"))


async def test_catch_up_for_data_imported_earlier_previews_then_posts_once(client, engine):
    h = await _org(client, engine)
    await _import(client, h, post=False)                                # imported "the old way": nothing in Finance
    assert tuple(await _one(engine, SALES_SQL)) == (0, 0)

    prev = (await client.post("/api/v1/feedlot/ledger-sync", headers=h)).json()      # default = preview
    assert prev["dry_run"] is True and prev["sales"]["missing"] == 108 and prev["purchases"]["missing"] == 131
    assert prev["needs_confirmation"] is False and len(prev["sample"]) > 0
    assert tuple(await _one(engine, SALES_SQL)) == (0, 0)               # preview posts nothing

    done = (await client.post("/api/v1/feedlot/ledger-sync?dry_run=false", headers=h)).json()
    assert done["sales"]["posted"] == 108 and done["purchases"]["posted"] == 131
    n_sales, amt_sales = await _one(engine, SALES_SQL)
    assert n_sales == 108 and float(amt_sales) == pytest.approx(float((await _one(engine, EXITS_SQL))[1]))

    repeat = (await client.post("/api/v1/feedlot/ledger-sync?dry_run=false", headers=h)).json()
    assert repeat["sales"]["posted"] == 0 and repeat["purchases"]["posted"] == 0
    assert repeat["sales"]["already_recorded"] == 108 and repeat["purchases"]["already_recorded"] == 131
    assert tuple(await _one(engine, SALES_SQL)) == (n_sales, amt_sales)


async def test_catch_up_refuses_to_post_over_manually_typed_entries_unless_confirmed(client, engine):
    h = await _org(client, engine)
    await _import(client, h, post=False)
    manual = await client.post("/api/v1/finance/transactions", headers=h, json={
        "transaction_type": "income", "category": "livestock_sale", "amount": "250000",
        "transaction_date": "2026-03-01", "description": "Bulls sold - typed by hand"})
    assert manual.status_code == 201, manual.text

    prev = (await client.post("/api/v1/feedlot/ledger-sync", headers=h)).json()
    assert prev["needs_confirmation"] is True and prev["overlap"]["manual_sales"]["count"] == 1
    assert float(prev["overlap"]["manual_sales"]["total"]) == 250000.0

    blocked = await client.post("/api/v1/feedlot/ledger-sync?dry_run=false", headers=h)
    assert blocked.status_code == 409 and "twice" in blocked.text
    assert tuple(await _one(engine, SALES_SQL)) == (0, 0)               # nothing was posted

    ok = await client.post("/api/v1/feedlot/ledger-sync?dry_run=false&confirm_overlap=true", headers=h)
    assert ok.status_code == 200 and ok.json()["sales"]["posted"] == 108


async def test_sale_typed_into_the_feedlot_is_booked_once_and_not_rebooked_by_the_catch_up(client, engine):
    h = await _org(client, engine, "Manual Sale Farm", "manual@example.com")
    farm = (await client.get("/api/v1/farms", headers=h)).json()[0]["id"]
    b = (await client.post("/api/v1/feedlot/intake-batches", headers=h, json={
        "delivered_on": "2025-12-11", "farm_id": farm, "head_purchased": 1, "purchase_cost": "50000"})).json()
    await client.post(f"/api/v1/feedlot/intake-batches/{b['id']}/animals", headers=h, json={
        "animals": [{"animal_number": "M01", "entry_weight_kg": 200}]})
    sb = (await client.post("/api/v1/feedlot/sale-batches", headers=h, json={"sold_on": "2026-06-22", "price_per_kg": "330"})).json()
    sold = (await client.post(f"/api/v1/feedlot/sale-batches/{sb['id']}/sales", headers=h, json={
        "entries": [{"animal_number": "M01", "exit_weight_kg": 300}]})).json()
    assert sold["sold"] == 1
    assert tuple(await _one(engine, SALES_SQL)) == (1, 99000)
    prev = (await client.post("/api/v1/feedlot/ledger-sync", headers=h)).json()
    assert prev["sales"]["missing"] == 0 and prev["sales"]["already_recorded"] == 1
    done = (await client.post("/api/v1/feedlot/ledger-sync?dry_run=false", headers=h)).json()
    assert done["sales"]["posted"] == 0
    assert tuple(await _one(engine, SALES_SQL)) == (1, 99000)


async def test_a_sale_without_a_price_is_never_booked_as_zero(client, engine):
    h = await _org(client, engine)
    await _import(client, h, post=False)
    async with engine.begin() as c:
        await c.execute(text("UPDATE feedlot_exits SET amount = 0 WHERE id IN "
                             "(SELECT id FROM feedlot_exits WHERE exit_type='sold' LIMIT 3)"))
    prev = (await client.post("/api/v1/feedlot/ledger-sync", headers=h)).json()
    assert prev["sales"]["no_price"] == 3 and prev["sales"]["missing"] == 105
    done = (await client.post("/api/v1/feedlot/ledger-sync?dry_run=false", headers=h)).json()
    assert done["sales"]["posted"] == 105
    assert (await _one(engine, SALES_SQL))[0] == 105


async def test_ledger_sync_is_permissioned_and_tenant_isolated(client, engine):
    h1 = await _org(client, engine)
    await _import(client, h1, post=False)
    h2 = await _org(client, engine, "Other Ledger Farm", "other-ledger@example.com")
    other = (await client.post("/api/v1/feedlot/ledger-sync", headers=h2)).json()
    assert other["sales"]["missing"] == 0 and other["purchases"]["missing"] == 0     # sees only its own data
    assert (await client.post("/api/v1/feedlot/ledger-sync")).status_code in (401, 403)


async def test_manually_registered_animal_purchase_is_recognised_so_the_catch_up_never_rebooks_it(client, engine):
    """Animals registered through the feedlot screen get their purchase booked by the existing event handler.
    The catch-up must recognise that entry (same key) instead of booking the purchase a second time."""
    h = await _org(client, engine, "Manual Buy Farm", "manualbuy@example.com")
    farm = (await client.get("/api/v1/farms", headers=h)).json()[0]["id"]
    b = (await client.post("/api/v1/feedlot/intake-batches", headers=h, json={
        "delivered_on": "2025-12-11", "farm_id": farm, "head_purchased": 2, "purchase_cost": "100000"})).json()
    await client.post(f"/api/v1/feedlot/intake-batches/{b['id']}/animals", headers=h, json={
        "animals": [{"animal_number": "B01", "entry_weight_kg": 200}, {"animal_number": "B02", "entry_weight_kg": 210}]})
    n_buy, amt_buy = await _one(engine, BUY_SQL)
    assert n_buy == 2 and float(amt_buy) == 100000.0                   # booked by the existing handler
    prev = (await client.post("/api/v1/feedlot/ledger-sync", headers=h)).json()
    assert prev["purchases"]["missing"] == 0 and prev["purchases"]["already_recorded"] == 2
    done = (await client.post("/api/v1/feedlot/ledger-sync?dry_run=false", headers=h)).json()
    assert done["purchases"]["posted"] == 0
    assert tuple(await _one(engine, BUY_SQL)) == (n_buy, amt_buy)


def _window_start(months: int = 24) -> date:
    d = date.today().replace(day=1)
    for _ in range(months - 1):
        d = (d - __import__("datetime").timedelta(days=1)).replace(day=1)
    return d


async def test_sales_panel_shows_what_was_spent_buying_bulls_and_it_matches_finance(client, engine):
    h = await _org(client, engine)
    await _import(client, h)
    start = _window_start()
    sales = (await client.get("/api/v1/reports/analytics?months=24", headers=h)).json()["sales"]

    exp_head, exp_cost = await _one(engine, (
        "SELECT count(*), coalesce(sum(a.acquisition_cost),0) FROM feedlot_animals f JOIN animals a ON a.id=f.animal_id "
        "WHERE a.acquisition_cost > 0 AND f.received_on >= :s"), s=start)
    assert exp_head == 131 and sales["feedlot_purchase_head"] == exp_head       # culled and sold bulls were bought too
    assert float(sales["feedlot_purchases"]) == pytest.approx(float(exp_cost))
    assert sum(m["feedlot_purchase_head"] for m in sales["monthly"]) == exp_head
    assert sum(float(m["feedlot_purchases"]) for m in sales["monthly"]) == pytest.approx(float(exp_cost))

    # Reports and Finance must tell the same story about the same money.
    ledger = (await _one(engine, "SELECT coalesce(sum(amount),0) FROM finance_transactions "
                                 "WHERE reference_type='animal' AND category='livestock_acquisition' AND transaction_date >= :s", s=start))[0]
    assert float(sales["feedlot_purchases"]) == pytest.approx(float(ledger))

    # bought and sold land in the months they happened (batch 1 was delivered December 2025)
    dec = next(m for m in sales["monthly"] if m["month"] == "2025-12")
    assert dec["feedlot_purchase_head"] > 0 and float(dec["feedlot_purchases"]) > 0
    # existing numbers are untouched
    assert sales["total_orders"] == 0 and float(sales["total_revenue"]) == 0.0
    assert float(sales["combined_revenue"]) == pytest.approx(float(sales["feedlot_revenue"]))


async def test_purchases_in_the_sales_panel_do_not_depend_on_the_finance_sync(client, engine):
    h = await _org(client, engine)
    await _import(client, h, post=False)                                # nothing booked in Finance
    assert tuple(await _one(engine, BUY_SQL)) == (0, 0)
    sales = (await client.get("/api/v1/reports/analytics?months=24", headers=h)).json()["sales"]
    assert sales["feedlot_purchase_head"] == 131 and float(sales["feedlot_purchases"]) > 0


async def test_animals_with_no_cost_are_not_counted_as_purchases(client, engine):
    h = await _org(client, engine)
    await _import(client, h, post=False)
    async with engine.begin() as c:
        await c.execute(text("UPDATE animals SET acquisition_cost = 0 WHERE id IN "
                             "(SELECT animal_id FROM feedlot_animals LIMIT 2)"))
    sales = (await client.get("/api/v1/reports/analytics?months=24", headers=h)).json()["sales"]
    assert sales["feedlot_purchase_head"] == 129


async def test_orgs_without_a_feedlot_and_other_tenants_see_zero_feedlot_purchases(client, engine):
    h1 = await _org(client, engine)
    await _import(client, h1)
    h2 = await _org(client, engine, "No Feedlot Farm", "nofeedlot@example.com")
    s = (await client.get("/api/v1/reports/analytics?months=6", headers=h2)).json()["sales"]
    assert s["feedlot_purchase_head"] == 0 and float(s["feedlot_purchases"]) == 0.0 and s["feedlot_head"] == 0
    assert all(m["feedlot_purchase_head"] == 0 for m in s["monthly"])

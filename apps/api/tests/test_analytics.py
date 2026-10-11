"""Tests for GET /reports/analytics (tenant) and GET /platform/analytics (superadmin).

Every expected number below is worked out by hand from the seed data, so a wrong
GROUP BY, a missing org filter, a timezone slip or a mis-scoped join fails here.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.commerce.models import Order
from app.modules.crops.models import HarvestRecord
from app.modules.dairy.models import MilkProductionRecord
from app.modules.identity.models import Organization
from app.modules.livestock.models import Animal
from app.modules.payments.models import Payment
from tests.test_platform_admin import _make_platform_admin, _platform_login, _register_org

pytestmark = pytest.mark.asyncio

D = Decimal


def _first_of_previous_month(day: date) -> date:
    return (day.replace(day=1) - timedelta(days=1)).replace(day=1)


async def _org_id(engine, name: str) -> uuid.UUID:
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        return (await session.execute(select(Organization.id).where(Organization.name == name))).scalar_one()


async def _seed_farm(client, engine, name="Analytics Farm", email="analytics@example.com"):
    """One org with data in every module. Returns (headers, org_id, today-in-org-tz)."""
    tenant = await _register_org(client, name, email)
    headers = {"Authorization": f"Bearer {tenant['access_token']}"}
    org_id = await _org_id(engine, name)
    today = date.fromisoformat((await client.get("/api/v1/reports/analytics?months=1", headers=headers)).json()["end_date"])
    prev_month_day = _first_of_previous_month(today)
    now = datetime.now(timezone.utc)

    # finance, via the real API. NB: recording a health cost (below) also posts a
    # 300 "veterinary" expense to this same ledger - existing behaviour that the
    # charts must, and do, include.
    for kind, category, amount, when in [
        ("income", "milk_sale", "1000", today), ("expense", "feed", "400", today),
        ("income", "livestock_sale", "500", prev_month_day), ("expense", "veterinary", "150", prev_month_day),
    ]:
        r = await client.post("/api/v1/finance/transactions", headers=headers, json={
            "transaction_type": kind, "category": category, "amount": amount, "transaction_date": when.isoformat(),
        })
        assert r.status_code == 201, r.text

    # herd: 2 cattle + 1 goat, one of the cattle then sold
    farm = (await client.post("/api/v1/farms", json={"name": "F", "county": "Nakuru"}, headers=headers)).json()
    ids = {}
    for number, species in [("C-1", "cattle"), ("C-2", "cattle"), ("G-1", "goat")]:
        r = await client.post("/api/v1/livestock", headers=headers, json={
            "farm_id": farm["id"], "animal_number": number, "species": species, "sex": "female",
            "acquisition_method": "purchased", "acquisition_date": "2026-01-01",
        })
        assert r.status_code == 201, r.text
        ids[number] = r.json()["id"]

    # crops + inventory + health, via the real API
    planting = await client.post("/api/v1/crops", headers=headers, json={
        "farm_id": farm["id"], "planting_number": "P-1", "crop_type": "maize",
        "planting_date": "2026-03-01", "area_size": 2, "area_unit": "acres",
    })
    assert planting.status_code == 201, planting.text
    feed = (await client.post("/api/v1/inventory/items", headers=headers, json={
        "name": "Dairy Meal", "category": "feed", "unit": "kg", "reorder_level": "10"})).json()
    await client.post("/api/v1/inventory/items", headers=headers, json={"name": "Syringes", "category": "supply", "unit": "box", "reorder_level": "1"})
    assert (await client.post(f"/api/v1/inventory/items/{feed['id']}/movements", headers=headers, json={
        "movement_type": "purchase", "quantity": "100", "unit_cost": "20"})).status_code == 201
    health = await client.post(f"/api/v1/livestock/{ids['C-1']}/health", headers=headers, json={
        "record_type": "treatment", "title": "Mastitis", "cost": "300",
        "performed_at": f"{today.isoformat()}T09:00:00Z",
    })
    assert health.status_code == 201, health.text

    # things with no convenient API: write them straight to the database
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        await session.execute(update(Animal).where(Animal.id == uuid.UUID(ids["C-2"])).values(status="sold"))
        for day, liters, rejected in [(today, "10", False), (today - timedelta(days=1), "5", False), (today, "3", True)]:
            session.add(MilkProductionRecord(
                organization_id=org_id, animal_id=uuid.UUID(ids["C-1"]), production_date=day,
                session="evening" if rejected else "morning", quantity_liters=D(liters), rejected=rejected,
            ))
        session.add(HarvestRecord(planting_id=uuid.UUID(planting.json()["id"]), quantity=D("120"), unit="kg", harvested_at=now))
        from app.modules.customers.models import Customer
        customer = Customer(organization_id=org_id, name="Buyer")
        session.add(customer)
        await session.flush()
        paid = Order(organization_id=org_id, customer_id=customer.id, status="paid", total_amount=D("1500"))
        pending = Order(organization_id=org_id, customer_id=customer.id, status="pending", total_amount=D("700"))
        session.add_all([paid, pending])
        await session.flush()
        session.add(Payment(
            organization_id=org_id, order_id=paid.id, provider="mpesa", provider_reference=f"ref-{uuid.uuid4()}",
            amount=D("1500"), status="successful", initiated_at=now, completed_at=now,
        ))
        await session.commit()
    return headers, org_id, today


async def test_tenant_analytics_matches_hand_computed_numbers(client, engine):
    headers, _, today = await _seed_farm(client, engine)
    resp = await client.get("/api/v1/reports/analytics?months=3", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # window: exactly 3 months, oldest first, ending with the current one
    this_month, prev_month = today.strftime("%Y-%m"), _first_of_previous_month(today).strftime("%Y-%m")
    months = [m["month"] for m in data["finance"]["monthly"]]
    assert len(months) == 3 and months[-1] == this_month and months[-2] == prev_month
    assert data["months"] == 3 and data["end_date"] == today.isoformat()

    # finance - includes a zero-filled oldest month
    by_month = {m["month"]: m for m in data["finance"]["monthly"]}
    assert (D(by_month[this_month]["income"]), D(by_month[this_month]["expense"]), D(by_month[this_month]["net"])) == (D("1000"), D("700"), D("300"))
    assert (D(by_month[prev_month]["income"]), D(by_month[prev_month]["expense"])) == (D("500"), D("150"))
    oldest = by_month[months[0]]
    assert (D(oldest["income"]), D(oldest["expense"]), D(oldest["net"])) == (0, 0, 0)
    fin = data["finance"]
    assert (D(fin["total_income"]), D(fin["total_expense"]), D(fin["net"])) == (D("1500"), D("850"), D("650"))
    assert [(c["key"], D(c["amount"])) for c in fin["expense_by_category"]] == [("veterinary", D("450")), ("feed", D("400"))]
    assert [(c["key"], D(c["amount"])) for c in fin["income_by_category"]] == [("milk_sale", D("1000")), ("livestock_sale", D("500"))]

    # sales: only the paid order is revenue; both orders appear in the status split
    sales = data["sales"]
    assert (sales["monthly"][-1]["orders"], D(sales["monthly"][-1]["revenue"])) == (1, D("1500"))
    assert (sales["total_orders"], D(sales["total_revenue"]), D(sales["average_order_value"])) == (1, D("1500"), D("1500"))
    assert {s["key"]: s["count"] for s in sales["orders_by_status"]} == {"paid": 1, "pending": 1}
    assert [(p["key"], D(p["amount"]), p["count"]) for p in sales["payments_by_provider"]] == [("mpesa", D("1500"), 1)]

    # herd: the sold cow is in the status split but not in the active species split
    herd = data["herd"]
    assert (herd["total"], herd["active"]) == (3, 2)
    assert {s["key"]: s["count"] for s in herd["by_species"]} == {"cattle": 1, "goat": 1}
    assert {s["key"]: s["count"] for s in herd["by_status"]}["sold"] == 1

    # dairy: 30 zero-filled days; the rejected 3 L never counts as production
    dairy = data["dairy"]
    assert len(dairy["daily"]) == 30 and dairy["daily"][-1]["date"] == today.isoformat()
    assert D(dairy["daily"][-1]["liters"]) == D("10") and D(dairy["daily"][-2]["liters"]) == D("5")
    assert (D(dairy["total_liters"]), D(dairy["average_per_day"]), D(dairy["rejected_liters"])) == (D("15"), D("0.5"), D("3"))

    # crops
    crops = data["crops"]
    assert (crops["total"], crops["active"]) == (1, 1)
    assert [(c["key"], c["plantings"], D(c["area"])) for c in crops["by_type"]] == [("maize", 1, D("2"))]
    assert [(h["unit"], D(h["quantity"]), h["records"]) for h in crops["harvest_by_unit"]] == [("kg", D("120"), 1)]
    assert crops["harvests_monthly"][-1]["count"] == 1 and len(crops["harvests_monthly"]) == 3

    # inventory: 100 kg x 20 = 2000; the item with no stock/cost adds a count but no value
    inv = data["inventory"]
    assert (inv["total_items"], D(inv["total_value"])) == (2, D("2000"))
    assert {c["key"]: (c["items"], D(c["value"])) for c in inv["by_category"]} == {"feed": (1, D("2000")), "supply": (1, D("0"))}

    # health
    health = data["health"]
    assert (health["total_records"], D(health["total_cost"])) == (1, D("300"))
    assert health["by_type"] == [{"key": "treatment", "count": 1}]
    assert D(health["cost_monthly"][-1]["amount"]) == D("300")


async def test_tenant_analytics_agrees_with_the_existing_dashboard_cards(client, engine):
    headers, _, today = await _seed_farm(client, engine)
    dashboard = (await client.get("/api/v1/reports/dashboard", headers=headers)).json()
    analytics = (await client.get("/api/v1/reports/analytics?months=1", headers=headers)).json()
    # The dashboard uses the server clock, analytics the org's timezone; they only
    # diverge for a few hours around midnight, so compare when they're the same day.
    if date.today() == today:
        assert D(analytics["finance"]["monthly"][-1]["income"]) == D(dashboard["monthly_revenue"])
        assert D(analytics["finance"]["monthly"][-1]["expense"]) == D(dashboard["monthly_expenses"])
    assert D(analytics["inventory"]["total_value"]) == D(dashboard["inventory_value"])
    assert analytics["herd"]["total"] == dashboard["total_animals"]
    assert analytics["herd"]["active"] == dashboard["active_animals"]
    assert analytics["crops"]["active"] == dashboard["active_crop_plantings"]


async def test_tenant_analytics_is_isolated_between_organizations(client, engine):
    await _seed_farm(client, engine)
    other = await _register_org(client, "Empty Farm", "empty-analytics@example.com")
    data = (await client.get("/api/v1/reports/analytics?months=3", headers={"Authorization": f"Bearer {other['access_token']}"})).json()
    assert D(data["finance"]["total_income"]) == 0 and D(data["finance"]["total_expense"]) == 0
    assert data["herd"]["total"] == 0 and data["crops"]["total"] == 0
    assert data["sales"]["total_orders"] == 0 and data["sales"]["payments_by_provider"] == []
    assert data["inventory"]["total_items"] == 0 and data["health"]["total_records"] == 0
    assert D(data["dairy"]["total_liters"]) == 0 and data["crops"]["harvest_by_unit"] == []


async def test_analytics_months_bounds_auth_and_permission(client, engine):
    headers, _, _ = await _seed_farm(client, engine)
    assert (await client.get("/api/v1/reports/analytics?months=24", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/reports/analytics?months=0", headers=headers)).status_code == 422
    assert (await client.get("/api/v1/reports/analytics?months=25", headers=headers)).status_code == 422
    assert len((await client.get("/api/v1/reports/analytics", headers=headers)).json()["finance"]["monthly"]) == 6  # default window
    assert (await client.get("/api/v1/reports/analytics")).status_code == 401

    # a default new team member (Farm Worker) lacks reports.view
    worker = await client.post("/api/v1/users", headers=headers, json={
        "full_name": "Worker", "email": "worker-analytics@example.com", "password": "supersecret123"})
    assert worker.status_code == 201, worker.text
    login = await client.post("/api/v1/auth/login", json={"email": "worker-analytics@example.com", "password": "supersecret123"})
    worker_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await client.get("/api/v1/reports/analytics", headers=worker_headers)).status_code == 403


# --- platform ---------------------------------------------------------------

async def test_platform_analytics_totals_tiers_and_top_tenants(client, engine):
    await _make_platform_admin(engine)
    await _seed_farm(client, engine, "Big Farm", "big-analytics@example.com")
    await _register_org(client, "Small Farm", "small-analytics@example.com")
    token = await _platform_login(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/platform/analytics?months=4", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["months"] == 4 and len(data["signups_monthly"]) == 4
    assert data["totals"]["organizations"] == 2
    assert data["totals"]["animals"] == 2          # active only: C-1 and G-1 (C-2 was sold)
    assert data["totals"]["crop_plantings"] == 1
    assert D(data["totals"]["gmv"]) == D("1500")
    assert D(data["totals"]["mrr_kes"]) == 0       # nobody has an *active* paid subscription

    # both orgs signed up this month; cumulative must end at the org total
    assert data["signups_monthly"][-1]["count"] == 2 and data["signups_monthly"][-1]["cumulative"] == 2
    assert sum(m["count"] for m in data["signups_monthly"]) == 2

    # orgs that never opened billing are counted as Free, so the split sums to the total
    assert sum(t["count"] for t in data["organizations_by_tier"]) == 2
    assert {s["key"]: s["count"] for s in data["organizations_by_status"]} == {"active": 2, "suspended": 0}

    assert [(p["key"], D(p["amount"])) for p in data["tenant_payments_by_provider"]] == [("mpesa", D("1500"))]
    assert D(data["tenant_gmv_monthly"][-1]["amount"]) == D("1500") and data["tenant_gmv_monthly"][-1]["payments"] == 1
    assert {s["key"]: s["count"] for s in data["species_distribution"]} == {"cattle": 1, "goat": 1}

    top = data["top_tenants"]
    assert [t["name"] for t in top] == ["Big Farm", "Small Farm"]   # ranked by GMV
    assert D(top[0]["gmv"]) == D("1500") and top[0]["animals"] == 2 and top[0]["orders"] == 2
    assert top[1]["animals"] == 0 and D(top[1]["gmv"]) == 0


async def test_platform_analytics_viewer_can_read_and_tenants_cannot(client, engine):
    await _make_platform_admin(engine)
    tenant = await _register_org(client, "Some Farm", "some-analytics@example.com")
    headers = {"Authorization": f"Bearer {await _platform_login(client)}"}

    await client.post("/api/v1/platform/admins", json={
        "email": "viewer-an@platform.example.com", "full_name": "Viewer", "password": "viewerpass123", "role": "viewer"}, headers=headers)
    login = await client.post("/api/v1/platform/auth/login", data={"username": "viewer-an@platform.example.com", "password": "viewerpass123"})
    viewer = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await client.get("/api/v1/platform/analytics", headers=viewer)).status_code == 200

    assert (await client.get("/api/v1/platform/analytics")).status_code == 401
    assert (await client.get("/api/v1/platform/analytics", headers={"Authorization": f"Bearer {tenant['access_token']}"})).status_code in (401, 403)
    assert (await client.get("/api/v1/platform/analytics?months=0", headers=headers)).status_code == 422
    assert (await client.get("/api/v1/platform/analytics?months=37", headers=headers)).status_code == 422
    assert len((await client.get("/api/v1/platform/analytics", headers=headers)).json()["signups_monthly"]) == 12  # default


async def test_platform_analytics_on_an_empty_platform(client, engine):
    await _make_platform_admin(engine)
    headers = {"Authorization": f"Bearer {await _platform_login(client)}"}
    data = (await client.get("/api/v1/platform/analytics?months=2", headers=headers)).json()
    assert data["totals"]["organizations"] == 0 and data["top_tenants"] == []
    assert [m["cumulative"] for m in data["signups_monthly"]] == [0, 0]
    assert data["species_distribution"] == [] and data["tenant_payments_by_provider"] == []

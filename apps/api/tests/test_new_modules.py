"""Training, flock/fish groups, fuel logs, product feedback and animal photos."""
import io

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _org(client, email, name="Mixed Farm"):
    reg = await client.post("/api/v1/auth/register", json={"organization_name": name, "full_name": "Owner One", "email": email, "password": "supersecret123"})
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    farm = (await client.post("/api/v1/farms", json={"name": "Segera"}, headers=h)).json()["id"]
    return h, farm


# --------------------------------------------------------------------------- training
async def test_training_enrolment_capacity_billing_attendance_and_certificate(client):
    h, farm = await _org(client, "tr1@example.com")
    course = (await client.post("/api/v1/training/courses", headers=h, json={"title": "Dairy Management", "duration_days": 2, "fee": "5000", "capacity": 2, "trainer": "Dr. Achieng"})).json()
    sess = (await client.post("/api/v1/training/sessions", headers=h, json={"course_id": course["id"], "start_date": "2026-09-01", "farm_id": farm, "venue": "Segera Hall"})).json()
    assert sess["end_date"] == "2026-09-02" and sess["seats_left"] == 2 and sess["fee"] == 5000.0
    jane = (await client.post(f"/api/v1/training/sessions/{sess['id']}/enrolments", headers=h, json={"participant_name": "Jane Mwangi", "phone": "0711000111"})).json()
    assert jane["fee_charged"] == 5000.0 and jane["customer_id"] and jane["seats_left"] == 1
    dup = await client.post(f"/api/v1/training/sessions/{sess['id']}/enrolments", headers=h, json={"participant_name": "Jane Mwangi", "phone": "0711000111"})
    assert dup.status_code == 409
    peter = (await client.post(f"/api/v1/training/sessions/{sess['id']}/enrolments", headers=h, json={"participant_name": "Peter Otieno", "fee_override": "3000"})).json()
    full = await client.post(f"/api/v1/training/sessions/{sess['id']}/enrolments", headers=h, json={"participant_name": "Third Person"})
    assert full.status_code == 409 and "full" in full.json()["detail"]

    st = (await client.get(f"/api/v1/receivables/customers/{jane['customer_id']}/statement", headers=h)).json()
    assert st["balance"] == 5000.0 and st["open_items"][0]["reference_type"] == "training_enrolment"
    await client.post("/api/v1/receivables/payments", headers=h, json={"customer_id": jane["customer_id"], "amount": 2000, "entry_date": "2026-08-20",
        "method": "mpesa", "receipt_ref": "QWE123", "reference_type": "training_enrolment", "reference_id": jane["id"]})
    fin = (await client.get("/api/v1/finance/transactions?category=training_revenue", headers=h)).json()
    assert len(fin) == 1 and fin[0]["activity"] == "training" and fin[0]["farm_id"] == farm

    detail = (await client.get(f"/api/v1/training/sessions/{sess['id']}", headers=h)).json()
    assert detail["fees_charged"] == 8000.0 and detail["collected"] == 2000.0 and detail["outstanding"] == 6000.0
    roster = {r["participant_name"]: r for r in detail["roster"]}
    assert roster["Jane Mwangi"]["paid"] == 2000.0 and roster["Jane Mwangi"]["outstanding"] == 3000.0

    assert (await client.post(f"/api/v1/training/enrolments/{jane['id']}/attendance", headers=h, json={"day": "2026-09-05"})).status_code == 422
    early = await client.post(f"/api/v1/training/enrolments/{jane['id']}/certificate", headers=h, json={})
    assert early.status_code == 409                                  # attendance not recorded
    for d in ("2026-09-01", "2026-09-02"):
        r = (await client.post(f"/api/v1/training/enrolments/{jane['id']}/attendance", headers=h, json={"day": d})).json()
    assert r["status"] == "attended"
    cert = (await client.post(f"/api/v1/training/enrolments/{jane['id']}/certificate", headers=h, json={})).json()
    assert cert["certificate_number"].endswith("-0001") and cert["already_issued"] is False
    assert (await client.post(f"/api/v1/training/enrolments/{jane['id']}/certificate", headers=h, json={})).json()["already_issued"] is True
    pdf = await client.get(f"/api/v1/training/enrolments/{jane['id']}/certificate.pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert (await client.get(f"/api/v1/training/enrolments/{peter['id']}/certificate.pdf", headers=h)).status_code == 409   # none issued

    # cancelling reverses the unpaid charge, flags the refund due on a paid one, and frees the seat
    cj = (await client.patch(f"/api/v1/training/enrolments/{peter['id']}/status", headers=h, json={"status": "cancelled"})).json()
    assert "refund_due" not in cj
    pst = (await client.get(f"/api/v1/receivables/customers/{peter['customer_id']}/statement", headers=h)).json()
    assert pst["balance"] == 0.0 and pst["written_off"] == 3000.0
    ok = await client.post(f"/api/v1/training/sessions/{sess['id']}/enrolments", headers=h, json={"participant_name": "Third Person"})
    assert ok.status_code == 201
    summ = (await client.get("/api/v1/training/summary?start_date=2026-01-01&end_date=2026-12-31", headers=h)).json()
    assert summ["sessions"] == 1 and summ["participants"] == 2 and summ["certificates_issued"] == 1 and summ["fees_collected"] == 2000.0


# ---------------------------------------------------------------------------- groups
async def test_flock_records_counts_sales_ledger_and_performance(client):
    h, farm = await _org(client, "gr1@example.com")
    cust = (await client.post("/api/v1/customers", json={"name": "Market Trader"}, headers=h)).json()["id"]
    g = (await client.post("/api/v1/groups", headers=h, json={"code": "L-01", "name": "Layers House 1", "species": "poultry", "purpose": "layers",
         "start_date": "2026-03-01", "initial_count": 500, "acquisition_cost": "150000", "farm_id": farm})).json()
    assert (await client.post("/api/v1/groups", headers=h, json={"code": "L-01", "name": "dup", "species": "poultry", "start_date": "2026-03-01", "initial_count": 1})).status_code == 409
    rec = lambda **kw: client.post(f"/api/v1/groups/{g['id']}/records", headers=h, json=kw)
    assert (await rec(record_date="2026-03-05", record_type="mortality", quantity=5)).json()["current_count"] == 495
    assert (await rec(record_date="2026-03-06", record_type="mortality", quantity=600)).status_code == 422
    assert (await rec(record_date="2026-03-06", record_type="mortality", quantity=2.5)).status_code == 422
    assert (await rec(record_date="2026-02-01", record_type="feed", quantity=10)).status_code == 422          # before the flock started
    for d, n in (("2026-04-01", 380), ("2026-04-02", 390), ("2026-04-03", 400)):
        await rec(record_date=d, record_type="production", quantity=n, unit="eggs")
    await rec(record_date="2026-04-03", record_type="feed", quantity=60, unit="kg", value=4800)
    await rec(record_date="2026-04-03", record_type="weight_sample", quantity=20, avg_weight_kg=1.8)
    cash = (await rec(record_date="2026-04-04", record_type="sale", quantity=1000, unit="eggs", product="eggs", value=15000)).json()
    assert cash["ledger"] == "income_posted"
    credit = (await rec(record_date="2026-04-05", record_type="sale", quantity=95, unit="head", product="live", value=95000, customer_id=cust)).json()
    assert credit["ledger"] == "charged_to_customer_account" and credit["current_count"] == 400
    fin = (await client.get("/api/v1/finance/transactions?category=egg_sale", headers=h)).json()
    assert len(fin) == 1 and fin[0]["activity"] == "poultry" and float(fin[0]["amount"]) == 15000.0
    assert (await client.get(f"/api/v1/receivables/customers/{cust}/statement", headers=h)).json()["balance"] == 95000.0
    p = (await client.get(f"/api/v1/groups/{g['id']}/performance?as_of=2026-04-10", headers=h)).json()
    assert p["mortality"]["died"] == 5 and p["mortality"]["mortality_pct"] == 1.0
    assert p["production"]["eggs"] == 1170.0 and p["feed_kg"] == 60.0
    eg = p["egg_production"]; assert eg["recording_days"] == 3 and eg["hen_day_pct"] == pytest.approx(100 * 1170 / (((500 + 400) / 2) * 3), abs=0.1)
    assert p["economics"]["revenue"] == 110000.0 and p["economics"]["margin"] == 110000 - 150000 - 4800
    closed = (await client.post(f"/api/v1/groups/{g['id']}/close", headers=h, json={"closed_on": "2026-05-01"})).json()
    assert closed["status"] == "closed"
    assert (await rec(record_date="2026-05-02", record_type="feed", quantity=1)).status_code == 409
    assert (await client.post(f"/api/v1/groups/{g['id']}/close", headers=h, json={"closed_on": "2026-05-02"})).status_code == 409
    assert len((await client.get("/api/v1/groups?state=active", headers=h)).json()) == 0


# ------------------------------------------------------------------------------ fuel
async def test_fuel_logs_post_expense_with_dimensions_and_report_consumption(client):
    h, farm = await _org(client, "fu1@example.com")
    a = (await client.post("/api/v1/assets", headers=h, json={"name": "MF 375", "asset_type": "tractor"})).json()
    r1 = (await client.post("/api/v1/fuel", headers=h, json={"asset_id": a["id"], "log_date": "2026-05-01", "litres": 50, "cost": 8500, "meter_reading": 1000, "activity": "crops", "farm_id": farm})).json()
    await client.post("/api/v1/fuel", headers=h, json={"asset_id": a["id"], "log_date": "2026-05-10", "litres": 40, "cost": 6800, "meter_reading": 1020, "activity": "crops", "farm_id": farm})
    assert r1["cost_per_litre"] == 170.0
    fin = (await client.get("/api/v1/finance/transactions?category=fuel", headers=h)).json()
    assert len(fin) == 2 and all(t["activity"] == "crops" and t["farm_id"] == farm for t in fin)
    nopost = (await client.post("/api/v1/fuel", headers=h, json={"asset_id": a["id"], "log_date": "2026-05-12", "litres": 5, "cost": 850, "post_to_finance": False}))
    assert nopost.status_code == 201
    assert len((await client.get("/api/v1/finance/transactions?category=fuel", headers=h)).json()) == 2
    s = (await client.get("/api/v1/fuel/summary?start_date=2026-05-01&end_date=2026-05-31", headers=h)).json()
    assert s["total_litres"] == 95.0 and s["total_cost"] == 16150.0 and s["cost_by_activity"]["crops"] == 15300.0
    assert s["by_asset"][0]["litres_per_meter_unit"] == 2.0          # 40 L after the first reading over 20 hours
    assert (await client.post("/api/v1/fuel", headers=h, json={"asset_id": a["id"], "log_date": "2026-05-12", "litres": 0, "cost": 1})).status_code == 422
    h2, _ = await _org(client, "fu2@example.com", "Other")
    assert (await client.post("/api/v1/fuel", headers=h2, json={"asset_id": a["id"], "log_date": "2026-05-12", "litres": 5})).status_code == 404


# -------------------------------------------------------------------------- feedback
async def test_product_feedback_is_moderated_rate_limited_and_isolated(client, engine):
    h, farm = await _org(client, "fb1@example.com", "Review Farm")
    animal = (await client.post("/api/v1/livestock", headers=h, json={"farm_id": farm, "animal_number": "REV-1", "species": "cattle", "sex": "female",
              "acquisition_date": "2024-01-01", "acquisition_method": "purchased", "acquisition_cost": "40000"})).json()
    await client.post(f"/api/v1/livestock/{animal['id']}/status", headers=h, json={"status": "for_sale"})
    lst = (await client.post("/api/v1/listings", headers=h, json={"animal_id": animal["id"], "title": "Fine Heifer", "pricing_type": "fixed", "price": "80000"})).json()
    async with engine.connect() as c:
        org_slug = (await c.execute(text("SELECT slug FROM organizations WHERE name = 'Review Farm'"))).scalar_one()
    url = f"/api/v1/public/{org_slug}/listings/{lst['slug']}/feedback"
    sub = await client.post(url, json={"customer_name": "Happy Buyer", "rating": 5, "comment": "Healthy animal, great service"})
    assert sub.status_code == 201 and sub.json()["status"] == "pending"
    assert (await client.post(url, json={"customer_name": "X", "rating": 9})).status_code == 422
    assert (await client.get(url)).json()["count"] == 0                      # not public until approved
    pending = (await client.get("/api/v1/feedback?status=pending", headers=h)).json()
    assert len(pending) == 1
    assert (await client.patch(f"/api/v1/feedback/{pending[0]['id']}", headers=h, json={"status": "approved"})).json()["status"] == "approved"
    pub = (await client.get(url)).json()
    assert pub["count"] == 1 and pub["average_rating"] == 5.0 and pub["reviews"][0]["customer_name"] == "Happy Buyer"
    assert (await client.get("/api/v1/feedback/summary", headers=h)).json()["listings"][0]["reviews"] == 1
    assert (await client.post(f"/api/v1/public/{org_slug}/listings/nope/feedback", json={"customer_name": "Zed Zed", "rating": 3})).status_code == 404
    h2, _ = await _org(client, "fb2@example.com", "Rival")
    assert (await client.get("/api/v1/feedback", headers=h2)).json() == []
    assert (await client.patch(f"/api/v1/feedback/{pending[0]['id']}", headers=h2, json={"status": "rejected"})).status_code == 404
    for i in range(25):
        await client.post(url, json={"customer_name": f"Spammer {i}", "rating": 1})
    assert (await client.post(url, json={"customer_name": "One More", "rating": 1})).status_code == 429


# ----------------------------------------------------------------------- animal photo
async def test_animal_photo_is_validated_resized_and_tenant_scoped(client):
    from PIL import Image
    h, farm = await _org(client, "ph1@example.com", "Photo Farm")
    a = (await client.post("/api/v1/livestock", headers=h, json={"farm_id": farm, "animal_number": "PH-1", "species": "cattle", "sex": "male",
         "acquisition_date": "2024-01-01", "acquisition_method": "purchased"})).json()
    buf = io.BytesIO(); Image.new("RGB", (3000, 2000), (120, 80, 40)).save(buf, "JPEG")
    up = await client.put(f"/api/v1/livestock/{a['id']}/photo", headers=h, files={"file": ("cow.jpg", buf.getvalue(), "image/jpeg")})
    assert up.status_code == 200 and max(up.json()["width"], up.json()["height"]) == 900
    got = await client.get(f"/api/v1/livestock/{a['id']}/photo", headers=h)
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg" and Image.open(io.BytesIO(got.content)).width == 900
    bad = await client.put(f"/api/v1/livestock/{a['id']}/photo", headers=h, files={"file": ("x.jpg", b"definitely not an image", "image/jpeg")})
    assert bad.status_code == 422
    h2, _ = await _org(client, "ph2@example.com", "Other Photo Farm")
    assert (await client.get(f"/api/v1/livestock/{a['id']}/photo", headers=h2)).status_code == 404
    assert (await client.delete(f"/api/v1/livestock/{a['id']}/photo", headers=h)).status_code == 204
    assert (await client.get(f"/api/v1/livestock/{a['id']}/photo", headers=h)).status_code == 404

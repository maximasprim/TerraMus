import hashlib
import hmac
import json

import pytest

from app.core.config import get_settings

pytestmark = pytest.mark.asyncio
settings = get_settings()


def _sign(body: bytes) -> str:
    return hmac.new(settings.MOCK_PAYMENT_SECRET.encode(), body, hashlib.sha256).hexdigest()


async def _setup_order(client, org_name: str, email: str):
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
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "COW-PAY",
        "species": "cattle", "sex": "female", "acquisition_date": "2024-01-01",
        "acquisition_method": "purchased", "acquisition_cost": "40000",
    })
    animal_id = animal.json()["id"]
    await client.post(f"/api/v1/livestock/{animal_id}/status", headers=headers, json={"status": "for_sale"})

    customer = await client.post("/api/v1/customers", headers=headers, json={"name": "Alice"})
    order = await client.post("/api/v1/orders", headers=headers, json={
        "customer_id": customer.json()["id"], "items": [{"animal_id": animal_id, "price": "80000"}],
    })
    order_id = order.json()["id"]
    await client.post(f"/api/v1/orders/{order_id}/status", headers=headers, json={"status": "payment_pending"})
    return headers, animal_id, order_id


async def test_acquisition_auto_creates_expense_transaction(client):
    headers, animal_id, _ = await _setup_order(client, "Pay Farm A", "pay1@example.com")
    txns = (await client.get("/api/v1/finance/transactions", headers=headers)).json()
    acquisition = [t for t in txns if t["reference_id"] == animal_id]
    assert len(acquisition) == 1
    assert acquisition[0]["transaction_type"] == "expense"
    assert acquisition[0]["category"] == "livestock_acquisition"
    assert acquisition[0]["amount"] == "40000.00"


async def test_webhook_requires_valid_signature(client):
    headers, _, order_id = await _setup_order(client, "Pay Farm B", "pay2@example.com")
    payment = await client.post("/api/v1/payments/mock", headers=headers, json={
        "order_id": order_id, "phone_or_token": "254700000000",
    })
    ref = payment.json()["provider_reference"]

    body = json.dumps({"event_id": "evt-x", "provider_reference": ref, "status": "successful"}).encode()
    unsigned = await client.post("/api/v1/payments/webhooks/mock", content=body,
                                  headers={"Content-Type": "application/json"})
    assert unsigned.status_code == 401

    signed = await client.post("/api/v1/payments/webhooks/mock", content=body, headers={
        "Content-Type": "application/json", "X-Mock-Signature": _sign(body),
    })
    assert signed.status_code == 200


async def test_webhook_idempotent_replay_not_reprocessed(client):
    headers, animal_id, order_id = await _setup_order(client, "Pay Farm C", "pay3@example.com")
    payment = await client.post("/api/v1/payments/mock", headers=headers, json={
        "order_id": order_id, "phone_or_token": "254700000000",
    })
    ref = payment.json()["provider_reference"]
    body = json.dumps({"event_id": "evt-replay", "provider_reference": ref, "status": "successful"}).encode()
    headers_sig = {"Content-Type": "application/json", "X-Mock-Signature": _sign(body)}

    first = await client.post("/api/v1/payments/webhooks/mock", content=body, headers=headers_sig)
    assert first.json()["status"] == "processed"

    second = await client.post("/api/v1/payments/webhooks/mock", content=body, headers=headers_sig)
    assert second.json()["status"] == "already_processed"


async def test_successful_payment_marks_order_paid_animal_sold_and_generates_invoice(client):
    headers, animal_id, order_id = await _setup_order(client, "Pay Farm D", "pay4@example.com")
    payment = await client.post("/api/v1/payments/mock", headers=headers, json={
        "order_id": order_id, "phone_or_token": "254700000000",
    })
    ref = payment.json()["provider_reference"]
    body = json.dumps({"event_id": "evt-success", "provider_reference": ref, "status": "successful"}).encode()
    await client.post("/api/v1/payments/webhooks/mock", content=body, headers={
        "Content-Type": "application/json", "X-Mock-Signature": _sign(body),
    })

    order = (await client.get(f"/api/v1/orders/{order_id}", headers=headers)).json()
    assert order["status"] == "paid"

    animal = (await client.get(f"/api/v1/livestock/{animal_id}", headers=headers)).json()
    assert animal["status"] == "sold"

    invoice = await client.get(f"/api/v1/finance/orders/{order_id}/invoice", headers=headers)
    assert invoice.status_code == 200
    assert invoice.json()["total"] == "80000.00"
    assert invoice.json()["invoice_number"].startswith("INV-")

    # Spec §59 "Generate downloadable PDF" (this session) - requires the
    # reportlab dependency added to requirements.txt this session; see
    # docs/architecture.md for why this specific assertion is unverified in
    # the sandbox that wrote it.
    invoice_pdf = await client.get(f"/api/v1/finance/orders/{order_id}/invoice.pdf", headers=headers)
    assert invoice_pdf.status_code == 200
    assert invoice_pdf.headers["content-type"] == "application/pdf"
    assert invoice_pdf.content[:4] == b"%PDF"

    txns = (await client.get("/api/v1/finance/transactions", headers=headers)).json()
    income = [t for t in txns if t["transaction_type"] == "income"]
    assert len(income) == 1
    assert income[0]["amount"] == "80000.00"


async def test_failed_payment_does_not_mark_order_paid(client):
    headers, animal_id, order_id = await _setup_order(client, "Pay Farm E", "pay5@example.com")
    payment = await client.post("/api/v1/payments/mock", headers=headers, json={
        "order_id": order_id, "phone_or_token": "254700000000",
    })
    ref = payment.json()["provider_reference"]
    body = json.dumps({"event_id": "evt-fail", "provider_reference": ref, "status": "failed"}).encode()
    await client.post("/api/v1/payments/webhooks/mock", content=body, headers={
        "Content-Type": "application/json", "X-Mock-Signature": _sign(body),
    })

    order = (await client.get(f"/api/v1/orders/{order_id}", headers=headers)).json()
    assert order["status"] == "payment_pending"  # unchanged


async def test_payments_tenant_isolation(client):
    headers_a, _, order_id_a = await _setup_order(client, "Pay Iso A", "pay6a@example.com")
    reg_b = await client.post("/api/v1/auth/register", json={
        "organization_name": "Pay Iso B", "full_name": "Owner",
        "email": "pay6b@example.com", "password": "supersecret123",
    })
    headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}

    payment = await client.post("/api/v1/payments/mock", headers=headers_a, json={
        "order_id": order_id_a, "phone_or_token": "254700000000",
    })
    payment_id = payment.json()["id"]

    leak = await client.get(f"/api/v1/payments/{payment_id}", headers=headers_b)
    assert leak.status_code == 404

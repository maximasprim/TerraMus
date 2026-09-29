import pytest
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


async def _register(client, org_name: str, email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org_name, "full_name": "Owner",
        "email": email, "password": "supersecret123",
    })
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def _get_reset_token_from_db(email: str) -> str | None:
    """Tests can't read the raw token from the API response (spec's own
    security requirement: it only ever goes out via email) - so this reads
    the DB directly the same way a real user would read their inbox, by
    parsing the link out of the EmailOutbox body."""
    from app.core import database as db_module
    async with db_module.AsyncSessionLocal() as db:
        from app.modules.notifications.models import EmailOutbox
        result = await db.execute(
            select(EmailOutbox).where(EmailOutbox.to_email == email).order_by(EmailOutbox.sent_at.desc())
        )
        outbox = result.scalars().first()
        if not outbox:
            return None
        marker = "token="
        start = outbox.body_text.index(marker) + len(marker)
        end = outbox.body_text.index("\n", start)
        return outbox.body_text[start:end]


async def test_password_reset_full_flow(client):
    await _register(client, "Reset Farm A", "reset1@example.com")

    request = await client.post("/api/v1/auth/password-reset/request", json={"email": "reset1@example.com"})
    assert request.status_code == 200

    token = await _get_reset_token_from_db("reset1@example.com")
    assert token is not None

    confirm = await client.post("/api/v1/auth/password-reset/confirm", json={
        "token": token, "new_password": "brandnewpassword456",
    })
    assert confirm.status_code == 200

    old_login = await client.post("/api/v1/auth/login", json={
        "email": "reset1@example.com", "password": "supersecret123",
    })
    assert old_login.status_code == 401

    new_login = await client.post("/api/v1/auth/login", json={
        "email": "reset1@example.com", "password": "brandnewpassword456",
    })
    assert new_login.status_code == 200


async def test_password_reset_token_is_single_use(client):
    await _register(client, "Reset Farm B", "reset2@example.com")
    await client.post("/api/v1/auth/password-reset/request", json={"email": "reset2@example.com"})
    token = await _get_reset_token_from_db("reset2@example.com")

    first = await client.post("/api/v1/auth/password-reset/confirm", json={
        "token": token, "new_password": "firstnewpassword456",
    })
    assert first.status_code == 200

    second = await client.post("/api/v1/auth/password-reset/confirm", json={
        "token": token, "new_password": "secondnewpassword789",
    })
    assert second.status_code == 400


async def test_password_reset_invalid_token_rejected(client):
    resp = await client.post("/api/v1/auth/password-reset/confirm", json={
        "token": "not-a-real-token", "new_password": "somenewpassword456",
    })
    assert resp.status_code == 400


async def test_password_reset_unknown_email_does_not_leak_existence(client):
    known = await client.post("/api/v1/auth/password-reset/request", json={"email": "reset3@example.com"})
    unknown = await client.post("/api/v1/auth/password-reset/request", json={"email": "definitely-not-registered@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


async def test_payment_succeeded_sends_customer_confirmation_email(client):
    headers = await _register(client, "Email Farm A", "email1@example.com")
    farm = await client.post("/api/v1/farms", json={"name": "Main Farm"}, headers=headers)
    farm_id = farm.json()["id"]
    branch = await client.post(f"/api/v1/farms/{farm_id}/branches", json={"name": "B"}, headers=headers)
    branch_id = branch.json()["id"]
    loc = await client.post(
        f"/api/v1/farms/{farm_id}/branches/{branch_id}/locations",
        json={"name": "L", "location_type": "paddock"}, headers=headers,
    )
    loc_id = loc.json()["id"]
    animal = await client.post("/api/v1/livestock", headers=headers, json={
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "EMAIL-COW",
        "species": "cattle", "sex": "female", "acquisition_date": "2024-01-01",
        "acquisition_method": "purchased", "acquisition_cost": "40000",
    })
    animal_id = animal.json()["id"]
    await client.post(f"/api/v1/livestock/{animal_id}/status", headers=headers, json={"status": "for_sale"})

    customer = await client.post("/api/v1/customers", headers=headers, json={
        "name": "Email Buyer", "email": "buyer@email1farm.example.com",
    })
    order = await client.post("/api/v1/orders", headers=headers, json={
        "customer_id": customer.json()["id"], "items": [{"animal_id": animal_id, "price": "10000"}],
    })
    order_id = order.json()["id"]
    await client.post(f"/api/v1/orders/{order_id}/status", headers=headers, json={"status": "payment_pending"})

    import hashlib
    import hmac
    import json as json_module
    from app.core.config import get_settings
    settings = get_settings()

    payment = await client.post("/api/v1/payments/mock", headers=headers, json={
        "order_id": order_id, "phone_or_token": "254700000000",
    })
    ref = payment.json()["provider_reference"]
    body = json_module.dumps({"event_id": "evt-email-test", "provider_reference": ref, "status": "successful"}).encode()
    signature = hmac.new(settings.MOCK_PAYMENT_SECRET.encode(), body, hashlib.sha256).hexdigest()
    await client.post("/api/v1/payments/webhooks/mock", content=body, headers={
        "Content-Type": "application/json", "X-Mock-Signature": signature,
    })

    outbox = await client.get("/api/v1/notifications/email-outbox", headers=headers)
    assert outbox.status_code == 200
    emails = [e for e in outbox.json() if e["to_email"] == "buyer@email1farm.example.com"]
    assert len(emails) == 1
    assert "confirmed" in emails[0]["subject"].lower()
    assert emails[0]["accepted"] is True


async def test_email_outbox_tenant_isolation(client):
    headers_a = await _register(client, "Email Farm B-A", "email2a@example.com")
    headers_b = await _register(client, "Email Farm B-B", "email2b@example.com")

    await client.post("/api/v1/auth/password-reset/request", json={"email": "email2a@example.com"})

    outbox_b = await client.get("/api/v1/notifications/email-outbox", headers=headers_b)
    assert all(e["to_email"] != "email2a@example.com" for e in outbox_b.json())

    outbox_a = await client.get("/api/v1/notifications/email-outbox", headers=headers_a)
    assert any(e["to_email"] == "email2a@example.com" for e in outbox_a.json())

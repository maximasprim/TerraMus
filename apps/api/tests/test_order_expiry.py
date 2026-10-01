"""Abandoned guest orders must not hold inventory forever."""
import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.modules.commerce.expiry import expire_stale_guest_orders
from test_guest_checkout import _setup_listing

pytestmark = pytest.mark.asyncio
settings = get_settings()


def _sign(body: bytes) -> str:
    return hmac.new(settings.MOCK_PAYMENT_SECRET.encode(), body, hashlib.sha256).hexdigest()


async def _place_guest_order(client, org_slug: str, slug: str, email: str) -> str:
    resp = await client.post(f"/api/v1/public/{org_slug}/orders", json={
        "customer_name": "Jane Guest", "customer_email": email, "items": [{"listing_slug": slug}],
    })
    assert resp.status_code == 201
    return resp.json()["order_id"]


async def _age(engine, order_id: str, *, created="3 hours", updated=None) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(f"UPDATE orders SET created_at = now() - interval '{created}', "
                 f"updated_at = now() - interval '{updated or created}' WHERE id = :id"),
            {"id": uuid.UUID(order_id)},
        )


async def _run_expiry(engine) -> int:
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        return await expire_stale_guest_orders(db)


async def _order_status(client, org_slug: str, order_id: str, email: str) -> str:
    return (await client.get(f"/api/v1/public/{org_slug}/orders/{order_id}", params={"email": email})).json()["status"]


async def test_stale_pending_guest_order_is_cancelled_and_animal_returns_to_the_store(client, engine):
    headers, org_slug, animal_id, slug = await _setup_listing(client, "Expiry Farm A", "exp1@example.com")
    order_id = await _place_guest_order(client, org_slug, slug, "jane@exp1.example.com")

    # the hold is real: animal reserved, listing gone from the storefront
    assert (await client.get(f"/api/v1/livestock/{animal_id}", headers=headers)).json()["status"] == "reserved"
    assert (await client.get(f"/api/v1/public/{org_slug}/listings")).json() == []

    await _age(engine, order_id)
    assert await _run_expiry(engine) == 1

    assert await _order_status(client, org_slug, order_id, "jane@exp1.example.com") == "cancelled"
    assert (await client.get(f"/api/v1/livestock/{animal_id}", headers=headers)).json()["status"] == "for_sale"
    relisted = (await client.get(f"/api/v1/public/{org_slug}/listings")).json()
    assert [l["slug"] for l in relisted] == [slug]  # back on sale without staff intervention


async def test_recent_orders_are_left_alone(client, engine):
    _, org_slug, _, slug = await _setup_listing(client, "Expiry Farm B", "exp2@example.com")
    order_id = await _place_guest_order(client, org_slug, slug, "jane@exp2.example.com")
    assert await _run_expiry(engine) == 0
    assert await _order_status(client, org_slug, order_id, "jane@exp2.example.com") == "pending"


async def test_staff_created_orders_are_never_auto_expired(client, engine):
    _, org_slug, _, slug = await _setup_listing(client, "Expiry Farm C", "exp3@example.com")
    order_id = await _place_guest_order(client, org_slug, slug, "jane@exp3.example.com")
    async with engine.begin() as conn:  # make it look staff-created
        await conn.execute(text("UPDATE orders SET created_by = :u WHERE id = :id"), {"u": uuid.uuid4(), "id": uuid.UUID(order_id)})
    await _age(engine, order_id)
    assert await _run_expiry(engine) == 0
    assert await _order_status(client, org_slug, order_id, "jane@exp3.example.com") == "pending"


async def test_payment_pending_order_expires_only_after_the_longer_window(client, engine):
    _, org_slug, _, slug = await _setup_listing(client, "Expiry Farm D", "exp4@example.com")
    email = "jane@exp4.example.com"
    order_id = await _place_guest_order(client, org_slug, slug, email)
    pay = await client.post(f"/api/v1/public/{org_slug}/orders/{order_id}/pay/mock", json={"phone_or_token": "x", "email": email})
    assert pay.status_code == 201
    assert await _order_status(client, org_slug, order_id, email) == "payment_pending"

    await _age(engine, order_id, created="5 hours", updated="5 hours")  # past the pending TTL, inside the 24h payment window
    assert await _run_expiry(engine) == 0
    assert await _order_status(client, org_slug, order_id, email) == "payment_pending"

    await _age(engine, order_id, created="26 hours", updated="25 hours")
    assert await _run_expiry(engine) == 1
    assert await _order_status(client, org_slug, order_id, email) == "cancelled"


async def test_paid_orders_are_never_expired(client, engine):
    _, org_slug, animal_id, slug = await _setup_listing(client, "Expiry Farm E", "exp5@example.com")
    email = "jane@exp5.example.com"
    order_id = await _place_guest_order(client, org_slug, slug, email)
    pay = await client.post(f"/api/v1/public/{org_slug}/orders/{order_id}/pay/mock", json={"phone_or_token": "x", "email": email})
    body = json.dumps({"provider_reference": pay.json()["provider_reference"], "event_id": "evt-exp5", "status": "successful"}).encode()
    hook = await client.post("/api/v1/payments/webhooks/mock", content=body, headers={"x-mock-signature": _sign(body)})
    assert hook.status_code == 200
    assert await _order_status(client, org_slug, order_id, email) == "paid"

    await _age(engine, order_id, created="72 hours")
    assert await _run_expiry(engine) == 0
    assert await _order_status(client, org_slug, order_id, email) == "paid"


async def test_ttl_of_zero_disables_the_rule(client, engine, monkeypatch):
    _, org_slug, _, slug = await _setup_listing(client, "Expiry Farm F", "exp6@example.com")
    order_id = await _place_guest_order(client, org_slug, slug, "jane@exp6.example.com")
    await _age(engine, order_id)
    monkeypatch.setattr(settings, "GUEST_ORDER_TTL_MINUTES", 0)
    monkeypatch.setattr(settings, "PAYMENT_PENDING_TTL_HOURS", 0)
    assert await _run_expiry(engine) == 0
    assert await _order_status(client, org_slug, order_id, "jane@exp6.example.com") == "pending"

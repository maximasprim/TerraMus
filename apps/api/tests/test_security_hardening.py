"""Guest-checkout rate limiting, trusted-proxy client IPs, and the mock
payment provider being unavailable in production."""
import hashlib
import hmac
import json

import pytest

from app.core.config import get_settings
from test_guest_checkout import _setup_listing

pytestmark = pytest.mark.asyncio
settings = get_settings()

ORDER_URL = "/api/v1/public/some-farm/orders"
ORDER_BODY = {"customer_name": "Bot", "customer_email": "bot@example.com", "items": [{"listing_slug": "nope"}]}
STRONG_SECRET = "s3cure-" + "x" * 40


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ------------------------------------------------------------- rate limiting --

async def test_guest_order_endpoint_is_rate_limited(client):
    codes = [(await client.post(ORDER_URL, json=ORDER_BODY)).status_code for _ in range(14)]
    assert 429 not in codes[:12]          # generous for real shoppers
    assert codes[12] == 429               # ...but a bot is cut off


async def test_forwarded_header_is_ignored_when_no_proxy_is_trusted(client):
    # default TRUSTED_PROXY_COUNT == 0: spoofing X-Forwarded-For must not buy a fresh bucket
    for i in range(12):
        await client.post(ORDER_URL, json=ORDER_BODY, headers={"X-Forwarded-For": f"10.0.0.{i}"})
    blocked = await client.post(ORDER_URL, json=ORDER_BODY, headers={"X-Forwarded-For": "203.0.113.99"})
    assert blocked.status_code == 429


async def test_buckets_follow_the_real_client_ip_behind_a_trusted_proxy(client, monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 1)

    async def hit(xff: str) -> int:
        return (await client.post(ORDER_URL, json=ORDER_BODY, headers={"X-Forwarded-For": xff})).status_code

    for i in range(12):
        assert await hit(f"spoof-{i}, 1.1.1.1") != 429
    assert await hit("another-spoof, 1.1.1.1") == 429   # same real client: the spoofable left part is ignored
    assert await hit("spoof, 2.2.2.2") != 429           # a different real client is unaffected


# ------------------------------------------------------ mock payment provider --

async def _guest_order(client, org: str, email: str):
    _, org_slug, _, slug = await _setup_listing(client, org, email)
    guest_email = f"guest-{email}"
    order = await client.post(f"/api/v1/public/{org_slug}/orders", json={
        "customer_name": "Jane", "customer_email": guest_email, "items": [{"listing_slug": slug}],
    })
    return org_slug, order.json()["order_id"], guest_email


async def _pay_mock(client, org_slug, order_id, email):
    return await client.post(f"/api/v1/public/{org_slug}/orders/{order_id}/pay/mock", json={"phone_or_token": "x", "email": email})


async def test_mock_provider_still_works_in_development(client):
    org_slug, order_id, email = await _guest_order(client, "Sec Farm A", "sec1@example.com")
    assert (await _pay_mock(client, org_slug, order_id, email)).status_code == 201


async def test_forged_paid_webhook_is_impossible_in_production_with_the_published_default_secret(client, monkeypatch):
    org_slug, order_id, email = await _guest_order(client, "Sec Farm B", "sec2@example.com")
    monkeypatch.setattr(settings, "ENV", "production")

    # step 1 of the old attack chain: anonymous caller obtains a provider_reference
    assert (await _pay_mock(client, org_slug, order_id, email)).status_code == 404

    # step 2: signing a fake "successful" webhook with the secret published in the repo
    body = json.dumps({"provider_reference": "MOCK-forged", "event_id": "e1", "status": "successful"}).encode()
    forged = await client.post(
        "/api/v1/payments/webhooks/mock", content=body,
        headers={"x-mock-signature": _sign(body, "mock-payment-secret-change-me")},
    )
    assert forged.status_code == 404


async def test_mock_stays_off_in_production_even_if_allowed_with_a_placeholder_secret(client, monkeypatch):
    org_slug, order_id, email = await _guest_order(client, "Sec Farm C", "sec3@example.com")
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENTS", True)  # secret is still the published default
    assert (await _pay_mock(client, org_slug, order_id, email)).status_code == 404


async def test_mock_can_be_deliberately_enabled_in_production_with_a_strong_secret(client, monkeypatch):
    org_slug, order_id, email = await _guest_order(client, "Sec Farm D", "sec4@example.com")
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENTS", True)
    monkeypatch.setattr(settings, "MOCK_PAYMENT_SECRET", STRONG_SECRET)

    pay = await _pay_mock(client, org_slug, order_id, email)
    assert pay.status_code == 201
    body = json.dumps({"provider_reference": pay.json()["provider_reference"], "event_id": "e2", "status": "successful"}).encode()
    ok = await client.post("/api/v1/payments/webhooks/mock", content=body, headers={"x-mock-signature": _sign(body, STRONG_SECRET)})
    assert ok.status_code == 200


async def test_explicit_disable_wins_even_in_development(client, monkeypatch):
    org_slug, order_id, email = await _guest_order(client, "Sec Farm E", "sec5@example.com")
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENTS", False)
    assert (await _pay_mock(client, org_slug, order_id, email)).status_code == 404

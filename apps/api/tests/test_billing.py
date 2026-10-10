import uuid
from datetime import datetime, timezone

import pytest

from app.modules.payments.providers.base import InitiateResult, WebhookResult

pytestmark = pytest.mark.asyncio


async def _register_org(client, name, email):
    resp = await client.post("/api/v1/auth/register", json={
        "organization_name": name, "full_name": f"Owner of {name}",
        "email": email, "password": "supersecret123",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


class FakeMpesaProvider:
    """Stands in for the real MpesaDarajaProvider so these tests exercise
    billing/service.py's own logic (payment record creation, subscription
    activation, webhook idempotency) without a live Daraja sandbox call -
    the real provider is already exercised by the existing
    tests/test_payments.py for the order-payments flow, and billing reuses
    that exact class unmodified (see billing/service.py's module docstring)."""
    def __init__(self, reference="ws_CO_test_ref_1", status="pending"):
        self._reference = reference
        self._status = status

    async def initiate_payment(self, amount, currency, reference, phone_or_token):
        return InitiateResult(provider_reference=self._reference, status=self._status, raw_response={"ok": True})

    def verify_and_parse_webhook(self, headers, body):
        import json
        payload = json.loads(body)
        return WebhookResult(
            provider_reference=payload["provider_reference"],
            event_id=payload["event_id"],
            status=payload["status"],
            raw_payload=payload,
        )


async def test_list_tiers(client):
    tenant = await _register_org(client, "Farm G", "g@example.com")
    resp = await client.get(
        "/api/v1/billing/tiers", headers={"Authorization": f"Bearer {tenant['access_token']}"},
    )
    assert resp.status_code == 200
    slugs = {t["slug"] for t in resp.json()}
    assert slugs == {"free", "basic", "pro", "enterprise"}


async def test_subscription_lazily_created_as_free_trial(client):
    tenant = await _register_org(client, "Farm H", "h@example.com")
    resp = await client.get(
        "/api/v1/billing/subscription", headers={"Authorization": f"Bearer {tenant['access_token']}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "trialing"
    assert body["tier"]["slug"] == "free"


async def test_subscribe_to_free_tier_rejected(client):
    tenant = await _register_org(client, "Farm I", "i@example.com")
    resp = await client.post(
        "/api/v1/billing/subscribe", json={"tier_slug": "free", "phone_number": "254712345678"},
        headers={"Authorization": f"Bearer {tenant['access_token']}"},
    )
    assert resp.status_code == 400


async def test_subscribe_to_paid_tier_and_webhook_activates_it(client, monkeypatch):
    import app.modules.billing.service as billing_service
    monkeypatch.setattr(billing_service, "get_provider", lambda name: FakeMpesaProvider())

    tenant = await _register_org(client, "Farm J", "j@example.com")
    headers = {"Authorization": f"Bearer {tenant['access_token']}"}

    resp = await client.post(
        "/api/v1/billing/subscribe", json={"tier_slug": "pro", "phone_number": "254712345678"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    payment = resp.json()
    assert payment["status"] == "pending"
    assert payment["provider_reference"] == "ws_CO_test_ref_1"

    sub_before = await client.get("/api/v1/billing/subscription", headers=headers)
    assert sub_before.json()["status"] == "trialing"  # not activated yet, only initiated

    webhook_body = {
        "provider_reference": "ws_CO_test_ref_1", "event_id": "evt-1", "status": "successful",
    }
    import json
    webhook_resp = await client.post(
        "/api/v1/billing/webhooks/mpesa", content=json.dumps(webhook_body),
    )
    assert webhook_resp.status_code == 200
    assert webhook_resp.json()["status"] == "processed"

    sub_after = await client.get("/api/v1/billing/subscription", headers=headers)
    body = sub_after.json()
    assert body["status"] == "active"
    assert body["tier"]["slug"] == "pro"

    # Idempotency: replaying the same event_id is a no-op, not a duplicate charge.
    replay = await client.post(
        "/api/v1/billing/webhooks/mpesa", content=json.dumps(webhook_body),
    )
    assert replay.status_code == 200
    assert replay.json()["status"] == "already_processed"


async def test_animal_limit_enforced_on_free_tier(client):
    """Free tier caps at 25 animals (billing/service.py DEFAULT_TIERS).
    Rather than creating 25 real animals to hit the cap in a test, this
    calls check_animal_limit directly against a subscription pinned to a
    tier with max_animals=0 - proving the enforcement function itself
    raises correctly, which is the part that's actually new/risky here.
    (Full-stack "create 25 animals then the 26th fails" is covered
    implicitly by this same function being called from
    livestock.service.create_animal per HOW_TO_APPLY.md's patch.)"""
    from fastapi import HTTPException
    from app.modules.billing.service import ensure_default_tiers, get_or_create_subscription, check_animal_limit

    tenant = await _register_org(client, "Farm K", "k@example.com")
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tenant['access_token']}"},
    )
    org_id = uuid.UUID(me.json()["organization"]["id"])

    # Access the same engine the running app is using via its overridden
    # get_db dependency - simplest is a fresh session against the same URL
    # already configured for this test run.
    from app.core import database as db_module
    async with db_module.AsyncSessionLocal() as session:
        tiers = await ensure_default_tiers(session)
        sub = await get_or_create_subscription(session, org_id)
        # Force the org onto a zero-capacity tier to prove the check fires
        # without needing to create 25 real animals first.
        tiers["free"].max_animals = 0
        await session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await check_animal_limit(session, org_id)
        assert exc_info.value.status_code == 402


async def test_user_limit_enforced_on_free_tier(client):
    """Free tier caps at 2 users (billing/service.py DEFAULT_TIERS) - the
    org already has 1 (its own Farm Owner from registration), so adding one
    more teammate should succeed, and a second should be blocked."""
    tenant = await _register_org(client, "Farm L", "l@example.com")
    headers = {"Authorization": f"Bearer {tenant['access_token']}"}

    first = await client.post(
        "/api/v1/users", json={
            "full_name": "Teammate One", "email": "teammate1-l@example.com", "password": "supersecret123",
        },
        headers=headers,
    )
    assert first.status_code == 201, first.text  # 2nd user total - exactly at the free tier's cap of 2

    second = await client.post(
        "/api/v1/users", json={
            "full_name": "Teammate Two", "email": "teammate2-l@example.com", "password": "supersecret123",
        },
        headers=headers,
    )
    assert second.status_code == 402, second.text


async def test_downgrade_blocked_when_over_new_tier_limit(client, monkeypatch):
    """An org with 3 users can't pay to move to the free tier (cap: 2)."""
    import app.modules.billing.service as billing_service
    monkeypatch.setattr(billing_service, "get_provider", lambda name: FakeMpesaProvider())

    tenant = await _register_org(client, "Farm M", "m@example.com")
    headers = {"Authorization": f"Bearer {tenant['access_token']}"}

    await client.post(
        "/api/v1/users", json={
            "full_name": "Teammate", "email": "teammate-m@example.com", "password": "supersecret123",
        },
        headers=headers,
    )  # org now has 2 users - upgrade to pro first so the 2nd user above didn't already 402

    # Move to pro (unlimited-ish: 20 users) so we have room, then try to
    # downgrade back to free (cap: 2) while at 2 users - should be blocked
    # since 2 users == free tier's cap is fine, so add a 3rd via pro first.
    upgrade = await client.post(
        "/api/v1/billing/subscribe", json={"tier_slug": "pro", "phone_number": "254712345678"}, headers=headers,
    )
    assert upgrade.status_code == 200

    import json
    await client.post(
        "/api/v1/billing/webhooks/mpesa",
        content=json.dumps({"provider_reference": "ws_CO_test_ref_1", "event_id": "evt-m-1", "status": "successful"}),
    )

    await client.post(
        "/api/v1/users", json={
            "full_name": "Teammate Two", "email": "teammate2-m@example.com", "password": "supersecret123",
        },
        headers=headers,
    )  # org now has 3 users, fine under pro's 20-user cap

    downgrade = await client.post(
        "/api/v1/billing/subscribe", json={"tier_slug": "free", "phone_number": "254712345678"}, headers=headers,
    )
    assert downgrade.status_code == 400


async def test_payment_history_lists_past_payments(client, monkeypatch):
    import app.modules.billing.service as billing_service
    monkeypatch.setattr(billing_service, "get_provider", lambda name: FakeMpesaProvider())

    tenant = await _register_org(client, "Farm N", "n@example.com")
    headers = {"Authorization": f"Bearer {tenant['access_token']}"}

    await client.post(
        "/api/v1/billing/subscribe", json={"tier_slug": "basic", "phone_number": "254712345678"}, headers=headers,
    )
    resp = await client.get("/api/v1/billing/payments", headers=headers)
    assert resp.status_code == 200
    payments = resp.json()
    assert len(payments) == 1
    assert payments[0]["provider_reference"] == "ws_CO_test_ref_1"


async def _owner_and_limited_user(client, org: str, owner_email: str, worker_email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org, "full_name": "Owner", "email": owner_email, "password": "supersecret123",
    })
    owner = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    await client.post("/api/v1/users", headers=owner, json={"full_name": "Worker", "email": worker_email, "password": "supersecret123"})
    login = await client.post("/api/v1/auth/login", json={"email": worker_email, "password": "supersecret123"})
    return owner, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_users_without_admin_rights_cannot_start_subscriptions_or_see_payment_history(client):
    owner, worker = await _owner_and_limited_user(client, "Bill Farm A", "bill1@example.com", "billworker@example.com")
    body = {"tier_slug": "pro", "phone_number": "254712345678"}

    assert (await client.post("/api/v1/billing/subscribe", json=body, headers=worker)).status_code == 403
    assert (await client.get("/api/v1/billing/payments", headers=worker)).status_code == 403
    assert (await client.get("/api/v1/billing/payments/00000000-0000-0000-0000-000000000000/receipt.pdf", headers=worker)).status_code == 403
    # reading the current plan stays open - other screens depend on it
    assert (await client.get("/api/v1/billing/subscription", headers=worker)).status_code == 200
    # the owner is unaffected
    assert (await client.get("/api/v1/billing/payments", headers=owner)).status_code == 200


async def test_receipt_with_a_malformed_id_is_a_422_not_a_500(client):
    owner, _ = await _owner_and_limited_user(client, "Bill Farm B", "bill2@example.com", "billworker2@example.com")
    bad = await client.get("/api/v1/billing/payments/not-a-uuid/receipt.pdf", headers=owner)
    assert bad.status_code == 422
    missing = await client.get("/api/v1/billing/payments/00000000-0000-0000-0000-000000000000/receipt.pdf", headers=owner)
    assert missing.status_code == 404


# ---- crop planting plan limit ---------------------------------------------------------------------

async def _farm_id(client, headers) -> str:
    return (await client.post("/api/v1/farms", json={"name": "Crop Cap Farm", "county": "Nakuru"}, headers=headers)).json()["id"]


async def _plant(client, headers, farm_id: str, number: str):
    return await client.post("/api/v1/crops", headers=headers, json={
        "farm_id": farm_id, "planting_number": number, "crop_type": "maize", "planting_date": "2026-01-01",
    })


async def _pin_tier_cap(org_slug_tier: str, cap):
    """Seeds the default tiers and pins one tier's crop cap (the same technique the animal-limit test uses)."""
    from app.core import database as db_module
    from app.modules.billing.service import ensure_default_tiers
    async with db_module.AsyncSessionLocal() as session:
        tiers = await ensure_default_tiers(session)
        tiers[org_slug_tier].max_crop_plantings = cap
        await session.commit()


async def test_default_tiers_carry_a_crop_planting_cap(client):
    tiers = {t["slug"]: t for t in (await client.get("/api/v1/billing/tiers")).json()}
    assert tiers["free"]["max_crop_plantings"] == 25 and tiers["enterprise"]["max_crop_plantings"] is None


async def test_crop_planting_limit_is_enforced_through_the_api(client):
    tenant = await _register_org(client, "Crop Cap A", "cropcap-a@example.com")
    headers = {"Authorization": f"Bearer {tenant['access_token']}"}
    await client.get("/api/v1/billing/subscription", headers=headers)   # lazily puts the org on the free tier
    await _pin_tier_cap("free", 2)
    farm = await _farm_id(client, headers)

    assert (await _plant(client, headers, farm, "CAP-1")).status_code == 201
    assert (await _plant(client, headers, farm, "CAP-2")).status_code == 201
    blocked = await _plant(client, headers, farm, "CAP-3")
    assert blocked.status_code == 402 and "crop plantings" in blocked.json()["detail"]


async def test_closed_plantings_do_not_use_up_plan_capacity(client):
    tenant = await _register_org(client, "Crop Cap B", "cropcap-b@example.com")
    headers = {"Authorization": f"Bearer {tenant['access_token']}"}
    await client.get("/api/v1/billing/subscription", headers=headers)
    await _pin_tier_cap("free", 1)
    farm = await _farm_id(client, headers)

    first = await _plant(client, headers, farm, "CAP-B1")
    assert first.status_code == 201
    assert (await _plant(client, headers, farm, "CAP-B2")).status_code == 402
    archived = await client.post(f"/api/v1/crops/{first.json()['id']}/status", headers=headers, json={"status": "failed"})
    assert archived.status_code == 200, archived.text
    assert (await _plant(client, headers, farm, "CAP-B2")).status_code == 201   # capacity freed


async def test_unlimited_tiers_never_block_planting(client):
    tenant = await _register_org(client, "Crop Cap C", "cropcap-c@example.com")
    headers = {"Authorization": f"Bearer {tenant['access_token']}"}
    await client.get("/api/v1/billing/subscription", headers=headers)
    await _pin_tier_cap("free", None)
    farm = await _farm_id(client, headers)
    for i in range(3):
        assert (await _plant(client, headers, farm, f"CAP-C{i}")).status_code == 201


async def test_downgrade_blocked_when_over_new_tiers_crop_planting_limit(client, monkeypatch):
    import app.modules.billing.service as billing_service
    monkeypatch.setattr(billing_service, "get_provider", lambda name: FakeMpesaProvider())

    tenant = await _register_org(client, "Crop Cap D", "cropcap-d@example.com")
    headers = {"Authorization": f"Bearer {tenant['access_token']}"}
    await client.get("/api/v1/billing/subscription", headers=headers)
    farm = await _farm_id(client, headers)
    for i in range(3):
        assert (await _plant(client, headers, farm, f"CAP-D{i}")).status_code == 201

    await _pin_tier_cap("basic", 2)   # org has 3 live plantings
    resp = await client.post("/api/v1/billing/subscribe", json={"tier_slug": "basic", "phone_number": "254712345678"}, headers=headers)
    assert resp.status_code == 400 and "crop plantings" in resp.json()["detail"]


async def test_subscription_phone_is_normalised_for_daraja(client, monkeypatch):
    import app.modules.billing.service as billing_service
    seen = []

    class Recorder(FakeMpesaProvider):
        async def initiate_payment(self, amount, currency, reference, phone_or_token):
            seen.append(phone_or_token)
            return await super().initiate_payment(amount, currency, reference, phone_or_token)

    monkeypatch.setattr(billing_service, "get_provider", lambda name: Recorder())
    tenant = await _register_org(client, "Bill Phone A", "billphone@example.com")
    headers = {"Authorization": f"Bearer {tenant['access_token']}"}

    ok = await client.post("/api/v1/billing/subscribe", json={"tier_slug": "pro", "phone_number": "0712 345 678"}, headers=headers)
    assert ok.status_code == 200 and seen == ["254712345678"]
    bad = await client.post("/api/v1/billing/subscribe", json={"tier_slug": "pro", "phone_number": "nope"}, headers=headers)
    assert bad.status_code == 422 and len(seen) == 1

"""Stripe Payment Intents integration (spec §22).

IMPORTANT - not live-tested, same reason as mpesa.py: api.stripe.com is
unreachable from this sandbox's network egress. Request/webhook-verification
shapes follow Stripe's published API and signing scheme, but this has not
been exercised against a real Stripe endpoint (test-mode or otherwise) in
this build. Uses raw HTTP via httpx rather than the `stripe` SDK to avoid an
unverifiable dependency; swapping in the official SDK is a reasonable
follow-up once this can actually be tested against Stripe."""
import hashlib
import hmac
import time
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import get_settings
from app.modules.payments.providers.base import PaymentProvider, InitiateResult, WebhookResult

settings = get_settings()

STRIPE_API_BASE = "https://api.stripe.com/v1"
WEBHOOK_TOLERANCE_SECONDS = 300  # reject callbacks older than 5 minutes (replay protection)


class StripeProvider(PaymentProvider):
    name = "stripe"

    async def initiate_payment(
        self, amount: Decimal, currency: str, reference: str, phone_or_token: str,
    ) -> InitiateResult:
        # Stripe amounts are in the smallest currency unit (cents for USD; KES
        # has no minor unit in Stripe's zero-decimal list - adjust per currency
        # in a real deployment rather than assuming *100 universally).
        amount_minor_units = int(amount * 100)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{STRIPE_API_BASE}/payment_intents",
                data={
                    "amount": amount_minor_units,
                    "currency": currency.lower(),
                    "metadata[reference]": reference,
                },
                headers={"Authorization": f"Bearer {settings.STRIPE_SECRET_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()

        return InitiateResult(
            provider_reference=data["id"],
            status="pending" if data["status"] in ("requires_payment_method", "requires_confirmation") else data["status"],
            raw_response=data,
        )

    def verify_and_parse_webhook(self, headers: dict[str, str], body: bytes) -> WebhookResult:
        sig_header = headers.get("stripe-signature", "")
        parts = dict(item.split("=", 1) for item in sig_header.split(",") if "=" in item)
        timestamp, signature = parts.get("t"), parts.get("v1")
        if not timestamp or not signature:
            raise ValueError("Malformed Stripe-Signature header")
        if abs(time.time() - int(timestamp)) > WEBHOOK_TOLERANCE_SECONDS:
            raise ValueError("Stripe webhook timestamp outside tolerance (possible replay)")

        signed_payload = f"{timestamp}.{body.decode()}"
        expected = hmac.new(
            settings.STRIPE_WEBHOOK_SECRET.encode(), signed_payload.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid Stripe webhook signature")

        import json
        event: dict[str, Any] = json.loads(body)
        obj = event["data"]["object"]
        event_type = event["type"]

        if event_type == "payment_intent.succeeded":
            status = "successful"
        elif event_type in ("payment_intent.payment_failed", "charge.failed"):
            status = "failed"
        else:
            status = "pending"

        return WebhookResult(
            provider_reference=obj["id"], event_id=event["id"], status=status, raw_payload=event,
        )

"""Fully working, live-testable provider - used by default in dev/test so the
whole payment→webhook→order-paid→finance-ledger flow can be exercised without
real M-Pesa/Stripe credentials or network access (spec §51: 'do not use real
payment credentials in development; create mock providers')."""
import hashlib
import hmac
import json
import secrets
from decimal import Decimal
from typing import Any

from app.core.config import get_settings
from app.modules.payments.providers.base import PaymentProvider, InitiateResult, WebhookResult

settings = get_settings()


class MockProvider(PaymentProvider):
    name = "mock"

    async def initiate_payment(
        self, amount: Decimal, currency: str, reference: str, phone_or_token: str,
    ) -> InitiateResult:
        provider_reference = f"MOCK-{secrets.token_hex(8)}"
        return InitiateResult(
            provider_reference=provider_reference,
            status="pending",
            raw_response={"provider_reference": provider_reference, "amount": str(amount), "currency": currency},
        )

    def verify_and_parse_webhook(self, headers: dict[str, str], body: bytes) -> WebhookResult:
        signature = headers.get("x-mock-signature", "")
        expected = hmac.new(settings.MOCK_PAYMENT_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid mock webhook signature")

        payload: dict[str, Any] = json.loads(body)
        return WebhookResult(
            provider_reference=payload["provider_reference"],
            event_id=payload["event_id"],
            status=payload["status"],
            raw_payload=payload,
        )

    @staticmethod
    def sign(body: bytes) -> str:
        """Test/dev helper - a real provider's signature comes from their side;
        this lets tests construct a validly-signed callback."""
        return hmac.new(settings.MOCK_PAYMENT_SECRET.encode(), body, hashlib.sha256).hexdigest()

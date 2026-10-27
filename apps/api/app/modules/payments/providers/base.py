"""Spec §11/§20: provider-independent payment abstraction.

Every concrete provider implements this interface. The rest of the codebase
(payments/service.py) only ever talks to `PaymentProvider` - it never knows
whether it's driving M-Pesa, Stripe, or the mock, which is exactly the point:
a new provider is a new class here, nothing else changes."""
import abc
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass
class InitiateResult:
    provider_reference: str  # e.g. Daraja CheckoutRequestID, Stripe PaymentIntent id
    status: str  # "pending" | "failed"
    raw_response: dict[str, Any]


@dataclass
class WebhookResult:
    provider_reference: str
    event_id: str  # provider's own idempotency key for this specific callback
    status: str  # "successful" | "failed" | "pending"
    raw_payload: dict[str, Any]
    # Optional settlement details (M-Pesa supplies them; mock/Stripe leave them empty).
    amount: Decimal | None = None   # what the payer was actually charged
    receipt: str | None = None      # provider receipt, e.g. M-Pesa "NLJ7RT61SV"
    payer: str | None = None        # payer's phone number
    detail: str | None = None       # provider's human-readable result text


class PaymentProvider(abc.ABC):
    name: str

    @abc.abstractmethod
    async def initiate_payment(
        self, amount: Decimal, currency: str, reference: str, phone_or_token: str,
    ) -> InitiateResult:
        """Kick off a payment. For M-Pesa this is an STK Push; for Stripe this
        creates a PaymentIntent. Must NOT mark anything as paid - only the
        webhook/callback path (verify_and_parse_webhook) can do that (spec
        §20/§65.10: never trust client-reported payment status)."""

    async def query_status(self, provider_reference: str) -> "WebhookResult | None":
        """Ask the provider what became of a payment whose callback never arrived. None = not supported,
        or the provider says it is still processing. Optional: providers without it simply do not reconcile."""
        return None

    @abc.abstractmethod
    def verify_and_parse_webhook(self, headers: dict[str, str], body: bytes) -> WebhookResult:
        """Verify the callback's authenticity (signature/shared-secret check)
        and parse it into a normalized result. Raises ValueError on a failed
        signature check - callers must treat that as untrusted input, not a
        payment event."""

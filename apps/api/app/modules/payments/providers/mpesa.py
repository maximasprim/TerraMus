"""Safaricom Daraja STK Push integration (spec §21).

IMPORTANT - not live-tested. This sandbox's network egress is restricted to
package registries (pypi/npm/github); safaricom.co.ke is unreachable here.
The request/response shapes below follow Daraja's published API contract, but
unlike the Mock provider, this class has NOT been exercised against a real
(or even sandbox) Daraja endpoint as part of this build. Treat it as a
correctly-shaped starting point that needs real credentials + a reachable
network to validate, not as verified working code."""
import base64
import hashlib
import hmac
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.security_checks import is_production_like
from app.modules.payments.providers.base import PaymentProvider, InitiateResult, WebhookResult

settings = get_settings()

DARAJA_BASE_URL = "https://sandbox.safaricom.co.ke"  # switch to api.safaricom.co.ke in production


class MpesaDarajaProvider(PaymentProvider):
    name = "mpesa"

    async def _get_access_token(self) -> str:
        auth = base64.b64encode(
            f"{settings.DARAJA_CONSUMER_KEY}:{settings.DARAJA_CONSUMER_SECRET}".encode()
        ).decode()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{DARAJA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials",
                headers={"Authorization": f"Basic {auth}"},
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def initiate_payment(
        self, amount: Decimal, currency: str, reference: str, phone_or_token: str,
    ) -> InitiateResult:
        # currency is ignored - Daraja STK Push is KES-only.
        token = await self._get_access_token()
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        password = base64.b64encode(
            f"{settings.DARAJA_SHORTCODE}{settings.DARAJA_PASSKEY}{timestamp}".encode()
        ).decode()

        payload = {
            "BusinessShortCode": settings.DARAJA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone_or_token,
            "PartyB": settings.DARAJA_SHORTCODE,
            "PhoneNumber": phone_or_token,
            "CallBackURL": settings.DARAJA_CALLBACK_URL,
            "AccountReference": reference,
            "TransactionDesc": f"Payment for {reference}",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{DARAJA_BASE_URL}/mpesa/stkpush/v1/processrequest",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            data = resp.json()

        return InitiateResult(
            provider_reference=data["CheckoutRequestID"],
            status="pending" if data.get("ResponseCode") == "0" else "failed",
            raw_response=data,
        )

    def verify_and_parse_webhook(self, headers: dict[str, str], body: bytes) -> WebhookResult:
        # Daraja does not sign callbacks with HMAC by default; the common
        # real-world mitigation is a shared secret embedded in the registered
        # CallBackURL itself (checked at the router level via the URL path)
        # plus IP allow-listing at the infra layer. We additionally accept an
        # optional shared-secret header for deployments that add one via a
        # reverse proxy in front of the callback endpoint.
        expected = getattr(settings, "DARAJA_CALLBACK_SHARED_SECRET", None)
        if not expected and is_production_like(settings.ENV):
            # Without a secret ANYONE could POST a "successful" callback for a
            # CheckoutRequestID (which the public pay endpoint returns to the
            # buyer) and mark their own order paid. Refuse rather than trust.
            raise ValueError("M-Pesa callback secret is not configured")
        if expected:
            provided = headers.get("x-callback-secret", "")
            if not hmac.compare_digest(provided, expected):
                raise ValueError("Invalid M-Pesa callback shared secret")

        import json
        payload: dict[str, Any] = json.loads(body)
        callback = payload["Body"]["stkCallback"]
        checkout_request_id = callback["CheckoutRequestID"]
        result_code = callback["ResultCode"]

        status = "successful" if result_code == 0 else "failed"
        # MerchantRequestID + CheckoutRequestID together are Daraja's own
        # idempotency identifiers for this callback.
        event_id = f"{callback['MerchantRequestID']}:{checkout_request_id}"

        return WebhookResult(
            provider_reference=checkout_request_id, event_id=event_id, status=status, raw_payload=payload,
        )

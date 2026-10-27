"""Safaricom Daraja STK Push integration (spec §21).

Not live-tested: this build environment cannot reach safaricom.co.ke. The request shapes follow Daraja's published
contract and are exercised against a recorded-traffic test double (tests/test_mpesa_hardening.py), not a real
endpoint. Validate with sandbox credentials before going live.

Fixed here after review:
  * the callback shared secret is carried in the callback URL path (Safaricom cannot send custom headers, so the old
    header-only check would have rejected every genuine callback in production);
  * the host comes from DARAJA_ENV, not a constant (production used to need a code change);
  * the timestamp is Nairobi time, not whatever the server's clock says;
  * amounts are rounded UP to whole shillings (Daraja takes integers; truncating silently under-charged);
  * the callback's amount and receipt are extracted so they can be checked and stored;
  * a status query exists so a lost callback does not leave a paid order unpaid."""
import base64
import hmac
import json
import re
from datetime import datetime
from decimal import ROUND_CEILING, Decimal
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.core.config import get_settings
from app.core.security_checks import is_production_like
from app.modules.payments.providers.base import InitiateResult, PaymentProvider, WebhookResult

settings = get_settings()

DARAJA_HOSTS = {"sandbox": "https://sandbox.safaricom.co.ke", "production": "https://api.safaricom.co.ke"}
SAFE_SECRET = re.compile(r"^[A-Za-z0-9_-]{24,}$")


def daraja_base_url() -> str:
    override = (settings.DARAJA_BASE_URL or "").strip().rstrip("/")
    if override:
        return override
    return DARAJA_HOSTS["production" if (settings.DARAJA_ENV or "").strip().lower() == "production" else "sandbox"]


def stk_amount(amount: Decimal) -> int:
    """Whole shillings, rounded UP so the customer is never charged less than the order total."""
    whole = int(Decimal(amount).to_integral_value(rounding=ROUND_CEILING))
    if whole < 1:
        raise ValueError("M-Pesa amount must be at least KES 1")
    return whole


def callback_url() -> str:
    """The URL sent to Safaricom: the public webhook address plus the secret as the final path segment."""
    base = (settings.DARAJA_CALLBACK_URL or "").rstrip("/")
    secret = settings.DARAJA_CALLBACK_SHARED_SECRET
    if secret and not base.endswith("/" + secret):
        if not SAFE_SECRET.match(secret):
            raise ValueError("DARAJA_CALLBACK_SHARED_SECRET must be 24+ URL-safe characters (letters, digits, - and _)")
        return f"{base}/{secret}"
    return base


def _nairobi_timestamp() -> str:
    return datetime.now(ZoneInfo(settings.DEFAULT_TIMEZONE)).strftime("%Y%m%d%H%M%S")


class MpesaDarajaProvider(PaymentProvider):
    name = "mpesa"
    client_factory = staticmethod(httpx.AsyncClient)     # replaced in tests by a client over a mock transport

    def _client(self):
        return self.client_factory(timeout=15)

    async def _get_access_token(self) -> str:
        auth = base64.b64encode(f"{settings.DARAJA_CONSUMER_KEY}:{settings.DARAJA_CONSUMER_SECRET}".encode()).decode()
        async with self._client() as client:
            resp = await client.get(f"{daraja_base_url()}/oauth/v1/generate?grant_type=client_credentials",
                                    headers={"Authorization": f"Basic {auth}"})
            resp.raise_for_status()
            return resp.json()["access_token"]

    def _password(self, timestamp: str) -> str:
        return base64.b64encode(f"{settings.DARAJA_SHORTCODE}{settings.DARAJA_PASSKEY}{timestamp}".encode()).decode()

    async def initiate_payment(self, amount: Decimal, currency: str, reference: str, phone_or_token: str) -> InitiateResult:
        # currency is ignored - Daraja STK Push is KES-only.
        whole = stk_amount(amount)
        token = await self._get_access_token()
        timestamp = _nairobi_timestamp()
        payload = {
            "BusinessShortCode": settings.DARAJA_SHORTCODE, "Password": self._password(timestamp), "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline", "Amount": whole, "PartyA": phone_or_token,
            "PartyB": settings.DARAJA_SHORTCODE, "PhoneNumber": phone_or_token, "CallBackURL": callback_url(),
            "AccountReference": reference[:12], "TransactionDesc": f"Payment for {reference}"[:13],
        }
        async with self._client() as client:
            resp = await client.post(f"{daraja_base_url()}/mpesa/stkpush/v1/processrequest", json=payload,
                                     headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            data = resp.json()
        return InitiateResult(
            provider_reference=data["CheckoutRequestID"], status="pending" if data.get("ResponseCode") == "0" else "failed",
            raw_response={**data, "stk_amount": whole},
        )

    async def query_status(self, provider_reference: str) -> WebhookResult | None:
        """STK Push Query: what happened to a prompt whose callback we never received. The answer carries a result
        code but no receipt or amount, so a payment settled this way is recorded as 'confirmed by status query'."""
        token = await self._get_access_token()
        timestamp = _nairobi_timestamp()
        payload = {"BusinessShortCode": settings.DARAJA_SHORTCODE, "Password": self._password(timestamp),
                   "Timestamp": timestamp, "CheckoutRequestID": provider_reference}
        async with self._client() as client:
            resp = await client.post(f"{daraja_base_url()}/mpesa/stkpushquery/v1/query", json=payload,
                                     headers={"Authorization": f"Bearer {token}"})
        try:
            data = resp.json()
        except ValueError:
            return None
        if resp.status_code >= 400 or data.get("ResultCode") in (None, ""):
            return None            # Daraja answers an error (500.001.1001) while the transaction is still being processed
        code = int(data["ResultCode"])
        return WebhookResult(provider_reference=provider_reference, event_id=f"query:{provider_reference}",
                             status="successful" if code == 0 else "failed", raw_payload=data, detail=data.get("ResultDesc"))

    def verify_and_parse_webhook(self, headers: dict[str, str], body: bytes) -> WebhookResult:
        # Daraja does not sign callbacks. The secret travels in the callback URL path (the router passes it on as the
        # x-callback-secret value); a reverse proxy may alternatively inject that header.
        expected = settings.DARAJA_CALLBACK_SHARED_SECRET
        if not expected and is_production_like(settings.ENV):
            # Without a secret ANYONE could POST a "successful" callback for a CheckoutRequestID (the public pay
            # endpoint returns it to the buyer) and mark their own order paid. Refuse rather than trust.
            raise ValueError("M-Pesa callback secret is not configured")
        if expected and not hmac.compare_digest(headers.get("x-callback-secret", ""), expected):
            raise ValueError("Invalid M-Pesa callback shared secret")

        payload: dict[str, Any] = json.loads(body)
        callback = payload["Body"]["stkCallback"]
        checkout_request_id = callback["CheckoutRequestID"]
        result_code = int(callback["ResultCode"])
        items = {i["Name"]: i.get("Value") for i in (callback.get("CallbackMetadata") or {}).get("Item", [])
                 if isinstance(i, dict) and "Name" in i}
        amount = Decimal(str(items["Amount"])) if items.get("Amount") is not None else None
        return WebhookResult(
            provider_reference=checkout_request_id, event_id=f"{callback['MerchantRequestID']}:{checkout_request_id}",
            status="successful" if result_code == 0 else "failed", raw_payload=payload, amount=amount,
            receipt=str(items["MpesaReceiptNumber"]) if items.get("MpesaReceiptNumber") else None,
            payer=str(items["PhoneNumber"]) if items.get("PhoneNumber") else None, detail=callback.get("ResultDesc"),
        )

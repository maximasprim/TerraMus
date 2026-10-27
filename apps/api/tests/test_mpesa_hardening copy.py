"""M-Pesa fixes from the review: callback secret in the URL path, host from DARAJA_ENV, Nairobi timestamp, whole-shilling
rounding, amount/receipt verification, late/duplicate payments routed to review (never lost), lost-callback reconciliation."""
import base64
import json
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.modules.payments.providers.mpesa as mpesa_mod
import app.modules.payments.service as payment_service
from app.core.config import get_settings
from app.core.security_checks import daraja_warnings
from app.modules.payments.providers.base import InitiateResult
from app.modules.payments.providers.mpesa import MpesaDarajaProvider
from test_guest_checkout import _setup_listing

pytestmark = pytest.mark.asyncio
settings = get_settings()
SECRET = "Xk3dP9aQ7mZr2LwN5tBv8YcH"            # 24 URL-safe characters
DARAJA = {"DARAJA_CONSUMER_KEY": "k", "DARAJA_CONSUMER_SECRET": "s", "DARAJA_SHORTCODE": "174379", "DARAJA_PASSKEY": "pk",
          "DARAJA_CALLBACK_URL": "https://farm.example.com/api/v1/payments/webhooks/mpesa", "DARAJA_CALLBACK_SHARED_SECRET": SECRET}


@pytest.fixture
def daraja(monkeypatch):
    for k, v in DARAJA.items():
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(settings, "DARAJA_ENV", "sandbox")
    monkeypatch.setattr(settings, "DARAJA_BASE_URL", "")


def mock_safaricom(monkeypatch, on_query=None):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        p = request.url.path
        if p.endswith("/oauth/v1/generate"):
            return httpx.Response(200, json={"access_token": "tok"})
        if p.endswith("/stkpush/v1/processrequest"):
            return httpx.Response(200, json={"MerchantRequestID": "m-1", "CheckoutRequestID": "ws_CO_REAL", "ResponseCode": "0"})
        if p.endswith("/stkpushquery/v1/query"):
            return on_query(request) if on_query else httpx.Response(200, json={"ResultCode": "0", "ResultDesc": "ok"})
        return httpx.Response(404)
    monkeypatch.setattr(MpesaDarajaProvider, "client_factory", staticmethod(lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kw)))
    return seen


# ------------------------------------------------------------------ the provider
async def test_stk_request_uses_env_host_nairobi_time_rounded_up_amount_and_secret_in_callback_path(daraja, monkeypatch):
    seen = mock_safaricom(monkeypatch)
    res = await MpesaDarajaProvider().initiate_payment(Decimal("1500.40"), "KES", "a" * 36, "254712345678")
    stk = next(r for r in seen if r.url.path.endswith("processrequest"))
    body = json.loads(stk.content)
    assert stk.url.host == "sandbox.safaricom.co.ke"
    assert body["Amount"] == 1501                                              # rounded UP, never truncated to 1500
    assert body["CallBackURL"] == f"https://farm.example.com/api/v1/payments/webhooks/mpesa/{SECRET}"
    assert len(body["AccountReference"]) <= 12
    nairobi = datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%Y%m%d%H")
    assert body["Timestamp"].startswith(nairobi)                               # Nairobi clock, not the server's
    assert base64.b64decode(body["Password"]).decode() == f"174379pk{body['Timestamp']}"
    assert res.raw_response["stk_amount"] == 1501 and res.provider_reference == "ws_CO_REAL"

    monkeypatch.setattr(settings, "DARAJA_ENV", "production")
    seen.clear(); await MpesaDarajaProvider().initiate_payment(Decimal("10"), "KES", "ref", "254712345678")
    assert {r.url.host for r in seen} == {"api.safaricom.co.ke"}              # production needs only the setting, not a code change
    monkeypatch.setattr(settings, "DARAJA_BASE_URL", "https://gateway.internal/")
    seen.clear(); await MpesaDarajaProvider().initiate_payment(Decimal("10"), "KES", "ref", "254712345678")
    assert {r.url.host for r in seen} == {"gateway.internal"}


async def test_unusable_amounts_and_secrets_are_refused_not_sent(daraja, monkeypatch):
    mock_safaricom(monkeypatch)
    with pytest.raises(ValueError):
        await MpesaDarajaProvider().initiate_payment(Decimal("0"), "KES", "ref", "254712345678")
    monkeypatch.setattr(settings, "DARAJA_CALLBACK_SHARED_SECRET", "short")            # would break the URL or be guessable
    with pytest.raises(ValueError, match="DARAJA_CALLBACK_SHARED_SECRET"):
        await MpesaDarajaProvider().initiate_payment(Decimal("100"), "KES", "ref", "254712345678")


def callback(checkout="ws_CO_1", merchant="mr-1", code=0, amount=None, receipt="NLJ7RT61SV"):
    cb = {"MerchantRequestID": merchant, "CheckoutRequestID": checkout, "ResultCode": code,
          "ResultDesc": "The service request is processed successfully." if code == 0 else "Request cancelled by user"}
    if code == 0:
        cb["CallbackMetadata"] = {"Item": [{"Name": "Amount", "Value": amount}, {"Name": "MpesaReceiptNumber", "Value": receipt},
                                           {"Name": "TransactionDate", "Value": 20260101101010}, {"Name": "PhoneNumber", "Value": 254712345678}]}
    return {"Body": {"stkCallback": cb}}


def test_callback_parsing_extracts_amount_receipt_and_payer(daraja):
    r = MpesaDarajaProvider().verify_and_parse_webhook({"x-callback-secret": SECRET}, json.dumps(callback(amount=1501.0)).encode())
    assert r.status == "successful" and r.amount == Decimal("1501.0") and r.receipt == "NLJ7RT61SV" and r.payer == "254712345678"
    f = MpesaDarajaProvider().verify_and_parse_webhook({"x-callback-secret": SECRET}, json.dumps(callback(code=1032)).encode())
    assert f.status == "failed" and f.amount is None and f.detail == "Request cancelled by user"


# ----------------------------------------------------------- the whole flow over HTTP
class Hybrid:
    """Records the prompt like the existing stub, but verifies callbacks and queries status with the REAL provider."""
    def __init__(self):
        self.real = MpesaDarajaProvider(); self.n = 0

    async def initiate_payment(self, amount, currency, reference, phone_or_token):
        self.n += 1
        return InitiateResult(provider_reference=f"ws_CO_{self.n}", status="pending", raw_response={"stk_amount": int(amount) + 1})

    def verify_and_parse_webhook(self, headers, body):
        return self.real.verify_and_parse_webhook(headers, body)

    async def query_status(self, ref):
        return await self.real.query_status(ref)


@pytest.fixture
def flow(daraja, monkeypatch):
    p = Hybrid()
    monkeypatch.setattr(payment_service, "get_provider", lambda name: p)
    return p


async def _order(client, org, email):
    h, org_slug, _, slug = await _setup_listing(client, org, email)
    guest = f"guest-{email}"
    oid = (await client.post(f"/api/v1/public/{org_slug}/orders", json={"customer_name": "Jane", "customer_email": guest, "items": [{"listing_slug": slug}]})).json()["order_id"]
    pay = await client.post(f"/api/v1/public/{org_slug}/orders/{oid}/pay/mpesa", json={"phone_or_token": "0712345678", "email": guest})
    assert pay.status_code == 201, pay.text
    return h, org_slug, oid, guest


async def _state(engine, oid):
    async with engine.connect() as c:
        pay = (await c.execute(text("SELECT status, payment_metadata, amount, provider_reference FROM payments WHERE order_id = :o"), {"o": oid})).one()
        order = (await c.execute(text("SELECT status FROM orders WHERE id = :o"), {"o": oid})).scalar_one()
    return pay, order


HOOK = "/api/v1/payments/webhooks/mpesa"


async def test_genuine_callback_with_secret_in_the_path_settles_the_order_and_records_the_receipt(client, engine, flow):
    h, slug, oid, guest = await _order(client, "Mp Farm 1", "mp1@example.com")
    pay, _ = await _state(engine, oid)
    amount = float(Decimal(pay.amount).to_integral_value(rounding="ROUND_CEILING"))
    body = callback(checkout=pay.provider_reference, amount=amount)
    assert (await client.post(f"{HOOK}/{SECRET}", json=body)).json()["payment_status"] == "successful"
    pay, order = await _state(engine, oid)
    assert pay.status == "successful" and order == "paid"
    assert pay.payment_metadata["settlement"]["receipt"] == "NLJ7RT61SV" and pay.payment_metadata["settlement"]["paid_amount"] == str(amount)
    assert (await client.post(f"{HOOK}/{SECRET}", json=body)).json()["status"] == "already_processed"        # a re-delivery changes nothing


async def test_wrong_or_missing_secret_is_rejected_and_changes_nothing(client, engine, flow):
    h, slug, oid, guest = await _order(client, "Mp Farm 2", "mp2@example.com")
    pay, _ = await _state(engine, oid)
    body = callback(checkout=pay.provider_reference, amount=float(Decimal(pay.amount).to_integral_value(rounding="ROUND_CEILING")))
    assert (await client.post(f"{HOOK}/wrong-secret-wrong-secret-xx", json=body)).status_code == 401
    assert (await client.post(HOOK, json=body)).status_code == 401                                            # no secret at all
    assert (await client.post(HOOK, json=body, headers={"x-callback-secret": SECRET})).json()["payment_status"] == "successful"   # proxy-injected header still works
    assert (await _state(engine, oid))[1] == "paid"


async def test_amount_that_does_not_match_the_order_goes_to_review_and_alerts_staff(client, engine, flow):
    h, slug, oid, guest = await _order(client, "Mp Farm 3", "mp3@example.com")
    pay, _ = await _state(engine, oid)
    r = (await client.post(f"{HOOK}/{SECRET}", json=callback(checkout=pay.provider_reference, amount=10.0))).json()
    assert r["payment_status"] == "needs_review" and "amount_mismatch" in r["problems"][0]
    pay, order = await _state(engine, oid)
    assert pay.status == "needs_review" and order == "payment_pending"                                       # the order is NOT marked paid
    titles = [n["title"] for n in (await client.get("/api/v1/notifications", headers=h)).json()]
    assert "Payment needs review" in titles


async def test_payment_after_the_order_was_cancelled_is_recorded_not_lost(client, engine, flow):
    h, slug, oid, guest = await _order(client, "Mp Farm 4", "mp4@example.com")
    cancel = await client.post(f"/api/v1/orders/{oid}/status", headers=h, json={"status": "cancelled", "reason": "customer asked"})
    assert cancel.status_code == 200, cancel.text
    pay, _ = await _state(engine, oid)
    amount = float(Decimal(pay.amount).to_integral_value(rounding="ROUND_CEILING"))
    resp = await client.post(f"{HOOK}/{SECRET}", json=callback(checkout=pay.provider_reference, amount=amount, receipt="LATE123"))
    assert resp.status_code == 200                                                                          # was a 409 that rolled everything back
    r = resp.json(); assert r["payment_status"] == "needs_review" and "order_not_payable" in r["problems"][0]
    pay, order = await _state(engine, oid)
    assert pay.status == "needs_review" and order == "cancelled" and pay.payment_metadata["settlement"]["receipt"] == "LATE123"
    assert "Payment needs review" in [n["title"] for n in (await client.get("/api/v1/notifications", headers=h)).json()]


async def test_a_duplicate_receipt_is_never_applied_twice(client, engine, flow):
    h, slug, oid, guest = await _order(client, "Mp Farm 5", "mp5@example.com")
    pay, _ = await _state(engine, oid)
    amount = float(Decimal(pay.amount).to_integral_value(rounding="ROUND_CEILING"))
    await client.post(f"{HOOK}/{SECRET}", json=callback(checkout=pay.provider_reference, amount=amount, receipt="SAME1"))
    async with engine.begin() as c:     # a second prompt for the same order, as if the customer retried
        await c.execute(text("INSERT INTO payments (id, organization_id, order_id, provider, provider_reference, amount, currency, status, initiated_at, payment_metadata, created_at, updated_at) "
                             "SELECT gen_random_uuid(), organization_id, order_id, provider, 'ws_CO_dup', amount, currency, 'pending', now(), '{}'::jsonb, now(), now() FROM payments WHERE order_id = :o LIMIT 1"), {"o": oid})
    r = (await client.post(f"{HOOK}/{SECRET}", json=callback(checkout="ws_CO_dup", merchant="mr-2", amount=amount, receipt="SAME1"))).json()
    assert r["payment_status"] == "needs_review" and any("duplicate_receipt" in p for p in r["problems"])


async def test_a_late_failure_never_undoes_a_settled_payment(client, engine, flow):
    h, slug, oid, guest = await _order(client, "Mp Farm 6", "mp6@example.com")
    pay, _ = await _state(engine, oid)
    amount = float(Decimal(pay.amount).to_integral_value(rounding="ROUND_CEILING"))
    await client.post(f"{HOOK}/{SECRET}", json=callback(checkout=pay.provider_reference, amount=amount))
    r = (await client.post(f"{HOOK}/{SECRET}", json=callback(checkout=pay.provider_reference, merchant="mr-late", code=1032))).json()
    assert r["status"] == "ignored" and (await _state(engine, oid))[0].status == "successful"


async def test_a_customer_who_cancels_the_prompt_can_try_again(client, engine, flow):
    h, slug, oid, guest = await _order(client, "Mp Farm 7", "mp7@example.com")
    pay, _ = await _state(engine, oid)
    assert (await client.post(f"{HOOK}/{SECRET}", json=callback(checkout=pay.provider_reference, code=1032))).json()["payment_status"] == "failed"
    again = await client.post(f"/api/v1/public/{slug}/orders/{oid}/pay/mpesa", json={"phone_or_token": "0712345678", "email": guest})
    assert again.status_code == 201


# ----------------------------------------------------------- lost callbacks
async def test_reconciliation_settles_paid_orders_whose_callback_never_arrived(client, engine, flow, monkeypatch):
    h, slug, oid, guest = await _order(client, "Mp Farm 8", "mp8@example.com")
    mock_safaricom(monkeypatch, on_query=lambda r: httpx.Response(200, json={"ResultCode": "0", "ResultDesc": "The service request is processed successfully."}))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        out = await payment_service.reconcile_pending(s, "mpesa", min_age_minutes=0)
    assert out["settled"] == 1
    pay, order = await _state(engine, oid)
    assert pay.status == "successful" and order == "paid" and pay.payment_metadata["settlement"]["source"] == "status_query"


async def test_reconciliation_marks_cancelled_prompts_failed_and_leaves_in_flight_ones_alone(client, engine, flow, monkeypatch):
    h, slug, oid, guest = await _order(client, "Mp Farm 9", "mp9@example.com")
    mock_safaricom(monkeypatch, on_query=lambda r: httpx.Response(200, json={"ResultCode": "1032", "ResultDesc": "Request cancelled by user"}))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        assert (await payment_service.reconcile_pending(s, "mpesa", min_age_minutes=0))["failed"] == 1
    assert (await _state(engine, oid))[0].status == "failed"
    h2, slug2, oid2, g2 = await _order(client, "Mp Farm 10", "mp10@example.com")
    mock_safaricom(monkeypatch, on_query=lambda r: httpx.Response(500, json={"errorCode": "500.001.1001", "errorMessage": "The transaction is being processed"}))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        out = await payment_service.reconcile_pending(s, "mpesa", min_age_minutes=0)
    assert out["still_pending"] == 1 and (await _state(engine, oid2))[0].status == "pending"
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:           # too-recent prompts are not queried at all
        assert (await payment_service.reconcile_pending(s, "mpesa", min_age_minutes=60))["checked"] == 0


# ------------------------------------------------------------ misconfiguration warnings
def test_production_misconfigurations_are_called_out():
    assert daraja_warnings("development", "sandbox", "key", "http://x", "") == []                    # dev: nothing to say
    assert daraja_warnings("production", "sandbox", "", "http://x", "") == []                        # M-Pesa not in use
    w = " ".join(daraja_warnings("production", "sandbox", "key", "http://insecure", "short"))
    assert "SANDBOX" in w and "https://" in w and "24 characters" in w
    assert daraja_warnings("production", "production", "key", "https://farm.example.com/cb", SECRET) == []

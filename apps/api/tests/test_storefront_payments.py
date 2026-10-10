"""Customer-facing M-Pesa payment: available methods, phone normalisation, retry."""
import pytest

from app.core.config import get_settings
from app.modules.payments.providers.base import InitiateResult
from test_guest_checkout import _setup_listing

pytestmark = pytest.mark.asyncio
settings = get_settings()

DARAJA = {
    "DARAJA_CONSUMER_KEY": "k", "DARAJA_CONSUMER_SECRET": "s", "DARAJA_SHORTCODE": "174379",
    "DARAJA_PASSKEY": "p", "DARAJA_CALLBACK_URL": "https://example.test/cb", "DARAJA_CALLBACK_SHARED_SECRET": "z",
}


class RecordingMpesa:
    """Stands in for Daraja: records the number it was asked to charge."""
    def __init__(self):
        self.phones: list[str] = []

    async def initiate_payment(self, amount, currency, reference, phone_or_token):
        self.phones.append(phone_or_token)
        return InitiateResult(provider_reference=f"ws_CO_{len(self.phones)}", status="pending", raw_response={"ok": True})


@pytest.fixture
def mpesa(monkeypatch):
    provider = RecordingMpesa()
    import app.modules.payments.service as payment_service
    monkeypatch.setattr(payment_service, "get_provider", lambda name: provider)
    return provider


async def _guest_order(client, org: str, email: str):
    _, org_slug, _, slug = await _setup_listing(client, org, email)
    guest = f"guest-{email}"
    order = await client.post(f"/api/v1/public/{org_slug}/orders", json={
        "customer_name": "Jane", "customer_email": guest, "items": [{"listing_slug": slug}],
    })
    return org_slug, order.json()["order_id"], guest


async def test_no_online_methods_are_offered_until_mpesa_is_configured(client):
    assert (await client.get("/api/v1/public/payment-methods")).json() == {"methods": []}


async def test_mpesa_is_offered_once_every_daraja_setting_is_present(client, monkeypatch):
    for key, value in DARAJA.items():
        monkeypatch.setattr(settings, key, value)
    assert (await client.get("/api/v1/public/payment-methods")).json() == {
        "methods": [{"provider": "mpesa", "label": "M-Pesa", "input": "phone"}]
    }
    monkeypatch.setattr(settings, "DARAJA_PASSKEY", "")        # half-configured -> hidden
    assert (await client.get("/api/v1/public/payment-methods")).json() == {"methods": []}


async def test_the_mock_provider_is_never_offered_to_customers(client, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_MOCK_PAYMENTS", True)  # even where mock is enabled (development)
    assert all(m["provider"] != "mock" for m in (await client.get("/api/v1/public/payment-methods")).json()["methods"])


async def test_guest_can_pay_with_a_number_typed_the_way_people_type_it(client, mpesa):
    org_slug, order_id, email = await _guest_order(client, "Pay Farm A", "pay1@example.com")
    resp = await client.post(f"/api/v1/public/{org_slug}/orders/{order_id}/pay/mpesa", json={"phone_or_token": "0712 345 678", "email": email})
    assert resp.status_code == 201, resp.text
    assert mpesa.phones == ["254712345678"]                       # Daraja got the format it requires
    order = (await client.get(f"/api/v1/public/{org_slug}/orders/{order_id}", params={"email": email})).json()
    assert order["status"] == "payment_pending"


async def test_an_invalid_phone_is_a_clear_422_and_never_reaches_the_provider(client, mpesa):
    org_slug, order_id, email = await _guest_order(client, "Pay Farm B", "pay2@example.com")
    resp = await client.post(f"/api/v1/public/{org_slug}/orders/{order_id}/pay/mpesa", json={"phone_or_token": "12345", "email": email})
    assert resp.status_code == 422 and "valid Kenyan mobile number" in resp.json()["detail"]
    assert mpesa.phones == []
    order = (await client.get(f"/api/v1/public/{org_slug}/orders/{order_id}", params={"email": email})).json()
    assert order["status"] == "pending"                           # nothing half-started


async def test_a_customer_can_retry_after_a_cancelled_prompt(client, mpesa):
    org_slug, order_id, email = await _guest_order(client, "Pay Farm C", "pay3@example.com")
    url = f"/api/v1/public/{org_slug}/orders/{order_id}/pay/mpesa"
    assert (await client.post(url, json={"phone_or_token": "0712345678", "email": email})).status_code == 201
    assert (await client.post(url, json={"phone_or_token": "0712345678", "email": email})).status_code == 201   # order is still payment_pending
    assert len(mpesa.phones) == 2


async def test_someone_elses_email_cannot_start_a_payment(client, mpesa):
    org_slug, order_id, _ = await _guest_order(client, "Pay Farm D", "pay4@example.com")
    resp = await client.post(f"/api/v1/public/{org_slug}/orders/{order_id}/pay/mpesa", json={"phone_or_token": "0712345678", "email": "stranger@example.com"})
    assert resp.status_code in (403, 404) and mpesa.phones == []

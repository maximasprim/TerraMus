"""Public contact form -> staff inbox."""
import pytest

pytestmark = pytest.mark.asyncio


async def _org(client, name: str, email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": name, "full_name": "Owner", "email": email, "password": "supersecret123",
    })
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    slug = (await client.get("/api/v1/auth/me", headers=headers)).json()["organization"]["slug"]
    return headers, slug


def _msg(**over):
    body = {"name": "Wanjiru", "email": "wanjiru@example.com", "message": "Do you deliver to Nakuru?"}
    body.update(over)
    return body


async def test_visitor_message_lands_in_staff_inbox_without_any_login(client):
    headers, slug = await _org(client, "Inbox Farm A", "inq1@example.com")
    resp = await client.post(f"/api/v1/public/{slug}/contact", json=_msg(phone="0712345678", listing_slug="holstein-cow"))
    assert resp.status_code == 201 and resp.json() == {"received": True}

    inbox = (await client.get("/api/v1/inquiries", headers=headers)).json()
    assert len(inbox) == 1
    assert inbox[0]["name"] == "Wanjiru" and inbox[0]["status"] == "new" and inbox[0]["listing_slug"] == "holstein-cow"
    assert (await client.get("/api/v1/inquiries/summary", headers=headers)).json() == {"new": 1, "read": 0, "replied": 0, "archived": 0}


async def test_staff_are_notified_of_a_new_enquiry(client):
    headers, slug = await _org(client, "Inbox Farm B", "inq2@example.com")
    await client.post(f"/api/v1/public/{slug}/contact", json=_msg(name="Otieno"))
    notes = (await client.get("/api/v1/notifications", headers=headers)).json()
    assert any(n["category"] == "orders" and "New enquiry from Otieno" in n["title"] for n in notes)


async def test_a_way_to_reply_is_required_and_message_must_be_real(client):
    _, slug = await _org(client, "Inbox Farm C", "inq3@example.com")
    no_contact = await client.post(f"/api/v1/public/{slug}/contact", json={"name": "A", "message": "Hello there farm"})
    assert no_contact.status_code == 422
    phone_only = await client.post(f"/api/v1/public/{slug}/contact", json={"name": "A", "phone": "0700000000", "message": "Hello there farm"})
    assert phone_only.status_code == 201
    too_short = await client.post(f"/api/v1/public/{slug}/contact", json=_msg(message="hi"))
    assert too_short.status_code == 422
    bad_email = await client.post(f"/api/v1/public/{slug}/contact", json=_msg(email="not-an-email"))
    assert bad_email.status_code == 422


async def test_honeypot_submissions_look_successful_but_are_discarded(client):
    headers, slug = await _org(client, "Inbox Farm D", "inq4@example.com")
    resp = await client.post(f"/api/v1/public/{slug}/contact", json=_msg(website="http://spam.example"))
    assert resp.status_code == 201  # the bot learns nothing
    assert (await client.get("/api/v1/inquiries", headers=headers)).json() == []


async def test_contact_form_is_rate_limited_per_client(client):
    _, slug = await _org(client, "Inbox Farm E", "inq5@example.com")
    codes = [(await client.post(f"/api/v1/public/{slug}/contact", json=_msg())).status_code for _ in range(8)]
    assert codes[:6] == [201] * 6 and 429 in codes[6:]


async def test_unknown_farm_is_a_404(client):
    resp = await client.post("/api/v1/public/no-such-farm/contact", json=_msg())
    assert resp.status_code == 404


async def test_status_workflow_and_filter(client):
    headers, slug = await _org(client, "Inbox Farm F", "inq6@example.com")
    await client.post(f"/api/v1/public/{slug}/contact", json=_msg())
    inquiry_id = (await client.get("/api/v1/inquiries", headers=headers)).json()[0]["id"]

    for new_status in ("read", "replied", "archived"):
        r = await client.patch(f"/api/v1/inquiries/{inquiry_id}", headers=headers, json={"status": new_status})
        assert r.status_code == 200 and r.json()["status"] == new_status
    assert (await client.get("/api/v1/inquiries?status=archived", headers=headers)).json()[0]["id"] == inquiry_id
    assert (await client.get("/api/v1/inquiries?status=new", headers=headers)).json() == []
    assert (await client.patch(f"/api/v1/inquiries/{inquiry_id}", headers=headers, json={"status": "bogus"})).status_code == 422


async def test_inbox_requires_auth_and_is_tenant_isolated(client):
    headers_a, slug_a = await _org(client, "Inbox Farm G", "inq7@example.com")
    headers_b, _ = await _org(client, "Inbox Farm H", "inq8@example.com")
    await client.post(f"/api/v1/public/{slug_a}/contact", json=_msg())
    inquiry_id = (await client.get("/api/v1/inquiries", headers=headers_a)).json()[0]["id"]

    assert (await client.get("/api/v1/inquiries")).status_code == 401
    assert (await client.get("/api/v1/inquiries", headers=headers_b)).json() == []
    assert (await client.patch(f"/api/v1/inquiries/{inquiry_id}", headers=headers_b, json={"status": "read"})).status_code == 404

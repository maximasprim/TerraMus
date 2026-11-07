"""A broken mail server must not turn a password-reset request into a 500 (it would also leak which emails exist)."""
import pytest
from unittest.mock import patch

from tests.test_platform_admin import _register_org

pytestmark = pytest.mark.asyncio


async def test_reset_request_survives_a_failing_mail_server(client, engine):
    await _register_org(client, "Mail Fail Farm", "mailfail@example.com")
    with patch("app.modules.notifications.service.send_email", side_effect=OSError("smtp down")):
        known = await client.post("/api/v1/auth/password-reset/request", json={"email": "mailfail@example.com"})
        unknown = await client.post("/api/v1/auth/password-reset/request", json={"email": "nobody@example.com"})
    assert known.status_code == 200 and unknown.status_code == 200
    assert known.json() == unknown.json()

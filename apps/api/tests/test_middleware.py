import pytest

pytestmark = pytest.mark.asyncio


async def test_request_id_header_present(client):
    resp = await client.get("/health")
    assert "x-request-id" in resp.headers


async def test_request_id_echoed_back_when_provided(client):
    resp = await client.get("/health", headers={"X-Request-ID": "test-trace-123"})
    assert resp.headers["x-request-id"] == "test-trace-123"


async def test_security_headers_present(client):
    resp = await client.get("/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"


async def test_readiness_probe_reports_db_ok(client):
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


async def test_login_rate_limit_triggers_after_threshold(client):
    """Confirms the limiter actually blocks, not just that it's wired in.
    Uses a wrong password so each attempt is fast and doesn't require a real
    account - the limiter fires on the request itself, before auth logic."""
    responses = []
    for _ in range(12):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "nobody@example.com", "password": "wrong",
        })
        responses.append(resp.status_code)

    assert 429 in responses
    # The first several should be normal auth failures (401), not rate-limited.
    assert responses[0] == 401

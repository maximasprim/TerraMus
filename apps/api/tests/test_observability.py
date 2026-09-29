import pytest

pytestmark = pytest.mark.asyncio


async def test_metrics_endpoint_exposes_prometheus_format(client):
    """Spec §47. Requires prometheus-client (added to requirements.txt this
    session) - unlike reportlab/qrcode/opentelemetry (only imported inside
    the specific handlers that use them), prometheus-client backs
    PrometheusMiddleware, which wraps every single request; if it isn't
    installed, the whole app fails to start, not just this one test. See
    docs/architecture.md's Phase 24 note."""
    resp = await client.get("/health")  # generate at least one request to count
    assert resp.status_code == 200

    metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    assert "http_requests_total" in metrics.text
    assert "http_request_duration_seconds" in metrics.text


async def test_metrics_not_exposed_in_openapi_schema(client):
    """include_in_schema=False - /metrics is operational, not part of the
    public API surface developers integrate against."""
    schema = await client.get("/openapi.json")
    assert "/metrics" not in schema.json()["paths"]

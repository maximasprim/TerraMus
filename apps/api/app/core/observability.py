"""Spec §47: 'Implement structured logging, request IDs, correlation IDs,
service health endpoints, metrics, error tracking, performance monitoring.
Prepare for: Prometheus, Grafana, OpenTelemetry.'

Structured logging, request IDs, and health/readiness endpoints already
existed before this session (see core/middleware.py's RequestContextMiddleware
and main.py's /health, /health/ready). This module adds the two pieces spec
§47 explicitly names that didn't exist yet: a real /metrics endpoint
Prometheus can scrape, and optional OpenTelemetry tracing.

New dependencies: prometheus-client, opentelemetry-api/-sdk/
-instrumentation-fastapi/-exporter-otlp-proto-http (all added to
requirements.txt this session). Not installable/testable in this sandbox
(no network) - the by-now-familiar "written and reviewed, not executed"
caveat this codebase already applies to reportlab/qrcode/the payment
providers/the Dockerfile.

Design principle, matching spec §54's own stance on AI features ("Do not
make AI mandatory for V1... Build reliable data collection first"): none of
this is mandatory for the app to boot. /metrics works with zero
configuration (prometheus-client's default registry). OpenTelemetry tracing
activates only if OTEL_EXPORTER_OTLP_ENDPOINT is set - an app with no
collector running anywhere still starts up and runs completely normally
with tracing simply inactive, not erroring or blocking on a collector that
doesn't exist.
"""
import time

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import get_settings


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Request counter + latency histogram, labeled by method/route-template/
    status. Uses the route *template* (e.g. "/api/v1/livestock/{animal_id}"),
    not the raw path, as the label value - using raw paths would create a
    new Prometheus time series per unique animal/order/etc. ID ever
    requested, which grows unboundedly and is the single most common
    Prometheus cardinality mistake."""

    def __init__(self, app):
        super().__init__(app)
        from prometheus_client import Counter, Histogram
        self.request_count = Counter(
            "http_requests_total", "Total HTTP requests", ["method", "route", "status"],
        )
        self.request_latency = Histogram(
            "http_request_duration_seconds", "HTTP request latency", ["method", "route"],
        )

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        route = request.scope.get("route")
        route_template = route.path if route is not None else request.url.path
        self.request_count.labels(request.method, route_template, response.status_code).inc()
        self.request_latency.labels(request.method, route_template).observe(duration)
        return response


def register_metrics_endpoint(app: FastAPI) -> None:
    @app.get("/metrics", tags=["system"], include_in_schema=False)
    async def metrics():
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def setup_tracing(app: FastAPI) -> None:
    """No-op unless OTEL_EXPORTER_OTLP_ENDPOINT is configured - see module
    docstring. Imports are local to this function so a deployment that never
    sets that variable pays no import cost for packages it isn't using
    (mirrors the lazy-import pattern core/middleware.py's RedisRateLimiter
    already uses for the same reason: don't require a dependency to be
    reachable, or even importable, for a code path nobody enabled)."""
    settings = get_settings()
    if not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        return

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    resource = Resource.create({"service.name": settings.APP_NAME})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)

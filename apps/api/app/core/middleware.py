"""Spec §29 (Security) / §47 (Observability) - cross-cutting middleware
applied to every request, not per-router opt-in, so nothing can accidentally
skip it."""
import logging
import time
import uuid
from collections import defaultdict, deque

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("app.requests")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Spec §47 - structured logging with request/correlation IDs. Accepts an
    inbound X-Request-ID (so a frontend or gateway can propagate its own
    trace id) or generates one; always returns it in the response header so
    a client can correlate a support ticket with a specific log line."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.monotonic()

        response = await call_next(request)

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request.completed",
            extra={
                "request_id": request_id, "method": request.method, "path": request.url.path,
                "status_code": response.status_code, "duration_ms": duration_ms,
            },
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Spec §29 - secure headers. Deliberately conservative defaults; a real
    deployment behind a CDN/WAF may set some of these there instead, but
    having them at the app layer means they're correct even without one."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # No HSTS here - this app doesn't terminate TLS itself; a real
        # deployment's reverse proxy/load balancer is the right place for it,
        # and setting it here would be misleading about what's actually true.
        return response


class RateLimiter:
    """Spec §29 - rate limiting / API throttling. In-memory sliding-window
    limiter, keyed by client IP + route. This is the default backend
    (settings.RATE_LIMIT_BACKEND == "memory") - correct for a single
    instance, genuinely testable with no external dependency, and what every
    existing test in this suite runs against. See RedisRateLimiter below for
    the multi-replica case."""

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    async def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()
        if len(hits) >= self.max_requests:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests - please slow down")
        hits.append(now)


class RedisRateLimiter:
    """Shared-store rate limiter for when there's more than one API replica
    - the gap this codebase has documented since Phase 8 ("needs a
    Redis-backed limiter... before horizontal scaling"). Fixed-window
    counter via a single atomic INCR per request, not a sliding log: a
    request bucketed to `int(time.time() // window_seconds)`, expiring the
    key after one window. This allows up to ~2x max_requests across a
    window boundary (a known, accepted trade-off of fixed windows vs. a
    sliding log) in exchange for needing exactly one round-trip per check
    instead of a sorted-set + Lua script - reasonable for a brute-force
    throttle, not a strict billing quota.

    The redis client is created lazily (not at import time) so importing
    this module never requires Redis to be reachable - only actually
    calling `.check()` with RATE_LIMIT_BACKEND=redis does."""

    def __init__(self, max_requests: int, window_seconds: int, redis_url: str):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._redis_url = redis_url
        self._client = None

    def _client_or_create(self):
        if self._client is None:
            import redis.asyncio as redis_asyncio  # local import: keep this module importable with no redis package reachable
            self._client = redis_asyncio.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def check(self, key: str) -> None:
        client = self._client_or_create()
        bucket = int(time.time() // self.window_seconds)
        redis_key = f"ratelimit:{key}:{bucket}"
        count = await client.incr(redis_key)
        if count == 1:
            await client.expire(redis_key, self.window_seconds)
        if count > self.max_requests:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests - please slow down")


# Stricter limit on auth endpoints specifically (spec §29's implicit concern:
# brute-force login/registration abuse), looser default elsewhere.
# `auth_rate_limiter` is kept as this exact name/object because
# tests/conftest.py resets it directly (`auth_rate_limiter._hits.clear()`)
# between tests - renaming or removing it would break that isolation fixture
# for every existing test, not just rate-limiting ones.
auth_rate_limiter = RateLimiter(max_requests=10, window_seconds=60)
_redis_auth_limiter: RedisRateLimiter | None = None


def _get_auth_limiter():
    from app.core.config import get_settings
    settings = get_settings()
    if settings.RATE_LIMIT_BACKEND == "redis":
        global _redis_auth_limiter
        if _redis_auth_limiter is None:
            _redis_auth_limiter = RedisRateLimiter(max_requests=10, window_seconds=60, redis_url=settings.REDIS_URL)
        return _redis_auth_limiter
    return auth_rate_limiter


async def rate_limit_auth(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    await _get_auth_limiter().check(f"auth:{client_ip}")

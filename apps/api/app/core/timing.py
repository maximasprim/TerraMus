"""Per-request timing: how long each API call took, how many SQL statements it ran and how long the database
part took. One log line per request (WARNING when slower than REQUEST_SLOW_MS, default 1000 ms) plus a standard
`Server-Timing` response header, so the browser's Network tab shows "app" and "db" times for every call.

Why: a screen that feels slow is usually a few calls doing many round trips to a distant database, and the fix
differs per call. This tells you which calls, and whether the time is the database or the code.

Switch off with REQUEST_TIMING=false. Pure observation: it never changes a request or a response body.
"""
from __future__ import annotations

import contextvars
import logging
import os
import time

from sqlalchemy import event
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

log = logging.getLogger("app.timing")
ENABLED = os.getenv("REQUEST_TIMING", "true").strip().lower() not in ("0", "false", "no", "off")
SLOW_MS = int(os.getenv("REQUEST_SLOW_MS", "1000") or 1000)


class _Stats:
    __slots__ = ("queries", "db_seconds")

    def __init__(self) -> None:
        self.queries = 0
        self.db_seconds = 0.0


_current: contextvars.ContextVar[_Stats | None] = contextvars.ContextVar("request_sql_stats", default=None)


def install_sql_timing(engine) -> None:
    """Count and time every statement the engine executes on behalf of the current request."""
    sync_engine = getattr(engine, "sync_engine", engine)

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):      # noqa: ANN001
        if context is not None and _current.get() is not None:
            context._request_t0 = time.perf_counter()

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):       # noqa: ANN001
        stats = _current.get()
        t0 = getattr(context, "_request_t0", None) if context is not None else None
        if stats is not None and t0 is not None:
            stats.queries += 1
            stats.db_seconds += time.perf_counter() - t0


class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not ENABLED:
            return await call_next(request)
        stats = _Stats()
        token = _current.set(stats)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            _current.reset(token)
        total_ms = (time.perf_counter() - started) * 1000
        db_ms = stats.db_seconds * 1000
        route = request.scope.get("route")
        path = route.path if route is not None else request.url.path          # the template, so ids don't clutter the log
        log.log(logging.WARNING if total_ms >= SLOW_MS else logging.INFO,
                "%s %s -> %s %dms (db %dms, %d queries)", request.method, path, response.status_code,
                total_ms, db_ms, stats.queries)
        response.headers["Server-Timing"] = f"app;dur={total_ms:.0f}, db;dur={db_ms:.0f}"
        return response
import os
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.main import app
from app.core import database as db_module

API_ROOT = Path(__file__).resolve().parents[1]

# Async URL for the app's own engine/session (asyncpg driver).
TEST_DATABASE_URL_ASYNC = "postgresql+asyncpg://farm:farm@localhost:5432/farmdb_test"
# Sync URL for Alembic (psycopg driver) - migrations run synchronously.
TEST_DATABASE_URL_SYNC = "postgresql+psycopg://farm:farm@localhost:5432/farmdb_test"


def _run_alembic(command: str) -> None:
    """Runs real Alembic migrations against the test database rather than
    Base.metadata.create_all(). This matters: several correctness guarantees
    (append-only triggers, partial unique indexes like 'only one active
    listing/reservation per animal') are expressed as raw SQL inside the
    migrations themselves, not as SQLAlchemy ORM/Column constructs - so
    create_all() would silently produce a schema missing those guarantees,
    and tests would pass without ever exercising them.

    Uses `sys.executable -m alembic` (the same interpreter running pytest)
    rather than a bare `alembic` command, so it works regardless of whether
    the venv's bin/ directory is on PATH in the subprocess environment."""
    env = os.environ.copy()
    env["DATABASE_URL"] = TEST_DATABASE_URL_SYNC
    target = "head" if command == "upgrade" else "base"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", command, target],
        cwd=str(API_ROOT), env=env, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic {command} failed:\n{result.stdout}\n{result.stderr}")


@pytest_asyncio.fixture
async def engine():
    _run_alembic("downgrade")  # start from a clean base each test
    _run_alembic("upgrade")
    eng = create_async_engine(TEST_DATABASE_URL_ASYNC)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def client(engine):
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[db_module.get_db] = override_get_db

    # Fire-and-forget event handlers (e.g. finance/handlers.py) don't go through
    # FastAPI's dependency injection - they open their own session via the
    # module-level `db_module.AsyncSessionLocal`, which was created once at
    # import time bound to whatever event loop existed then. Under pytest-asyncio,
    # each test gets its own event loop, so that stale global engine belongs to a
    # *different* loop than the current test - asyncpg then raises "attached to a
    # different loop". In production this never manifests (one loop for the
    # app's lifetime), so this is a test-only fixup: point the global session
    # factory at this test's own loop-bound engine for the duration of the test,
    # then restore it so tests stay isolated from each other.
    original_session_local = db_module.AsyncSessionLocal
    db_module.AsyncSessionLocal = SessionLocal

    # Same isolation concern as the session-factory swap above, for a
    # different reason: the in-memory rate limiter (core/middleware.py) is
    # module-level state on the shared `app` object, which persists across
    # the *entire* pytest session (the FastAPI app is imported once, not
    # recreated per test). Without resetting it, tests later in the run start
    # getting 429'd by hit counts accumulated from unrelated earlier tests'
    # register()/login() calls - found by actually running the full suite
    # after adding the rate limiter, not just the isolated middleware tests.
    from app.core.middleware import auth_rate_limiter
    auth_rate_limiter._hits.clear()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    db_module.AsyncSessionLocal = original_session_local
    app.dependency_overrides.clear()

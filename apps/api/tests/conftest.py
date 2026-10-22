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


_TEMPLATE_DB = "farmdb_test_template"
_template_ready = False


def _admin_conn():
    import psycopg
    return psycopg.connect("postgresql://farm:farm@localhost:5432/postgres", autocommit=True)


def _ensure_template() -> None:
    """FAST HARNESS: run the real Alembic chain ONCE into a template database,
    then clone it per test (CREATE DATABASE ... TEMPLATE) instead of
    downgrade+upgrade through every migration on every test. Same isolation,
    same real-migration schema (triggers and partial indexes included)."""
    global _template_ready
    if _template_ready:
        return
    with _admin_conn() as c:
        c.execute(f"DROP DATABASE IF EXISTS {_TEMPLATE_DB} WITH (FORCE)")
        c.execute(f"CREATE DATABASE {_TEMPLATE_DB}")
    env = os.environ.copy()
    env["DATABASE_URL"] = f"postgresql+psycopg://farm:farm@localhost:5432/{_TEMPLATE_DB}"
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       cwd=str(API_ROOT), env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"alembic upgrade failed:\n{r.stdout}\n{r.stderr}")
    _template_ready = True


def _clone_template() -> None:
    with _admin_conn() as c:
        c.execute("DROP DATABASE IF EXISTS farmdb_test WITH (FORCE)")
        c.execute(f"CREATE DATABASE farmdb_test TEMPLATE {_TEMPLATE_DB}")


@pytest_asyncio.fixture
async def engine():
    """Fresh, fully-migrated database per test.

    Default (fast, ~1s/test): migrate once into a template database, then clone it per test.
    Needs a database user allowed to CREATE DATABASE (the project's `farm` user is a superuser).
    Set TEST_FULL_MIGRATIONS=1 to use the original method instead (downgrade to base + upgrade to
    head before EVERY test, ~10s/test) - the same schema, just slower; it also exercises the
    downgrade path of every migration."""
    if os.environ.get("TEST_FULL_MIGRATIONS") == "1":
        _run_alembic("downgrade")
        _run_alembic("upgrade")
    else:
        _ensure_template()
        _clone_template()
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
    from app.core.middleware import auth_rate_limiter, reset_public_limiters
    auth_rate_limiter._hits.clear()
    # Same reasoning for the public-write limiters (guest checkout / contact
    # form / guest payment): without this, order POSTs from unrelated earlier
    # tests would accumulate against the per-IP limit and 429 later tests.
    reset_public_limiters()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    db_module.AsyncSessionLocal = original_session_local
    app.dependency_overrides.clear()

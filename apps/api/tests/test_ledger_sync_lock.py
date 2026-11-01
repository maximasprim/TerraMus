"""Finance catch-up sync: never two at once, and it commits in chunks."""
import pytest
from sqlalchemy import text

from app.modules.feedlot import ledger_sync
from tests.test_feedlot_import import FIXTURE, H, _org

pytestmark = pytest.mark.asyncio
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _import_without_finance(client, h):
    with open(FIXTURE, "rb") as f:
        r = await client.post("/api/v1/feedlot/worksheet/import?dry_run=false&post_to_finance=false", headers=h,
                              files={"file": (FIXTURE.name, f, XLSX)})
    assert r.json()["ok"]


async def test_second_sync_is_refused_while_one_is_running(client, engine):
    h = await _org(client, engine, name="Lock Farm", email="lock@example.com")
    await _import_without_finance(client, h)
    async with engine.connect() as c:
        org_id = (await c.execute(text("SELECT id FROM organizations ORDER BY created_at DESC LIMIT 1"))).scalar_one()
    async with engine.connect() as other:                      # pretend another sync holds this organisation's lock
        await other.execute(text("SELECT pg_advisory_lock(:ns, :k)"), {"ns": ledger_sync._LOCK_NAMESPACE, "k": org_id.int % 2147483647})
        blocked = await client.post("/api/v1/feedlot/ledger-sync?dry_run=false&confirm_overlap=true", headers=h)
        assert blocked.status_code == 409 and "already running" in blocked.json()["detail"]
        assert (await client.post("/api/v1/feedlot/ledger-sync", headers=h)).status_code == 200        # a preview is never blocked
        await other.execute(text("SELECT pg_advisory_unlock(:ns, :k)"), {"ns": ledger_sync._LOCK_NAMESPACE, "k": org_id.int % 2147483647})
    ok = await client.post("/api/v1/feedlot/ledger-sync?dry_run=false&confirm_overlap=true", headers=h)
    assert ok.status_code == 200


async def test_chunked_sync_posts_everything_once(client, engine, monkeypatch):
    monkeypatch.setattr(ledger_sync, "CHUNK", 7)                # many commits inside one run
    h = await _org(client, engine, name="Chunk Farm", email="chunk@example.com")
    await _import_without_finance(client, h)
    first = (await client.post("/api/v1/feedlot/ledger-sync?dry_run=false&confirm_overlap=true", headers=h)).json()
    assert first["sales"]["posted"] > 7 and first["purchases"]["posted"] > 7
    again = (await client.post("/api/v1/feedlot/ledger-sync", headers=h)).json()
    assert again["sales"]["missing"] == 0 and again["purchases"]["missing"] == 0
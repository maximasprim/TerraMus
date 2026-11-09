"""Automatic import of the Google Sheet: link checks, import through the shared importer, skip-when-unchanged, failures."""
import pathlib

import pytest

from app.modules.feedlot import worksheet_sync
from app.modules.notifications.scheduled import run_scheduled_checks
from tests.test_feedlot_export import _org

pytestmark = pytest.mark.asyncio
FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sahara_oasis_bulls_wg_sample.xlsx"
SHEET = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit#gid=0"


def test_only_google_links_are_accepted_and_turned_into_export_links():
    assert worksheet_sync.export_url(SHEET) == "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/export?format=xlsx"
    assert "uc?export=download&id=" in worksheet_sync.export_url("https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/view")
    for bad in ("", "http://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "https://evil.example.com/x.xlsx",
                "https://docs.google.com.evil.example/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"):
        with pytest.raises(worksheet_sync.SyncError):
            worksheet_sync.export_url(bad)


async def test_sync_imports_then_skips_an_unchanged_sheet_and_reports_failures(client, engine, monkeypatch):
    h = await _org(client, engine, "sync1@example.com")
    cyc = (await client.post("/api/v1/production-cycles", json={"name": "Cycle 1"}, headers=h)).json()["id"]
    calls = {"n": 0}
    content = FIXTURE.read_bytes()

    async def fake_fetch(url):
        calls["n"] += 1
        if calls["n"] == 4:
            raise worksheet_sync.SyncError("Google would not let the system read the sheet.")
        return content
    monkeypatch.setattr(worksheet_sync, "fetch_workbook", fake_fetch)

    assert (await client.get("/api/v1/feedlot/worksheet/sync", headers=h)).json()["configured"] is False
    bad = await client.put("/api/v1/feedlot/worksheet/sync", headers=h, json={"sheet_url": "https://evil.example.com/a", "enabled": True})
    assert bad.status_code == 422
    need_cycle = await client.put("/api/v1/feedlot/worksheet/sync", headers=h, json={"sheet_url": SHEET, "enabled": True})
    assert need_cycle.status_code == 422 and "production cycle" in need_cycle.json()["detail"]
    ok = await client.put("/api/v1/feedlot/worksheet/sync", headers=h, json={"sheet_url": SHEET, "enabled": True, "production_cycle_id": cyc})
    assert ok.status_code == 200 and ok.json()["enabled"] is True

    preview = (await client.post("/api/v1/feedlot/worksheet/sync/run?dry_run=true", headers=h)).json()
    assert preview["status"] == "ok" and preview["dry_run"] is True
    assert (await client.get("/api/v1/feedlot/intake-batches", headers=h)).json() == []          # a preview saves nothing

    first = (await client.post("/api/v1/feedlot/worksheet/sync/run", headers=h)).json()
    assert first["status"] == "ok" and sum(first["report"]["created"].values()) > 0
    assert len((await client.get("/api/v1/feedlot/intake-batches", headers=h)).json()) > 0
    again = (await client.post("/api/v1/feedlot/worksheet/sync/run", headers=h)).json()          # same bytes as the import
    assert again["status"] == "unchanged"
    failed = (await client.post("/api/v1/feedlot/worksheet/sync/run?force=true", headers=h)).json()   # Google refuses
    assert failed["status"] == "failed" and "Google" in failed["message"]
    cfg = (await client.get("/api/v1/feedlot/worksheet/sync", headers=h)).json()
    assert cfg["last_status"] == "failed" and cfg["last_run_at"]


async def test_daily_check_runs_the_sync_and_alerts_once_when_it_fails(client, engine, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker
    h = await _org(client, engine, "sync2@example.com")
    cyc = (await client.post("/api/v1/production-cycles", json={"name": "Cycle 1"}, headers=h)).json()["id"]

    async def refuse(url):
        raise worksheet_sync.SyncError("The sheet is not shared.")
    monkeypatch.setattr(worksheet_sync, "fetch_workbook", refuse)
    await client.put("/api/v1/feedlot/worksheet/sync", headers=h, json={"sheet_url": SHEET, "enabled": True, "production_cycle_id": cyc})
    async with engine.begin() as c:
        org_id = (await c.execute(text("SELECT organization_id FROM worksheet_syncs"))).scalar_one()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        r = await run_scheduled_checks(db, org_id)
    assert r.worksheet_sync_failed == 1
    notes = (await client.get("/api/v1/notifications", headers=h)).json()
    assert [n["title"] for n in notes].count("Google Sheet import failed") == 1
    async with factory() as db:
        await run_scheduled_checks(db, org_id)                                                    # same day: no second alert
    notes = (await client.get("/api/v1/notifications", headers=h)).json()
    assert [n["title"] for n in notes].count("Google Sheet import failed") == 1


async def test_switched_off_sync_does_nothing(client, engine, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    h = await _org(client, engine, "sync3@example.com")
    async def boom(url):
        raise AssertionError("must not be called")
    monkeypatch.setattr(worksheet_sync, "fetch_workbook", boom)
    me = (await client.get("/api/v1/auth/me", headers=h)).json()
    org_id = me.get("organization_id") or me["organization"]["id"]
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        r = await run_scheduled_checks(db, org_id)
    assert r.worksheet_sync_failed == 0

"""Automatic import of the farm's Google Sheet worksheet.

The sheet is downloaded as an .xlsx (Google's own export link, which works for a sheet shared as "Anyone with the
link can view") and handed to the SAME importer as the manual upload. That importer updates what changed and leaves
the rest alone, so running it every day is safe. A workbook that is byte-for-byte the one already imported is skipped.
"""
import hashlib
import re
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.feedlot.models import WorksheetSync

MAX_BYTES = 15 * 1024 * 1024
_SHEET = re.compile(r"^https://docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]{20,})")
_FILE = re.compile(r"^https://drive\.google\.com/(?:file/d/|open\?id=|uc\?(?:[^#]*&)?id=)([A-Za-z0-9_-]{20,})")


class SyncError(Exception):
    """Something the owner can fix (sheet not shared, wrong link, bad workbook). The message is shown to them."""


def export_url(sheet_url: str) -> str:
    """Google's download link for a Google Sheet or an Excel file stored in Drive. Only Google addresses are accepted."""
    u = (sheet_url or "").strip()
    if m := _SHEET.match(u):
        return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=xlsx"
    if m := _FILE.match(u):
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    raise SyncError("That is not a Google Sheets or Google Drive link. Paste the sheet's address, for example "
                    "https://docs.google.com/spreadsheets/d/…/edit")


async def fetch_workbook(sheet_url: str) -> bytes:
    url = export_url(sheet_url)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(60.0)) as c:
            async with c.stream("GET", url) as r:
                if r.status_code in (401, 403, 404):
                    raise SyncError("Google would not let the system read the sheet. Open the sheet, choose Share, and set "
                                    "General access to 'Anyone with the link' (Viewer), then try again.")
                if r.status_code != 200:
                    raise SyncError(f"Google answered {r.status_code} when downloading the sheet.")
                body = bytearray()
                async for chunk in r.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise SyncError("The sheet is larger than 15 MB.")
    except httpx.HTTPError as e:
        raise SyncError(f"Could not reach Google ({type(e).__name__}). It will be tried again next time.") from e
    data = bytes(body)
    if not data.startswith(b"PK"):          # an .xlsx is a zip; Google answers with an HTML sign-in page when the sheet is private
        raise SyncError("Google did not return a spreadsheet. The sheet is probably not shared: set General access to "
                        "'Anyone with the link' (Viewer).")
    return data


def _out(c: WorksheetSync | None) -> dict:
    if c is None:
        return {"sheet_url": "", "enabled": False, "production_cycle_id": None, "post_to_finance": True, "include_costing": True,
                "last_run_at": None, "last_status": None, "last_message": None, "last_report": None, "configured": False}
    return {"sheet_url": c.sheet_url, "enabled": c.enabled, "production_cycle_id": str(c.production_cycle_id) if c.production_cycle_id else None,
            "post_to_finance": c.post_to_finance, "include_costing": c.include_costing,
            "last_run_at": c.last_run_at.isoformat() if c.last_run_at else None, "last_status": c.last_status,
            "last_message": c.last_message, "last_report": c.last_report, "configured": True}


async def _row(db: AsyncSession, org_id: uuid.UUID) -> WorksheetSync | None:
    return (await db.execute(select(WorksheetSync).where(WorksheetSync.organization_id == org_id))).scalar_one_or_none()


async def get_config(db: AsyncSession, org_id: uuid.UUID) -> dict:
    return _out(await _row(db, org_id))


async def save_config(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, *, sheet_url: str, enabled: bool,
                      production_cycle_id: uuid.UUID | None, post_to_finance: bool, include_costing: bool) -> dict:
    sheet_url = (sheet_url or "").strip()
    if sheet_url:
        try:
            export_url(sheet_url)
        except SyncError as e:
            raise HTTPException(422, str(e))
    elif enabled:
        raise HTTPException(422, "Paste the Google Sheet link before switching automatic import on.")
    if enabled:
        from app.modules.cycles.deps import ensure_writable
        await ensure_writable(db, org_id, production_cycle_id)
        if production_cycle_id is None:
            from sqlalchemy import func
            from app.modules.cycles.models import ProductionCycle
            if (await db.execute(select(func.count()).select_from(ProductionCycle).where(ProductionCycle.organization_id == org_id))).scalar_one():
                raise HTTPException(422, "Choose the production cycle this worksheet belongs to. Batch numbers restart in every cycle.")
    c = await _row(db, org_id)
    if c is None:
        c = WorksheetSync(organization_id=org_id)
        db.add(c)
    if sheet_url != c.sheet_url:
        c.last_hash = None                  # a different sheet: import it even if it happens to look the same
    c.sheet_url, c.enabled, c.production_cycle_id = sheet_url, enabled, production_cycle_id
    c.post_to_finance, c.include_costing, c.configured_by = post_to_finance, include_costing, user_id
    await db.commit()
    return _out(c)


def _summary(report: dict) -> dict:
    return {"created": report.get("created", {}), "updated": report.get("updated", {}), "unchanged": report.get("unchanged", {}),
            "warnings": len(report.get("warnings", [])), "errors": [e.get("message") for e in report.get("errors", [])][:5]}


def _describe(report: dict) -> str:
    made, changed = sum(report["created"].values()), sum(report["updated"].values())
    return f"Imported: {made} added, {changed} updated, {sum(report['unchanged'].values())} unchanged." if report["ok"] else "The workbook was not imported."


async def run_sync(db: AsyncSession, org_id: uuid.UUID, *, dry_run: bool = False, force: bool = False) -> dict:
    """Download the sheet and import it. dry_run previews and records nothing. Returns {status, message, report}."""
    c = await _row(db, org_id)
    if c is None or not c.sheet_url:
        raise HTTPException(422, "Paste the Google Sheet link first.")
    from app.modules.feedlot.worksheet_import import import_worksheet
    status, message, report = "failed", "", None
    digest = None
    try:
        content = await fetch_workbook(c.sheet_url)
        digest = hashlib.sha256(content).hexdigest()
        if not dry_run and not force and c.last_hash == digest:
            status, message = "unchanged", "The sheet has not changed since the last import."
        else:
            if not c.configured_by:
                raise SyncError("Save the settings once so the system knows whose name the import is recorded under.")
            report = await import_worksheet(db, org_id, c.configured_by, content, dry_run=dry_run, include_costing=c.include_costing,
                                            post_to_finance=c.post_to_finance, production_cycle_id=c.production_cycle_id)
            if report["ok"]:
                status, message = "ok", _describe(report)
            else:
                message = "; ".join(e.get("message", "") for e in report["errors"][:3]) or "The workbook could not be imported."
    except SyncError as e:
        message = str(e)
    except HTTPException as e:
        message = str(e.detail)
    if dry_run:
        return {"status": status, "message": message, "report": report, "dry_run": True}
    c = await _row(db, org_id)
    c.last_run_at, c.last_status, c.last_message = datetime.now(timezone.utc), status, message[:1000]
    if status == "ok":
        c.last_hash = digest
    if report is not None:
        c.last_report = _summary(report)
    await db.commit()
    return {"status": status, "message": message, "report": report, "dry_run": False}

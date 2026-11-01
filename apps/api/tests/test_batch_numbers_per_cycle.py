"""Batch numbers restart in every production cycle; importing cycle 2 must never touch cycle 1."""
import pathlib

import pytest
from sqlalchemy import text

from tests.test_feedlot_import import FIXTURE as CYCLE1, H, _org

pytestmark = pytest.mark.asyncio
CYCLE2 = pathlib.Path(__file__).parent / "fixtures" / "sahara_oasis_second_cycle.xlsx"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _import(client, h, path, dry_run, cycle_id=None):
    q = f"dry_run={'true' if dry_run else 'false'}" + (f"&production_cycle_id={cycle_id}" if cycle_id else "")
    with open(path, "rb") as f:
        return (await client.post(f"/api/v1/feedlot/worksheet/import?{q}", headers=h, files={"file": (path.name, f, XLSX)})).json()


async def test_second_cycle_import_keeps_cycle_one_untouched(client, engine):
    h = await _org(client, engine, name="Two Cycles", email="two@example.com")
    first = await _import(client, h, CYCLE1, False)                       # cycle 1, imported with no cycle (as today)
    assert first["ok"], first["errors"]
    before = (await client.get("/api/v1/feedlot/intake-batches", headers=h)).json()
    assert [b["batch_number"] for b in before] == [1, 2, 3, 4, 5]

    cyc = (await client.post("/api/v1/production-cycles", json={"name": "2nd Production Cycle", "status": "running"}, headers=h)).json()
    no_cycle = await _import(client, h, CYCLE2, True)                                # guard: once cycles exist an import must name one
    assert no_cycle.get("detail", "").startswith("Choose the production cycle")
    dry = await _import(client, h, CYCLE2, True, cyc["id"])
    assert dry["ok"] and dry["created"]["intake_batches"] == 6 and dry["created"]["animals"] == 112
    assert dry["created"].get("finance_purchases") == 112
    assert any(w["code"] == "batch_number_reused" for w in dry["warnings"])         # batch 1-5 exist unassigned, different dates
    assert len((await client.get("/api/v1/feedlot/intake-batches", headers=h)).json()) == 5     # dry run saved nothing

    real = await _import(client, h, CYCLE2, False, cyc["id"])
    assert real["ok"], real["errors"]
    again = await _import(client, h, CYCLE2, False, cyc["id"])                       # idempotent
    assert again["created"].get("animals", 0) == 0 and again["created"].get("intake_batches", 0) == 0

    c2 = (await client.get(f"/api/v1/feedlot/intake-batches?production_cycle_id={cyc['id']}", headers=h)).json()
    assert [b["batch_number"] for b in c2] == [1, 2, 3, 4, 5, 6] and sum(b["head_registered"] for b in c2) == 112
    assert round(sum(b["landed_cost"] for b in c2)) == 6738100
    unassigned = (await client.get("/api/v1/feedlot/intake-batches?production_cycle_id=unassigned", headers=h)).json()
    key = lambda rows: [(b["batch_number"], b["delivered_on"], b["head_registered"], b["landed_cost"]) for b in rows]
    assert key(unassigned) == key(before)                                             # cycle 1 exactly as it was


async def test_batch_number_unique_per_cycle_not_per_organisation(client, engine):
    h = await _org(client, engine, name="Numbering", email="num@example.com")
    c1 = (await client.post("/api/v1/production-cycles", json={"name": "A"}, headers=h)).json()["id"]
    c2 = (await client.post("/api/v1/production-cycles", json={"name": "B"}, headers=h)).json()["id"]
    body = lambda cyc, **kw: {"delivered_on": "2026-09-03", "production_cycle_id": cyc, **kw}
    r1 = await client.post("/api/v1/feedlot/intake-batches", json=body(c1, batch_number=1), headers=h)
    r2 = await client.post("/api/v1/feedlot/intake-batches", json=body(c2, batch_number=1), headers=h)
    assert r1.status_code == 201 and r2.status_code == 201
    assert (await client.post("/api/v1/feedlot/intake-batches", json=body(c2, batch_number=1), headers=h)).status_code == 409
    auto = await client.post("/api/v1/feedlot/intake-batches", json=body(c2), headers=h)       # auto number counts inside the cycle
    assert auto.json()["batch_number"] == 2
    # moving batch 1 of cycle B into cycle A (which already has a batch 1) is refused, not a 500
    moved = await client.patch(f"/api/v1/feedlot/intake-batches/{r2.json()['id']}", json={"production_cycle_id": c1}, headers=h)
    assert moved.status_code == 409
    # batches in no cycle keep the old org-wide rule
    assert (await client.post("/api/v1/feedlot/intake-batches", json={"delivered_on": "2026-01-01", "batch_number": 7}, headers=h)).status_code == 201
    assert (await client.post("/api/v1/feedlot/intake-batches", json={"delivered_on": "2026-01-02", "batch_number": 7}, headers=h)).status_code == 409

"""Request timing header, and the narrowed feedlot loader returns exactly what the unfiltered one would."""
import re

import pytest

from tests.test_feedlot_import import FIXTURE, H, _org, _post

pytestmark = pytest.mark.asyncio


async def test_every_response_carries_server_timing(client, engine):
    h = await _org(client, engine, name="Timing Farm", email="timing@example.com")
    r = await client.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 200
    assert re.fullmatch(r"app;dur=\d+, db;dur=\d+", r.headers["server-timing"])


async def test_performance_filters_in_sql_give_the_same_answer(client, engine):
    h = await _org(client, engine, name="Loader Farm", email="loader@example.com")
    assert (await _post(client, h, False)).json()["ok"]

    def view(rep):                                              # order is not part of the contract
        return sorted(rep["animals"], key=lambda a: a["tag"]), rep["summary"]

    full = (await client.get("/api/v1/feedlot/performance", headers=h)).json()
    assert full["summary"]["head"] > 20

    # a cycle filter ("unassigned": the worksheet was imported with no cycle)
    un = (await client.get("/api/v1/feedlot/performance?production_cycle_id=unassigned", headers=h)).json()
    assert view(un) == view(full)

    # an intake batch filter equals filtering the full answer by hand
    batches = (await client.get("/api/v1/feedlot/intake-batches", headers=h)).json()
    first = batches[0]["id"]
    one = (await client.get(f"/api/v1/feedlot/performance?intake_batch_id={first}", headers=h)).json()
    expected = [a for a in full["animals"] if a["intake_batch_id"] == first]
    assert sorted(a["tag"] for a in one["animals"]) == sorted(a["tag"] for a in expected) and expected

    # a sale batch filter likewise
    sales = (await client.get("/api/v1/feedlot/sale-batches", headers=h)).json()
    if sales:
        sid = sales[0]["id"]
        sold = (await client.get(f"/api/v1/feedlot/performance?sale_batch_id={sid}", headers=h)).json()
        want = [a for a in full["animals"] if a["sale_batch_id"] == sid]
        assert sorted(a["tag"] for a in sold["animals"]) == sorted(a["tag"] for a in want) and want

    # a batch / cycle that does not exist -> nothing, not an error
    none = (await client.get("/api/v1/feedlot/performance?intake_batch_id=00000000-0000-0000-0000-000000000001", headers=h)).json()
    assert none["summary"]["head"] == 0
"""Dashboard: feedlot herd value is estimated when no value is stated; the money cards follow the selected cycle."""
import pytest

from tests.test_feedlot_import import _org, _post

pytestmark = pytest.mark.asyncio


async def test_feedlot_herd_value_and_cycle_money_cards(client, engine):
    h = await _org(client, engine, name="Dash Farm", email="dash@example.com")
    assert (await _post(client, h, False)).json()["ok"]

    all_cycles = (await client.get("/api/v1/reports/dashboard", headers=h)).json()
    assert all_cycles["finance_period"] == "month"                      # no cycle selected: unchanged behaviour

    cyc = (await client.get("/api/v1/reports/dashboard?production_cycle_id=unassigned", headers=h)).json()
    assert cyc["finance_period"] == "cycle"
    assert float(cyc["monthly_revenue"]) > 0                            # the imported sales are counted, not just this month's

    # the Insights charts reach back to the cycle's first entry instead of stopping at the last 6 months
    six = (await client.get("/api/v1/reports/analytics?months=6&production_cycle_id=unassigned", headers=h)).json()
    fit = (await client.get("/api/v1/reports/analytics?months=6&fit_cycle=true&production_cycle_id=unassigned", headers=h)).json()
    assert six["months"] == 6 and fit["months"] >= 6
    assert float(fit["finance"]["total_expense"]) >= float(six["finance"]["total_expense"])
    plain = (await client.get("/api/v1/reports/analytics?months=6&fit_cycle=true", headers=h)).json()
    assert plain["months"] == 6                                         # no cycle selected: unchanged

    if cyc["active_animals"] > 0:                                       # unsold bulls are valued instead of showing 0
        assert float(cyc["herd_value"]) > 0 and cyc["herd_value_estimated"] and cyc["herd_value_basis"]
"""Pure-calculation tests: the engine must reproduce the Sahara Oasis worksheet's own figures."""
from datetime import date

import pytest

from app.modules.feedlot import metrics as m

S = m.get_settings(None)


def test_days_on_farm_uses_worksheet_minus_one_convention():
    # worksheet: Batch 1 delivered 11/12/2025, as-at 28/7/2026 -> 228 days
    assert m.days_on_farm(date(2025, 12, 11), date(2026, 7, 28)) == 228
    assert m.days_on_farm(date(2026, 1, 9), date(2026, 7, 28)) == 199     # Batch 4
    assert m.days_on_farm(date(2026, 1, 16), date(2026, 7, 28)) == 192    # Batch 5
    assert m.days_on_farm(date(2026, 1, 1), date(2026, 1, 1)) == 0        # never negative


@pytest.mark.parametrize("adg,band", [(0.1, "poor"), (0.2, "poor"), (0.3, "below_target"),
                                      (0.4, "on_target"), (0.7, "on_target"), (0.71, "excellent"), (None, None)])
def test_adg_bands_match_worksheet_colour_rules(adg, band):
    assert m.adg_band(adg, S) == band


def test_concentrate_recipe_matches_worksheet():
    ings = [(472, 38), (157, 18), (120, 25), (97, 37), (60, 26), (40, 5), (25, 15), (22.5, 140), (2.5, 125),
            (1, 450), (1, 280), (1, 280), (0.4, 500), (0.025, 3500), (0.05, 6000), (0.05, 2600), (0.1, 5500)]
    r = m.recipe_cost({"ingredients": [{"quantity_kg": q, "price_per_kg": p} for q, p in ings],
                       "fixed_costs": [{"amount": 1500}, {"amount": 1000}]})
    assert r["total_cost"] == 37726.0
    assert r["total_quantity_kg"] == 999.625
    assert r["cost_per_kg"] == pytest.approx(37.74015256, abs=1e-4)


def test_hay_budget_matches_worksheet():
    lines = [(5000, 1, 1), (4760.31, 1, 1), (10000, 1, 5), (5000, 1, 5), (5000, 1, 5), (10000, 1, 3), (3000, 1, 2),
             (60, 300, 1), (10000, 1, 1), (2000, 1, 1), (21327.45, 1, 1)]
    r = m.budget_cost({"yield_per_year": 300, "unit_weight_kg": 14,
                       "lines": [{"amount": a, "multiply_by": x, "divide_by": d} for a, x, d in lines]})
    assert r["total_cost_per_year"] == pytest.approx(69921.09, abs=0.01)
    assert r["cost_per_unit"] == pytest.approx(233.0703, abs=1e-3)
    assert r["cost_per_kg"] == pytest.approx(16.6479, abs=1e-3)


def test_acre_weighted_silage_blend_matches_worksheet():
    def budget(per_year_total, yield_kg, acres):
        return {"yield_per_year": yield_kg, "acres": acres, "lines": [{"amount": per_year_total}]}
    blend = m.blend_cost_per_kg([budget(93327.81, 30000, 34), budget(126211.61, 20000, 28), budget(119211.61, 20000, 11)])
    assert blend == pytest.approx(4.454665739, abs=1e-4)


def test_ration_plan_total_matches_worksheet_221_days():
    stages = [{"days": 21, "feeds": {"hay": 10, "silage": 0, "concentrate": 0}},
              {"days": 30, "feeds": {"hay": 6, "silage": 6, "concentrate": 0.5}},
              {"days": 30, "feeds": {"hay": 6, "silage": 6, "concentrate": 1.2}},
              {"days": 30, "feeds": {"hay": 4, "silage": 8, "concentrate": 2}},
              {"days": 30, "feeds": {"hay": 4, "silage": 8, "concentrate": 3.6}},
              {"days": 80, "feeds": {"hay": 8, "silage": 4, "concentrate": 3.6}}]
    costs = {"hay": 16.64787937, "silage": 4.454665739, "concentrate": 37.74015256}
    assert m.standard_feed_cost(stages, costs, 221) == pytest.approx(48441.09468, abs=0.05)
    assert m.standard_feed_cost(stages, costs, 21) == pytest.approx(3496.05, abs=0.05)
    assert m.standard_feed_cost(stages, costs, 0) == 0.0
    # held past the plan: last stage's daily cost keeps accruing
    extra = m.ration_stage_cost_per_day(stages[-1], costs) * 10
    assert m.standard_feed_cost(stages, costs, 231) == pytest.approx(48441.09468 + extra, abs=0.1)


def test_overhead_totals_match_worksheet():
    lines = [("Machinery", 626900, "fixed"), ("Structures", 465532.7, "fixed"), ("Lease", 2500, "fixed"),
             ("Tick", 13800, "variable"), ("Tagging", 19500, "variable"), ("Vet", 7500, "variable"),
             ("Vaccines", 6000, "variable"), ("Deworming", 9470, "variable"), ("Labour", 354000, "step"),
             ("Water", 140223.8, "fixed"), ("Power", 35055.95, "fixed"), ("Security", 108000, "fixed")]
    r = m.overhead_totals({"heads": 130, "cycle_days": 171,
                           "lines": [{"item": i, "amount": a, "behaviour": b} for i, a, b in lines]})
    assert r["total"] == pytest.approx(1788482.45, abs=0.01)
    assert r["per_head"] == pytest.approx(13757.56, abs=0.01)


def _animal(**kw):
    base = dict(animal_id="a", tag="A01", received_on=date(2025, 12, 11), entry_weight=210.0,
                weights=[(date(2025, 12, 11), 210.0), (date(2026, 1, 14), 220.0), (date(2026, 7, 28), 349.0)])
    base.update(kw)
    return m.AnimalInput(**base)


def test_active_animal_performance_matches_worksheet_row():
    # worksheet BATCH 1 row A04: entry 221, 28/7 weight 349 -> gain 128, ADG 0.5614, 57.9%
    a = _animal(entry_weight=221.0, weights=[(date(2025, 12, 11), 221.0), (date(2026, 7, 28), 349.0)])
    p = m.animal_performance(a, date(2026, 7, 28), S)
    assert (p["overall_gain"], p["days_on_farm"]) == (128.0, 228)
    assert p["adg"] == pytest.approx(0.5614, abs=1e-4)
    assert p["pct_gain"] == pytest.approx(0.5792, abs=1e-4)
    assert p["adg_band"] == "on_target" and p["market_ready"] is True


def test_sold_animal_uses_sale_weight_and_reports_presale_shrink():
    a = _animal(entry_weight=221.0, weights=[(date(2025, 12, 11), 221.0), (date(2026, 7, 28), 349.0)],
                exit_type="sold", exit_date=date(2026, 8, 4), exit_weight=339.0, exit_amount=108480.0)
    p = m.animal_performance(a, date(2026, 8, 10), S)
    # worksheet 'Sales weight Batch4' A04: 339 kg, 235 days, ADG 0.5021, WG vs 28/7 = -10
    assert (p["end_weight"], p["days_on_farm"]) == (339.0, 235)
    assert p["adg"] == pytest.approx(0.5021, abs=1e-4)
    assert p["presale_shrink_kg"] == -10.0
    assert p["status"] == "sold" and p["market_ready"] is False


def test_back_dated_as_of_ignores_later_weights_and_exit():
    a = _animal(exit_type="sold", exit_date=date(2026, 8, 4), exit_weight=339.0, exit_amount=1.0)
    p = m.animal_performance(a, date(2026, 1, 20), S)
    assert p["latest_weight"] == 220.0 and p["status"] == "active"


def test_implausible_weight_change_is_flagged():
    a = _animal(weights=[(date(2026, 1, 1), 200.0), (date(2026, 1, 2), 260.0)])
    assert any(f.startswith("implausible") for f in m.animal_performance(a, date(2026, 2, 1), S)["flags"])


def test_profit_for_sold_and_culled_animals():
    sold = _animal(exit_type="sold", exit_date=date(2026, 6, 22), exit_weight=324.0, exit_amount=106920.0, landed_cost=52812.33)
    p = m.animal_performance(sold, date(2026, 7, 28), S)
    pr = m.animal_profit(p, sold, feed_cost=40121.97, ops_cost=13757.56, s=S)
    assert pr["profit"] == pytest.approx(106920 - (52812.33 + 40121.97 + 13757.56), abs=0.01)
    culled = _animal(exit_type="culled", exit_date=date(2026, 3, 1), exit_amount=0.0, landed_cost=50000.0)
    pc = m.animal_profit(m.animal_performance(culled, date(2026, 7, 28), S), culled, 10000.0, 5000.0, S)
    assert pc["revenue"] == 0 and pc["profit"] == -65000.0     # a cull is a full loss, not silently dropped


def test_resolve_feed_costs_follows_links_over_manual_values():
    recipes = {"Conc": {"ingredients": [{"quantity_kg": 100, "price_per_kg": 30}]}}
    budgets = {"Hay": {"yield_per_year": 100, "lines": [{"amount": 1400}], "unit_weight_kg": 14}}
    out = m.resolve_feed_costs({"feed_costs": {"hay": 1.0, "water": 0.1},
                                "cost_links": {"hay": {"kind": "enterprise_budget", "name": "Hay"},
                                               "concentrate": {"kind": "recipe", "name": "Conc"}}}, budgets, recipes)
    assert out["hay"] == 1.0 and out["water"] == 0.1 and out["concentrate"] == 30.0

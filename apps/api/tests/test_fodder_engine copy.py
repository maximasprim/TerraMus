"""Fodder maths, checked against hand calculations and the Sahara Oasis hay budget."""
from datetime import date

import pytest

from app.modules.fodder import engine as e

D = date


def test_straight_line_amortisation_over_five_years_gives_a_fifth_a_year():
    inv = e.Investment("i", None, 100_000, 0, D(2026, 1, 1), 5)
    assert e.daily_charge(inv) == pytest.approx(100_000 / (5 * 365))
    assert e.amortised_to_date(inv, D(2026, 12, 31)) == pytest.approx(20_000, abs=0.01)         # one year = a fifth
    assert e.amortised_to_date(inv, D(2040, 1, 1)) == pytest.approx(100_000, abs=0.01)          # never more than the cost
    assert e.amortised_to_date(inv, D(2025, 6, 1)) == 0.0                                       # not yet in service
    sold = e.Investment("s", None, 100_000, 10_000, D(2026, 1, 1), 5, disposed_on=D(2026, 6, 30))
    assert e.amortised_to_date(sold, D(2030, 1, 1)) == pytest.approx(181 * 90_000 / (5 * 365), abs=0.01)   # stops at disposal; salvage kept


def test_plot_specific_asset_is_carried_by_the_cycle_on_that_plot():
    inv = e.Investment("i", "P1", 100_000, 0, D(2026, 1, 1), 5)
    cycles = [e.Cycle("a", "P1", 10, D(2026, 1, 1), D(2026, 12, 31)), e.Cycle("b", "P2", 10, D(2026, 1, 1), D(2026, 12, 31))]
    r = e.allocate_investments([inv], cycles, D(2026, 12, 31))
    assert r["by_cycle"]["a"] == pytest.approx(20_000, abs=0.01) and r["by_cycle"]["b"] == 0.0     # P2's cycle is not charged for P1's asset
    assert r["by_investment"]["i"]["idle"] == 0.0


def test_shared_asset_is_split_by_acre_days():
    inv = e.Investment("bunker", None, 365_000, 0, D(2026, 1, 1), 5)                              # exactly 200/day
    cycles = [e.Cycle("a", "P1", 10, D(2026, 1, 1), D(2026, 12, 31)), e.Cycle("b", "P2", 30, D(2026, 1, 1), D(2026, 12, 31))]
    r = e.allocate_investments([inv], cycles, D(2026, 12, 31))
    assert r["by_cycle"]["a"] == pytest.approx(73_000 * 0.25, abs=0.01) and r["by_cycle"]["b"] == pytest.approx(73_000 * 0.75, abs=0.01)
    assert sum(r["by_cycle"].values()) + r["by_investment"]["bunker"]["idle"] == pytest.approx(r["by_investment"]["bunker"]["charged"], abs=0.01)


def test_days_nobody_uses_the_asset_are_idle_capacity_not_hidden_in_a_cycle():
    inv = e.Investment("baler", None, 365_000, 0, D(2026, 1, 1), 5)                               # 200 / day
    late = e.Cycle("late", "P1", 10, D(2026, 7, 1), D(2026, 12, 31))                              # starts 181 days in
    r = e.allocate_investments([inv], [late], D(2026, 12, 31))
    assert r["by_investment"]["baler"]["idle"] == pytest.approx(181 * 200, abs=0.01)
    assert r["by_cycle"]["late"] == pytest.approx(184 * 200, abs=0.01)
    assert r["by_investment"]["baler"]["charged"] == pytest.approx(365 * 200, abs=0.01)


def test_a_cycle_that_overlaps_only_part_of_the_time_shares_only_that_part():
    inv = e.Investment("tractor", None, 365_000, 0, D(2026, 1, 1), 5)
    a = e.Cycle("a", "P1", 10, D(2026, 1, 1), D(2026, 12, 31))
    b = e.Cycle("b", "P2", 10, D(2026, 7, 1), D(2026, 12, 31))
    r = e.allocate_investments([inv], [a, b], D(2026, 12, 31))
    assert r["by_cycle"]["b"] == pytest.approx(184 * 200 * 0.5, abs=0.01)                          # half of the shared days
    assert r["by_cycle"]["a"] == pytest.approx(181 * 200 + 184 * 200 * 0.5, abs=0.01)


def test_running_cycle_is_costed_up_to_today_and_nothing_is_double_counted():
    inv = e.Investment("i", None, 100_000, 0, D(2026, 1, 1), 5)
    c = e.Cycle("c", "P1", 5, D(2026, 3, 1), None)                                                 # still open
    r = e.allocate_investments([inv], [c], D(2026, 4, 10))
    assert r["by_cycle"]["c"] == pytest.approx(41 * 100_000 / 1825, abs=0.01)                      # 1 Mar..10 Apr = 41 days
    assert r["by_cycle"]["c"] + r["by_investment"]["i"]["idle"] == pytest.approx(r["by_investment"]["i"]["charged"], abs=0.02)


def test_cost_of_production_and_the_value_of_not_having_to_buy_it():
    # Sahara Oasis hay budget shape: 1 acre -> 300 bales of 14 kg; cost KES 69,921 / yr
    harvests = [(D(2026, 3, 10), 1_680.0), (D(2026, 8, 20), 2_520.0)]                              # 120 + 180 bales
    prices = [(D(2026, 1, 1), 22.0), (D(2026, 6, 1), 25.0)]                                        # market price per kg rose in June
    r = e.cycle_economics(1.0, direct_cost=50_000, amortised=19_921, harvests=harvests, prices=prices, kg_per_unit=14,
                          target_cost_per_kg=16.65, target_yield_kg_per_acre=4_200)
    assert r["harvested_kg"] == 4_200 and r["harvested_units"] == 300
    assert r["cost_per_kg"] == pytest.approx(69_921 / 4_200, abs=1e-4) and r["cost_per_unit"] == pytest.approx(233.07, abs=0.01)
    assert r["replacement_value"] == 1_680 * 22 + 2_520 * 25                                       # each harvest at the price of ITS date
    assert r["saving_vs_buying"] == pytest.approx(1_680 * 22 + 2_520 * 25 - 69_921, abs=0.01)
    assert r["cost_per_kg_vs_budget_pct"] == pytest.approx(100 * (69_921 / 4_200 - 16.65) / 16.65, abs=0.1)
    assert r["yield_vs_target_pct"] == 0.0


def test_no_harvest_yet_means_no_unit_cost_instead_of_a_division_error():
    r = e.cycle_economics(2.0, 10_000, 500, [], [], 14)
    assert r["cost_per_kg"] is None and r["cost_per_unit"] is None and r["total_cost"] == 10_500 and r["cost_per_acre"] == 5_250


def test_harvest_before_any_market_price_is_flagged_not_silently_valued_at_zero():
    r = e.cycle_economics(1.0, 1_000, 0, [(D(2026, 1, 1), 100.0)], [(D(2026, 6, 1), 20.0)], 1)
    assert r["unpriced_kg"] == 100.0 and r["replacement_value"] == 0.0


def test_price_lookup_uses_the_quote_in_force_on_the_day():
    p = [(D(2026, 1, 1), 20.0), (D(2026, 6, 1), 25.0)]
    assert e.price_at(p, D(2025, 12, 31)) is None and e.price_at(p, D(2026, 5, 31)) == 20.0 and e.price_at(p, D(2026, 6, 1)) == 25.0


def test_weighted_average_cost_and_days_of_cover():
    assert e.weighted_average_cost([(1_000, 10.0), (3_000, 18.0)]) == 16.0
    assert e.weighted_average_cost([]) is None
    assert e.days_of_cover(600, 300, 30, history_days=30) == 60.0                                  # uses 10 kg/day
    assert e.days_of_cover(600, 0, 30, history_days=30) is None                                    # not being used
    assert e.days_of_cover(600, 50, 30, history_days=3) is None                                    # too little history to say
    assert e.days_of_cover(-5, 300, 30, history_days=30) == 0.0

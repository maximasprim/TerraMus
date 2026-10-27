"""Fodder production maths (pure functions, no database).

AMORTISATION. An establishment cost (land preparation, a bunker, a baler) is spread straight-line over its useful
life: charge per day = (cost - salvage) / (life_years * 365). It is allocated to production cycles by ACRE-DAYS:
for every stretch of days, each cycle that is running (on that plot, or on any plot for a shared asset) carries a share
proportional to its acres. Days when nothing is using the asset are IDLE CAPACITY: reported, never hidden inside
another cycle's cost.

COST OF PRODUCTION. cost per kg = (direct costs + allocated amortisation) / kg harvested.

THE 'WOULD HAVE BOUGHT' VALUE. Each harvest is valued at the market purchase price in force on the harvest date;
value - cost = what growing it saved against buying it.

STOCK COST. Weighted average over everything that came in (harvests at their cycle's cost per kg, purchases at the
price paid). Issues are valued at that average, restated whenever cycle costs change."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable


@dataclass
class Investment:
    id: str
    plot_id: str | None          # None = shared by every plot
    cost: float
    salvage: float
    in_service_on: date
    life_years: float
    disposed_on: date | None = None


@dataclass
class Cycle:
    id: str
    plot_id: str
    acres: float
    start: date
    end: date | None = None      # None = still running


def daily_charge(inv: Investment) -> float:
    return max(inv.cost - inv.salvage, 0.0) / (inv.life_years * 365.0)


def charge_window(inv: Investment, as_of: date) -> tuple[date, date] | None:
    """First and last day (inclusive) on which the asset is being amortised, up to `as_of`."""
    life_end = inv.in_service_on + timedelta(days=round(inv.life_years * 365) - 1)
    end = min(life_end, as_of, inv.disposed_on or life_end)
    return (inv.in_service_on, end) if end >= inv.in_service_on else None


def amortised_to_date(inv: Investment, as_of: date) -> float:
    w = charge_window(inv, as_of)
    if not w:
        return 0.0
    return min(((w[1] - w[0]).days + 1) * daily_charge(inv), max(inv.cost - inv.salvage, 0.0))


def allocate_investments(invs: Iterable[Investment], cycles: list[Cycle], as_of: date) -> dict:
    """-> {'by_cycle': {cycle_id: amount}, 'by_investment': {inv_id: {'charged','allocated','idle'}}}"""
    by_cycle: dict[str, float] = {c.id: 0.0 for c in cycles}
    by_inv: dict[str, dict[str, float]] = {}
    for inv in invs:
        d = daily_charge(inv)
        w = charge_window(inv, as_of)
        rec = {"charged": 0.0, "allocated": 0.0, "idle": 0.0}
        by_inv[inv.id] = rec
        if not w or d <= 0:
            continue
        lo, hi = w[0], w[1] + timedelta(days=1)                       # half-open [lo, hi)
        span = [(c, c.start, (c.end or as_of) + timedelta(days=1)) for c in cycles if inv.plot_id in (None, c.plot_id)]
        span = [(c, a, b) for c, a, b in span if a < hi and b > lo]
        points = sorted({lo, hi, *[max(a, lo) for _, a, _ in span], *[min(b, hi) for _, _, b in span]})
        for a, b in zip(points, points[1:]):
            days = (b - a).days
            active = [c for c, ca, cb in span if ca <= a < cb]
            total_acres = sum(c.acres for c in active)
            amount = d * days
            rec["charged"] += amount
            if total_acres > 0:
                for c in active:
                    share = amount * c.acres / total_acres
                    by_cycle[c.id] += share
                    rec["allocated"] += share
            else:
                rec["idle"] += amount
    return {"by_cycle": {k: round(v, 2) for k, v in by_cycle.items()},
            "by_investment": {k: {m: round(x, 2) for m, x in v.items()} for k, v in by_inv.items()}}


def price_at(prices: list[tuple[date, float]], on: date) -> float | None:
    """Market price per kg in force on a date (latest quote on or before it)."""
    best = None
    for eff, p in sorted(prices):
        if eff <= on:
            best = p
    return best


def cycle_economics(acres: float, direct_cost: float, amortised: float, harvests: list[tuple[date, float]],
                    prices: list[tuple[date, float]], kg_per_unit: float, target_cost_per_kg: float | None = None,
                    target_yield_kg_per_acre: float | None = None) -> dict:
    kg = sum(k for _, k in harvests)
    total = direct_cost + amortised
    priced = [(k, price_at(prices, d)) for d, k in harvests]
    value = sum(k * p for k, p in priced if p is not None)
    unpriced_kg = sum(k for k, p in priced if p is None)
    out = {
        "harvested_kg": round(kg, 2), "harvested_units": round(kg / kg_per_unit, 2) if kg_per_unit else None,
        "direct_cost": round(direct_cost, 2), "amortised_cost": round(amortised, 2), "total_cost": round(total, 2),
        "cost_per_kg": round(total / kg, 4) if kg else None,
        "cost_per_unit": round(total / (kg / kg_per_unit), 2) if kg and kg_per_unit else None,
        "cost_per_acre": round(total / acres, 2) if acres else None,
        "yield_kg_per_acre": round(kg / acres, 1) if acres else None,
        "replacement_value": round(value, 2), "unpriced_kg": round(unpriced_kg, 2),
        "saving_vs_buying": round(value - total, 2) if kg and not unpriced_kg else (round(value - total, 2) if value else None),
    }
    if target_cost_per_kg and out["cost_per_kg"] is not None:
        out["cost_per_kg_vs_budget_pct"] = round(100 * (out["cost_per_kg"] - target_cost_per_kg) / target_cost_per_kg, 1)
    if target_yield_kg_per_acre and out["yield_kg_per_acre"] is not None:
        out["yield_vs_target_pct"] = round(100 * (out["yield_kg_per_acre"] - target_yield_kg_per_acre) / target_yield_kg_per_acre, 1)
    return out


def weighted_average_cost(layers: Iterable[tuple[float, float]]) -> float | None:
    """layers = (kg, cost per kg) of everything that came in. None when nothing has come in."""
    kg = cost = 0.0
    for k, c in layers:
        kg += k
        cost += k * c
    return round(cost / kg, 4) if kg > 0 else None


def days_of_cover(balance_kg: float, issued_last_n: float, n_days: int, min_history_days: int = 7, history_days: int = 0) -> float | None:
    """Days the stock lasts at the recent rate of use. None if there is too little history to say."""
    if history_days < min_history_days or issued_last_n <= 0:
        return None
    return round(max(balance_kg, 0.0) / (issued_last_n / n_days), 1)

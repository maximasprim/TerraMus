"""Pure calculation engine for the feedlot module (no database access).

Everything the Sahara Oasis "Bulls WG Worksheet" computes by hand lives here,
corrected: weight gain / ADG / % gain / days-on-farm, market-readiness bands,
recipe and enterprise-budget costing, stage-based ration (standard feed) cost,
overhead allocation and per-animal profit.

Conventions copied from the worksheet (and kept so figures reconcile):
  * days on farm = (end date - received date) - 1, floored at 0
  * % weight gain = overall gain / entry weight (a fraction, shown as %)
  * ADG = overall gain / days on farm
Known worksheet errors are deliberately NOT reproduced (see FEEDLOT.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

DEFAULT_SETTINGS: dict[str, Any] = {
    "market_ready_kg": 300,       # worksheet colours weights >= 300 green
    "adg_poor_max": 0.2,          # ADG <= 0.2 -> red
    "adg_target_min": 0.4,        # 0.4 .. 0.7 -> green
    "adg_target_max": 0.7,        # > 0.7 -> excellent (cyan)
    "interval_gain_good": 20,     # interval gain > 20 kg -> cyan
    "day_offset": 1,              # days_on_farm = date diff - day_offset
    "reference_price_per_kg": 320,
    "implausible_gain_kg_per_day": 3.0,   # data-entry sanity check
}


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def q2(v: float | Decimal) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_settings(overrides: dict | None) -> dict[str, Any]:
    s = dict(DEFAULT_SETTINGS)
    s.update({k: v for k, v in (overrides or {}).items() if v is not None})
    return s


def days_on_farm(received_on: date, end_on: date, offset: int = 1) -> int:
    return max((end_on - received_on).days - offset, 0)


def adg_band(adg: float | None, s: dict[str, Any]) -> str | None:
    """poor (<=0.2) | below_target (0.2-0.4) | on_target (0.4-0.7) | excellent (>0.7)."""
    if adg is None:
        return None
    if adg <= s["adg_poor_max"]:
        return "poor"
    if adg < s["adg_target_min"]:
        return "below_target"
    if adg <= s["adg_target_max"]:
        return "on_target"
    return "excellent"


# --------------------------------------------------------------------- costing
def recipe_cost(data: dict) -> dict[str, float]:
    ings = data.get("ingredients", [])
    total_qty = sum(_f(i.get("quantity_kg")) for i in ings)
    ing_cost = sum(_f(i.get("quantity_kg")) * _f(i.get("price_per_kg")) for i in ings)
    fixed = sum(_f(x.get("amount")) for x in data.get("fixed_costs", []))
    total = ing_cost + fixed
    return {
        "total_quantity_kg": round(total_qty, 4), "ingredient_cost": round(ing_cost, 2),
        "fixed_costs": round(fixed, 2), "total_cost": round(total, 2),
        "cost_per_kg": round(total / total_qty, 6) if total_qty else 0.0,
    }


def budget_line_per_year(line: dict) -> float:
    return _f(line.get("amount")) * _f(line.get("multiply_by", 1), 1.0) / (_f(line.get("divide_by", 1), 1.0) or 1.0)


def budget_cost(data: dict) -> dict[str, float]:
    total = sum(budget_line_per_year(l) for l in data.get("lines", []))
    y = _f(data.get("yield_per_year"))
    per_unit = total / y if y else 0.0
    uw = _f(data.get("unit_weight_kg"))
    per_kg = per_unit / uw if uw else None
    if per_kg is None and (data.get("yield_unit") or "kg") == "kg":
        per_kg = per_unit
    return {"total_cost_per_year": round(total, 2), "yield_per_year": y,
            "cost_per_unit": round(per_unit, 6), "cost_per_kg": round(per_kg, 6) if per_kg is not None else None}


def blend_cost_per_kg(budgets: Iterable[dict]) -> float:
    """Acre-weighted blend: sum(cost_per_year*acres) / sum(yield*acres)."""
    cost = yld = 0.0
    for b in budgets:
        acres = _f(b.get("acres"), 1.0)
        c = budget_cost(b)
        cost += c["total_cost_per_year"] * acres
        yld += c["yield_per_year"] * acres
    return round(cost / yld, 6) if yld else 0.0


def ration_stage_cost_per_day(stage: dict, feed_costs: dict[str, float]) -> float:
    return sum(_f(kg) * _f(feed_costs.get(feed)) for feed, kg in (stage.get("feeds") or {}).items())


def standard_feed_cost(stages: list[dict], feed_costs: dict[str, float], days: int) -> float:
    """Cumulative planned feed cost for `days` on feed. Beyond the plan, the last
    stage's daily cost continues (a bull held past the planned cycle keeps eating)."""
    if days <= 0 or not stages:
        return 0.0
    remaining, total = days, 0.0
    for st in stages:
        take = min(remaining, int(_f(st.get("days"))))
        total += take * ration_stage_cost_per_day(st, feed_costs)
        remaining -= take
        if remaining <= 0:
            return round(total, 2)
    return round(total + remaining * ration_stage_cost_per_day(stages[-1], feed_costs), 2)


def overhead_totals(data: dict) -> dict[str, float]:
    lines = data.get("lines", [])
    total = sum(_f(l.get("amount")) for l in lines)
    by_beh: dict[str, float] = {}
    for l in lines:
        by_beh[l.get("behaviour") or "unclassified"] = by_beh.get(l.get("behaviour") or "unclassified", 0.0) + _f(l.get("amount"))
    heads, cycle = _f(data.get("heads")), _f(data.get("cycle_days"))
    return {
        "total": round(total, 2), "by_behaviour": {k: round(v, 2) for k, v in by_beh.items()},
        "per_head": round(total / heads, 2) if heads else 0.0,
        "planned_rate_per_bull_day": round(total / heads / cycle, 4) if heads and cycle else 0.0,
    }


# ----------------------------------------------------------------- performance
@dataclass
class AnimalInput:
    animal_id: str
    tag: str
    received_on: date
    entry_weight: float | None
    weights: list[tuple[date, float]]          # all weigh records (any order)
    exit_type: str | None = None               # sold | culled | died
    exit_date: date | None = None
    exit_weight: float | None = None
    exit_amount: float = 0.0
    intake_batch: int | None = None
    sale_batch: int | None = None
    landed_cost: float = 0.0


def animal_performance(a: AnimalInput, as_of: date, s: dict[str, Any]) -> dict[str, Any]:
    ws = sorted((d, w) for d, w in a.weights if d <= as_of)
    entry = a.entry_weight if a.entry_weight is not None else (ws[0][1] if ws else None)
    last_d, last_w = (ws[-1] if ws else (None, None))
    exited = a.exit_type is not None and a.exit_date is not None and a.exit_date <= as_of
    end_on = a.exit_date if exited else (last_d or as_of)
    end_w = (a.exit_weight if (exited and a.exit_weight is not None) else last_w)
    days = days_on_farm(a.received_on, end_on, int(s["day_offset"]))
    gain = (end_w - entry) if (end_w is not None and entry is not None) else None
    adg = (gain / days) if (gain is not None and days > 0) else None
    intervals = []
    for (d0, w0), (d1, w1) in zip(ws, ws[1:]):
        n = (d1 - d0).days
        intervals.append({"from": d0.isoformat(), "to": d1.isoformat(), "days": n, "gain": round(w1 - w0, 2),
                          "adg": round((w1 - w0) / n, 3) if n > 0 else None})
    flags: list[str] = []
    for iv in intervals:
        if iv["days"] > 0 and abs(iv["gain"]) / iv["days"] > s["implausible_gain_kg_per_day"]:
            flags.append(f"implausible_change_{iv['to']}")
    if a.exit_weight is not None and last_w is not None and a.exit_type == "sold":
        pass
    shrink = None
    if exited and a.exit_type == "sold" and a.exit_weight is not None and last_w is not None:
        shrink = round(a.exit_weight - last_w, 2)   # negative => weight lost before sale
    est_days_to_market = None
    if (not exited) and last_w is not None and adg and adg > 0 and last_w < s["market_ready_kg"]:
        est_days_to_market = int(round((s["market_ready_kg"] - last_w) / adg))
    return {
        "animal_id": a.animal_id, "tag": a.tag, "intake_batch": a.intake_batch, "sale_batch": a.sale_batch,
        "received_on": a.received_on.isoformat(), "entry_weight": entry,
        "latest_weight": last_w, "latest_weigh_date": last_d.isoformat() if last_d else None,
        "end_date": end_on.isoformat(), "end_weight": end_w, "days_on_farm": days,
        "overall_gain": round(gain, 2) if gain is not None else None,
        "adg": round(adg, 4) if adg is not None else None,
        "pct_gain": round(gain / entry, 4) if (gain is not None and entry) else None,
        "adg_band": adg_band(adg, s),
        "market_ready": bool(last_w is not None and last_w >= s["market_ready_kg"] and not exited),
        "status": (a.exit_type if exited else "active"), "presale_shrink_kg": shrink,
        "est_days_to_market": est_days_to_market, "intervals": intervals, "flags": flags,
    }


def animal_profit(perf: dict[str, Any], a: AnimalInput, feed_cost: float, ops_cost: float,
                  s: dict[str, Any], reference_price: float | None = None) -> dict[str, Any]:
    cost = a.landed_cost + feed_cost + ops_cost
    realised = perf.get("status", "active") != "active"   # respects the as-of date
    revenue = a.exit_amount if realised else 0.0
    out = {
        "landed_cost": round(a.landed_cost, 2), "feed_cost": round(feed_cost, 2),
        "ops_cost": round(ops_cost, 2), "total_cost": round(cost, 2),
        "revenue": round(revenue, 2), "realised": realised,
        "profit": round(revenue - cost, 2) if realised else None,
    }
    gain = perf.get("overall_gain")
    out["cost_per_kg_gain"] = round((feed_cost + ops_cost) / gain, 2) if gain and gain > 0 else None
    ew = perf.get("end_weight")
    if ew:
        out["breakeven_price_per_kg"] = round(cost / ew, 2)
    if not realised and ew:
        price = reference_price if reference_price is not None else s["reference_price_per_kg"]
        out["projected_revenue"] = round(ew * price, 2)
        out["projected_profit"] = round(ew * price - cost, 2)
    return out


def resolve_feed_costs(plan_data: dict, budgets: dict[str, dict], recipes: dict[str, dict], fodder: dict[str, float] | None = None) -> dict[str, float]:
    """Per-kg cost of each ration feed: manual `feed_costs`, overridden by live
    `cost_links` into recipes / enterprise budgets / acre-weighted silage blends."""
    costs = {k: _f(v) for k, v in (plan_data.get("feed_costs") or {}).items()}
    for feed, link in (plan_data.get("cost_links") or {}).items():
        kind = link.get("kind")
        if kind == "recipe" and link.get("name") in recipes:
            costs[feed] = recipe_cost(recipes[link["name"]])["cost_per_kg"]
        elif kind == "enterprise_budget" and link.get("name") in budgets:
            c = budget_cost(budgets[link["name"]])
            costs[feed] = c["cost_per_kg"] if c["cost_per_kg"] is not None else c["cost_per_unit"]
        elif kind == "fodder" and link.get("name") in (fodder or {}):     # the live average cost of our own stock
            costs[feed] = fodder[link["name"]]
        elif kind == "blend":
            costs[feed] = blend_cost_per_kg([budgets[n] for n in link.get("names", []) if n in budgets])
    return costs

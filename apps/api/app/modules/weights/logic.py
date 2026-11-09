"""Pure weight-performance logic (no database, no web framework) so it can be tested on its own.

Daily gain (ADG) bands, as the farm owner defined them:
    above 1.25 kg/day -> excellent
    0.9 to 1.25       -> on target
    0.6 to 0.9        -> approaching target
    below 0.6         -> below target

Readiness, from the latest weight and the recent daily gain:
    ready         at or above the target weight
    nearly_ready  projected to reach the target within NEARLY_READY_DAYS days
    growing       gaining, but further than that from the target
    stalled       not gaining (zero or negative gain)
    needs_weights fewer than two weights, so no trend yet
    no_target     neither the animal nor its batch has a target weight
Schedule (only when a target number of days on the farm is set), from the day the animal arrived:
    achieved      already at its target weight
    on_schedule   the recent daily gain reaches the target weight within the target days
    behind        at the current gain it will reach the target weight after the target days
    overdue       the target days are used up and it is not at the target weight yet
An animal that is ready or nearly ready but is not healthy (or is in quarantine) carries a `hold_reason`: it is
still shown, but no alert is sent until it is healthy again.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

EXCELLENT_ADG = 1.25       # above this: excellent
ON_TARGET_ADG = 0.9        # this up to EXCELLENT_ADG: on target
APPROACHING_ADG = 0.6      # this up to ON_TARGET_ADG: approaching target; below: below target
NEARLY_READY_DAYS = 14
RECENT_WINDOW_DAYS = 30    # "recent" gain looks at the last 30 days of weighings
STALE_WEIGH_DAYS = 45      # last weighing older than this is flagged

THRESHOLDS = {"excellent_above": EXCELLENT_ADG, "on_target_from": ON_TARGET_ADG,
              "approaching_from": APPROACHING_ADG,
              "nearly_ready_days": NEARLY_READY_DAYS, "recent_window_days": RECENT_WINDOW_DAYS}


def adg_band(adg: float | None) -> str | None:
    if adg is None:
        return None
    if adg > EXCELLENT_ADG:
        return "excellent"
    if adg >= ON_TARGET_ADG:
        return "on_target"
    if adg >= APPROACHING_ADG:
        return "approaching_target"
    return "below_target"


def daily_points(records: list[tuple[date, float]]) -> list[tuple[date, float]]:
    """One weight per day (the last one entered that day), oldest first. `records` must be in entry order."""
    by_day: dict[date, float] = {}
    for d, w in records:
        by_day[d] = float(w)
    return sorted(by_day.items())


def overall_adg(points: list[tuple[date, float]]) -> float | None:
    if len(points) < 2:
        return None
    days = (points[-1][0] - points[0][0]).days
    return (points[-1][1] - points[0][1]) / days if days > 0 else None


def recent_adg(points: list[tuple[date, float]], window_days: int = RECENT_WINDOW_DAYS) -> float | None:
    """Gain per day over the last `window_days` days of weighings (at least the last two weighings)."""
    if len(points) < 2:
        return None
    cutoff = points[-1][0] - timedelta(days=window_days)
    inside = [p for p in points if p[0] >= cutoff]
    pts = inside if len(inside) >= 2 else points[-2:]
    days = (pts[-1][0] - pts[0][0]).days
    return (pts[-1][1] - pts[0][1]) / days if days > 0 else None


def intervals(points: list[tuple[date, float]]) -> list[dict[str, Any]]:
    out = []
    for (d0, w0), (d1, w1) in zip(points, points[1:]):
        n = (d1 - d0).days
        adg = (w1 - w0) / n if n > 0 else None
        out.append({"date": d1.isoformat(), "weight_kg": round(w1, 2), "change_kg": round(w1 - w0, 2), "days": n,
                    "adg": round(adg, 3) if adg is not None else None, "band": adg_band(adg)})
    return out


def assess(points: list[tuple[date, float]], target: float | None, start_kg: float | None, today: date,
           healthy: bool = True, hold_note: str | None = None, nearly_days: int = NEARLY_READY_DAYS,
           start_date: date | None = None, target_days: int | None = None) -> dict[str, Any]:
    """Everything the Weights page shows about one animal's progress. `points` are daily_points()."""
    current = points[-1][1] if points else None
    last_date = points[-1][0] if points else None
    start = start_kg if start_kg is not None else (points[0][1] if points else None)
    overall, recent = overall_adg(points), recent_adg(points)
    adg = recent if recent is not None else overall
    out: dict[str, Any] = {
        "current_kg": round(current, 2) if current is not None else None,
        "last_weighed": last_date.isoformat() if last_date else None,
        "days_since_weighed": (today - last_date).days if last_date else None,
        "start_kg": round(start, 2) if start is not None else None,
        "gain_kg": round(current - start, 2) if (current is not None and start is not None) else None,
        "overall_adg": round(overall, 3) if overall is not None else None,
        "recent_adg": round(recent, 3) if recent is not None else None,
        "adg": round(adg, 3) if adg is not None else None,
        "adg_band": adg_band(adg),
        "target_kg": round(target, 2) if target else None,
        "remaining_kg": None, "progress_pct": None, "est_ready_date": None, "days_to_ready": None,
        "stage": "no_target", "hold_reason": None, "flags": [],
        "start_date": None, "days_on_farm": None, "target_days": None, "days_left": None, "deadline": None,
        "plan_adg": None, "required_adg": None, "schedule": None, "days_late": None,
    }
    begin = start_date or (points[0][0] if points else None)
    if begin:
        out["start_date"] = begin.isoformat()
        out["days_on_farm"] = max(0, (today - begin).days)
    if begin and target_days:
        out["target_days"] = int(target_days)
        out["days_left"] = int(target_days) - out["days_on_farm"]
        out["deadline"] = (begin + timedelta(days=int(target_days))).isoformat()
    if last_date and (today - last_date).days > STALE_WEIGH_DAYS:
        out["flags"].append("stale_weight")
    if not target:
        return out
    if current is None:
        out["stage"] = "needs_weights"
        return out
    out["remaining_kg"] = round(max(0.0, target - current), 2)
    if start is not None and target > start:
        out["progress_pct"] = round(max(0.0, min(1.0, (current - start) / (target - start))) * 100, 1)
    elif current >= target:
        out["progress_pct"] = 100.0

    if current >= target:
        stage = "ready"
    elif adg is None:
        stage = "needs_weights"
    elif adg <= 0:
        stage = "stalled"
    else:
        days_needed = math.ceil((target - current) / adg)
        est = last_date + timedelta(days=days_needed)
        out["est_ready_date"] = est.isoformat()
        out["days_to_ready"] = max(0, (est - today).days)
        stage = "nearly_ready" if out["days_to_ready"] <= nearly_days else "growing"
    out["stage"] = stage
    if out["target_days"]:
        td = out["target_days"]
        if start is not None and target > start:
            out["plan_adg"] = round((target - start) / td, 3)
        left = out["days_left"]
        if stage == "ready":
            out["schedule"] = "achieved"
        elif left is not None and left <= 0:
            out["schedule"] = "overdue"
        else:
            out["required_adg"] = round((target - current) / left, 3) if left else None
            if out["est_ready_date"]:
                late = (date.fromisoformat(out["est_ready_date"]) - date.fromisoformat(out["deadline"])).days
                out["days_late"] = max(0, late)
                out["schedule"] = "behind" if late > 0 else "on_schedule"
            elif stage == "stalled":
                out["schedule"] = "behind"
    if stage in ("ready", "nearly_ready") and not healthy:
        out["hold_reason"] = hold_note or "Not healthy"
    return out


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts for the cards at the top of the page."""
    stages: dict[str, int] = {}
    bands: dict[str, int] = {}
    for r in rows:
        stages[r["stage"]] = stages.get(r["stage"], 0) + 1
        if r["adg_band"]:
            bands[r["adg_band"]] = bands.get(r["adg_band"], 0) + 1
    adgs = [r["adg"] for r in rows if r["adg"] is not None]
    schedule: dict[str, int] = {}
    for r in rows:
        if r.get("schedule"):
            schedule[r["schedule"]] = schedule.get(r["schedule"], 0) + 1
    return {"head": len(rows), "stages": stages, "bands": bands, "schedule": schedule,
            "avg_adg": round(sum(adgs) / len(adgs), 3) if adgs else None,
            "ready_on_hold": sum(1 for r in rows if r["hold_reason"])}

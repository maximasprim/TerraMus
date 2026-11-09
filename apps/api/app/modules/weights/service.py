"""Weights report: reads animals, their weighings and their targets, and hands them to logic.py."""
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.cycles.deps import CycleSel, cond
from app.modules.feedlot import metrics as feedlot_metrics
from app.modules.feedlot.models import FeedlotAnimal, IntakeBatch
from app.modules.livestock.models import Animal, WeightRecord
from app.modules.weights import logic

LIVE_STATUSES = ("active", "for_sale", "quarantined")   # animals still on the farm and not yet sold or lost
settings = get_settings()


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.DEFAULT_TIMEZONE)


def _local_date(dt: datetime) -> date:
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(_tz()).date()


def today_local() -> date:
    return datetime.now(_tz()).date()


async def _load(db: AsyncSession, org_id: uuid.UUID, statuses=LIVE_STATUSES, animal_id: uuid.UUID | None = None,
                batch_id: uuid.UUID | None = None, cycle: CycleSel | None = None):
    """Animals with their feedlot batch, plus every weighing (entry order) keyed by animal. A production cycle
    narrows it to that cycle's intake batches (animals in no batch belong to 'unassigned'), as on the Feedlot page."""
    q = (select(Animal, FeedlotAnimal, IntakeBatch)
         .outerjoin(FeedlotAnimal, FeedlotAnimal.animal_id == Animal.id)
         .outerjoin(IntakeBatch, IntakeBatch.id == FeedlotAnimal.intake_batch_id)
         .where(Animal.organization_id == org_id))
    if statuses:
        q = q.where(Animal.status.in_(statuses))
    if animal_id:
        q = q.where(Animal.id == animal_id)
    if batch_id:
        q = q.where(IntakeBatch.id == batch_id)
    if cycle is not None:
        q = q.where(cond(IntakeBatch.production_cycle_id, cycle))
    rows = (await db.execute(q.order_by(Animal.animal_number))).all()
    ids = [a.id for a, _, _ in rows]
    weights: dict[uuid.UUID, list[tuple[date, float]]] = defaultdict(list)
    if ids:
        wq = (select(WeightRecord.animal_id, WeightRecord.recorded_at, WeightRecord.weight_kg)
              .where(WeightRecord.animal_id.in_(ids)).order_by(WeightRecord.recorded_at, WeightRecord.created_at))
        for aid, at, kg in (await db.execute(wq)).all():
            weights[aid].append((_local_date(at), float(kg)))
    return rows, weights


def _batch_label(b: IntakeBatch | None) -> str | None:
    return None if b is None else (b.name if b.name and str(b.batch_number) in b.name else f"Batch {b.batch_number} · {b.name}")


async def default_target_days(db: AsyncSession, org_id: uuid.UUID) -> int | None:
    from app.modules.feedlot.service import _settings_data
    v = feedlot_metrics.get_settings(await _settings_data(db, org_id)).get("default_target_days")
    try:
        return int(v) if v and int(v) > 0 else None
    except (TypeError, ValueError):
        return None


async def set_defaults(db: AsyncSession, org_id: uuid.UUID, weight: float, days: int | None) -> dict:
    """Save the farm's default target weight and days. They live in the Feedlot settings document (the same
    place as the Costing thresholds), so Feedlot and Weights read one value; other settings are kept as they are."""
    from app.modules.feedlot import service as fs
    data = dict(await fs._settings_data(db, org_id))
    data["market_ready_kg"] = weight
    if days:
        data["default_target_days"] = days
    else:
        data.pop("default_target_days", None)
    await fs.upsert_costing_doc(db, org_id, "settings", "default", data)
    await db.commit()
    return {"default_target_kg": weight, "default_target_days": days}


async def default_target(db: AsyncSession, org_id: uuid.UUID) -> float:
    """The weight a feedlot animal is ready at when neither it nor its batch has a target (400 kg unless the farm
    changed it under Feedlot > Costing). It is the same setting Feedlot uses, so both pages agree."""
    from app.modules.feedlot.service import _settings_data
    return float(feedlot_metrics.get_settings(await _settings_data(db, org_id))["market_ready_kg"])


def _row(a: Animal, fa: FeedlotAnimal | None, b: IntakeBatch | None, recs, today: date, default_kg: float | None = None,
         default_days: int | None = None) -> dict:
    pts = logic.daily_points(recs)
    if a.target_weight:
        target, source = float(a.target_weight), "animal"
    elif b is not None and b.target_weight_kg:
        target, source = float(b.target_weight_kg), "batch"
    elif fa is not None and default_kg:
        target, source = float(default_kg), "default"      # only animals in a feedlot batch get the default
    else:
        target, source = None, None
    if a.target_days:
        t_days, days_source = int(a.target_days), "animal"
    elif b is not None and b.target_days:
        t_days, days_source = int(b.target_days), "batch"
    elif fa is not None and default_days:
        t_days, days_source = int(default_days), "default"
    else:
        t_days, days_source = None, None
    start = float(fa.entry_weight_kg) if (fa and fa.entry_weight_kg is not None) else None
    healthy = a.health_status == "healthy" and a.status != "quarantined"
    note = "In quarantine" if a.status == "quarantined" else (f"Health: {a.health_status}" if a.health_status != "healthy" else None)
    out = logic.assess(pts, target, start, today, healthy=healthy, hold_note=note,
                       start_date=fa.received_on if fa else None, target_days=t_days)
    out.update({
        "id": str(a.id), "tag": a.animal_number, "name": a.name, "species": a.species, "breed": a.breed, "sex": a.sex,
        "status": a.status, "health_status": a.health_status,
        "batch_id": str(b.id) if b else None, "batch": _batch_label(b),
        "target_source": source, "target_days_source": days_source, "weigh_count": len(pts),
    })
    return out


async def assess_org(db: AsyncSession, org_id: uuid.UUID, today: date | None = None, batch_id: uuid.UUID | None = None,
                     cycle: CycleSel | None = None) -> list[dict]:
    today = today or today_local()
    rows, weights = await _load(db, org_id, batch_id=batch_id, cycle=cycle)
    dflt, dd = await default_target(db, org_id), await default_target_days(db, org_id)
    return [_row(a, fa, b, weights.get(a.id, []), today, dflt, dd) for a, fa, b in rows]


def _batch_summaries(rows: list[dict]) -> list[dict]:
    groups: dict[str | None, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r["batch_id"]].append(r)
    out = []
    for bid, items in groups.items():
        cur = [r["current_kg"] for r in items if r["current_kg"] is not None]
        adgs = [r["adg"] for r in items if r["adg"] is not None]
        prog = [r["progress_pct"] for r in items if r["progress_pct"] is not None]
        tg = [r["target_kg"] for r in items if r["target_kg"]]
        out.append({
            "batch_id": bid, "batch": items[0]["batch"] or "No batch", "head": len(items),
            "with_target": len(tg), "avg_target_kg": round(sum(tg) / len(tg), 1) if tg else None,
            "avg_current_kg": round(sum(cur) / len(cur), 1) if cur else None,
            "avg_adg": round(sum(adgs) / len(adgs), 3) if adgs else None,
            "adg_band": logic.adg_band(sum(adgs) / len(adgs)) if adgs else None,
            "target_days": next((r["target_days"] for r in items if r["target_days"]), None),
            "behind": sum(1 for r in items if r["schedule"] in ("behind", "overdue")),
            "avg_progress_pct": round(sum(prog) / len(prog), 1) if prog else None,
            "ready": sum(1 for r in items if r["stage"] == "ready"),
            "nearly_ready": sum(1 for r in items if r["stage"] == "nearly_ready"),
        })
    out.sort(key=lambda g: (g["batch_id"] is None, g["batch"]))
    return out


async def overview(db: AsyncSession, org_id: uuid.UUID, batch_id: uuid.UUID | None = None,
                   cycle: CycleSel | None = None) -> dict:
    rows = await assess_org(db, org_id, batch_id=batch_id, cycle=cycle)
    bq = select(IntakeBatch).where(IntakeBatch.organization_id == org_id)
    if cycle is not None:
        bq = bq.where(cond(IntakeBatch.production_cycle_id, cycle))
    batches = (await db.execute(bq.order_by(IntakeBatch.batch_number))).scalars().all()
    return {
        "as_of": today_local().isoformat(), "thresholds": logic.THRESHOLDS,
        "summary": logic.summarise(rows), "animals": rows, "batches": _batch_summaries(rows),
        "batch_options": [{"id": str(b.id), "label": _batch_label(b), "target_weight_kg": float(b.target_weight_kg) if b.target_weight_kg else None,
                          "target_days": b.target_days}
                          for b in batches],
        "default_target_kg": await default_target(db, org_id),
        "default_target_days": await default_target_days(db, org_id),
    }


async def daily(db: AsyncSession, org_id: uuid.UUID, day: date | None, cycle: CycleSel | None = None) -> dict:
    """Weights recorded on one day, one row per animal, each compared with that animal's previous weighing."""
    rows, weights = await _load(db, org_id, statuses=None, cycle=cycle)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=400)).date()
    counts: dict[date, set] = defaultdict(set)
    for aid, recs in weights.items():
        for d, _kg in recs:
            if d >= cutoff:
                counts[d].add(aid)
    days = sorted(counts, reverse=True)
    chosen = day if day in counts else (days[0] if days else None)
    result = {"days": [{"date": d.isoformat(), "head": len(counts[d])} for d in days[:90]],
              "day": chosen.isoformat() if chosen else None, "rows": []}
    if not chosen:
        return result
    today = today_local()
    dflt, dd = await default_target(db, org_id), await default_target_days(db, org_id)
    for a, fa, b in rows:
        if a.id not in counts[chosen]:
            continue
        pts = logic.daily_points(weights.get(a.id, []))
        idx = next((i for i, (d, _) in enumerate(pts) if d == chosen), None)
        if idx is None:
            continue
        w = pts[idx][1]
        prev = pts[idx - 1] if idx > 0 else None
        n = (chosen - prev[0]).days if prev else None
        adg = (w - prev[1]) / n if (prev and n) else None
        info = _row(a, fa, b, weights.get(a.id, []), today, dflt, dd)
        result["rows"].append({
            "id": str(a.id), "tag": a.animal_number, "batch": info["batch"], "weight_kg": round(w, 2),
            "previous_kg": round(prev[1], 2) if prev else None, "previous_date": prev[0].isoformat() if prev else None,
            "days_between": n, "change_kg": round(w - prev[1], 2) if prev else None,
            "adg": round(adg, 3) if adg is not None else None, "band": logic.adg_band(adg),
            "target_kg": info["target_kg"], "remaining_kg": round(max(0.0, info["target_kg"] - w), 2) if info["target_kg"] else None,
            "stage": info["stage"],
        })
    result["rows"].sort(key=lambda r: r["tag"])
    return result


async def animal_detail(db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID) -> dict:
    rows, weights = await _load(db, org_id, statuses=None, animal_id=animal_id)
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Animal not found")
    a, fa, b = rows[0]
    today = today_local()
    info = _row(a, fa, b, weights.get(a.id, []), today, await default_target(db, org_id),
               await default_target_days(db, org_id))
    pts = logic.daily_points(weights.get(a.id, []))
    series = logic.intervals(pts)
    first = {"date": pts[0][0].isoformat(), "weight_kg": round(pts[0][1], 2), "change_kg": None, "days": None, "adg": None, "band": None} if pts else None
    all_series = ([first] if first else []) + series
    # batch-mates' average on the dates this animal was weighed (only dates where at least one other animal was weighed)
    batch_avg = []
    if b is not None:
        mates, mate_w = await _load(db, org_id, statuses=None, batch_id=b.id)
        by_day: dict[date, list[float]] = defaultdict(list)
        for ma, _, _ in mates:
            if ma.id == a.id:
                continue
            for d, w in logic.daily_points(mate_w.get(ma.id, [])):
                by_day[d].append(w)
        batch_avg = [{"date": d.isoformat(), "avg_kg": round(sum(by_day[d]) / len(by_day[d]), 1), "n": len(by_day[d])}
                     for d, _ in pts if d in by_day]
    projection = None
    if info["est_ready_date"] and pts:
        projection = [{"date": pts[-1][0].isoformat(), "weight_kg": round(pts[-1][1], 2)},
                      {"date": info["est_ready_date"], "weight_kg": info["target_kg"]}]
    plan = None   # the straight line from the arrival weight to the target weight at the target number of days
    if info["deadline"] and info["start_date"] and info["target_kg"] and info["start_kg"] is not None:
        plan = [{"date": info["start_date"], "weight_kg": info["start_kg"]},
                {"date": info["deadline"], "weight_kg": info["target_kg"]}]
    return {"animal": info, "series": all_series, "batch_avg": batch_avg, "projection": projection, "plan": plan,
            "thresholds": logic.THRESHOLDS}


_UNSET = object()


async def set_batch_target(db: AsyncSession, org_id: uuid.UUID, batch_id: uuid.UUID, target: float | None,
                           days=_UNSET) -> dict:
    b = (await db.execute(select(IntakeBatch).where(IntakeBatch.id == batch_id, IntakeBatch.organization_id == org_id))).scalar_one_or_none()
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
    b.target_weight_kg = target
    if days is not _UNSET:
        b.target_days = days
    await db.commit()
    return {"batch_id": str(b.id), "target_weight_kg": float(b.target_weight_kg) if b.target_weight_kg else None,
            "target_days": b.target_days}


async def set_animal_target(db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID, target: float | None,
                            days=_UNSET) -> dict:
    a = (await db.execute(select(Animal).where(Animal.id == animal_id, Animal.organization_id == org_id))).scalar_one_or_none()
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Animal not found")
    a.target_weight = target
    if days is not _UNSET:
        a.target_days = days
    await db.commit()
    return {"animal_id": str(a.id), "target_weight_kg": float(a.target_weight) if a.target_weight else None,
            "target_days": a.target_days}

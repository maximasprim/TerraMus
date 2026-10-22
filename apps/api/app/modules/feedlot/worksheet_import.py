"""Applies a parsed worksheet to the database (idempotent, transactional, dry-run capable).

Re-importing the same workbook changes nothing; importing a newer copy of the
workbook appends only what is new (new weigh dates, new sales, new batches).
Historical imports deliberately do NOT publish AnimalAcquired/AnimalSold events,
so they cannot back-date ledger entries to 'today' or double-book income.
"""
from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.farm.models import Farm
from app.modules.feedlot import metrics
from app.modules.feedlot.models import FeedlotAnimal, FeedlotExit, IntakeBatch, SaleBatch
from app.modules.feedlot.service import upsert_costing_doc
from app.modules.feedlot.worksheet_parse import ParsedWorkbook, parse_workbook, resolve_between
from app.modules.livestock.models import Animal, AnimalEvent, WeightRecord

MAX_REPORTED = 150


def D(x) -> Decimal:
    return Decimal(str(x))


def _utc(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


class _Abort(Exception):
    pass


async def import_worksheet(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, content: bytes, *,
                           farm_id: uuid.UUID | None = None, dry_run: bool = True,
                           include_costing: bool = True) -> dict:
    try:
        pw = parse_workbook(content)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not pw.intake and not pw.sales:
        raise HTTPException(422, "No 'BATCH n' or 'Sales weight Batch n' sheets were found in this workbook")
    # Billing creates (and COMMITS) an org's subscription row the first time it is consulted.
    # Do that now, before any import writes exist, so a dry run can never be partially persisted.
    from app.modules.billing.service import get_or_create_subscription
    await get_or_create_subscription(db, org_id)
    report: dict = {"dry_run": dry_run, "ok": True, "created": Counter(), "updated": Counter(), "unchanged": Counter(),
                    "warnings": list(pw.warnings), "errors": [], "date_corrections": pw.date_corrections,
                    "reconciliation": {}}
    try:
        await _apply(db, org_id, user_id, pw, farm_id, include_costing, report)
        if dry_run:
            await db.rollback()
        else:
            await db.commit()
    except _Abort:
        await db.rollback()
        report["ok"] = False
    except HTTPException as e:
        await db.rollback()
        report["ok"] = False
        report["errors"].append({"code": "http_error", "message": str(e.detail)})
    except Exception:
        await db.rollback()
        raise
    for k in ("created", "updated", "unchanged"):
        report[k] = dict(report[k])
    n = len(report["warnings"])
    if n > MAX_REPORTED:
        report["warnings"] = report["warnings"][:MAX_REPORTED] + [{"code": "truncated", "message": f"{n - MAX_REPORTED} more warnings not shown"}]
    return report


async def _apply(db, org_id, user_id, pw: ParsedWorkbook, farm_id, include_costing, report) -> None:
    def warn(code, where, msg, **kw):
        report["warnings"].append({"code": code, "where": where, "message": msg, **kw})

    def fail(code, msg):
        report["errors"].append({"code": code, "message": msg})
        raise _Abort()

    if farm_id is None:
        farm_id = (await db.execute(select(Farm.id).where(Farm.organization_id == org_id).order_by(Farm.created_at))).scalars().first()
    else:
        if not (await db.execute(select(Farm.id).where(Farm.id == farm_id, Farm.organization_id == org_id))).first():
            fail("farm_not_found", "farm_id does not belong to this organization")
    if farm_id is None:
        fail("no_farm", "Create a farm first (or pass farm_id) - imported animals must belong to a farm")

    from app.modules.catalog.service import is_species_allowed
    if not await is_species_allowed(db, org_id, "cattle"):
        fail("species_disabled", "Species 'cattle' is not enabled for this organization")

    # ---------------------------------------------------------- intake batches
    batches: dict[int, IntakeBatch] = {}
    existing = {b.batch_number: b for b in (await db.execute(select(IntakeBatch).where(IntakeBatch.organization_id == org_id))).scalars()}
    for num, sh in sorted(pw.intake.items()):
        cost = pw.batch_costs.get(num, {})
        fields = dict(delivered_on=sh.delivered_on, source=sh.source, sex_class=sh.sex_class, farm_id=farm_id,
                      head_purchased=cost.get("head") or sh.head_hint or len(sh.rows),
                      **{k: D(v) for k, v in cost.items() if k != "head"})
        b = existing.get(num)
        if b is None:
            b = IntakeBatch(organization_id=org_id, batch_number=num, name=sh.name, **fields)
            db.add(b)
            report["created"]["intake_batches"] += 1
        else:
            changed = False
            for k, v in fields.items():
                if k in ("farm_id",) and b.farm_id:
                    continue
                if v is not None and getattr(b, k) != v:
                    setattr(b, k, v); changed = True
            report["updated" if changed else "unchanged"]["intake_batches"] += 1
        batches[num] = b
    await db.flush()
    by_date = {b.delivered_on: b for b in batches.values()}
    for num, b in existing.items():
        batches.setdefault(num, b)
        by_date.setdefault(b.delivered_on, b)
    known_received = set(by_date)

    # ------------------------------------------------------------ sale batches
    sale_batches: dict[int, SaleBatch] = {}
    existing_sb = {b.batch_number: b for b in (await db.execute(select(SaleBatch).where(SaleBatch.organization_id == org_id))).scalars()}
    sales_rows: dict[str, list[dict]] = defaultdict(list)     # tag -> candidate sale rows
    tagless = 0
    for num, ss in sorted(pw.sales.items()):
        resolved_rows = []
        for r in ss.rows:
            recv, sw, _ = resolve_between([c for c in r["recv_cands"] if c in known_received] or r["recv_cands"], None, None)
            lo = recv
            sold, swapped, unres = resolve_between(r["sold_cands"], lo, None)
            if swapped:
                report["date_corrections"].append({"where": r["where"], "read_as": r["sold_cands"][0].isoformat(),
                                                   "corrected_to": sold.isoformat(), "reason": "sold date before received date as typed"})
            tag = r["tag"]
            if not tag or tag.lower() == "tagless":
                tagless += 1
                tag = f"TAGLESS-{num}-{tagless}"
                warn("tagless_animal", r["where"], f"Sale row without a tag; registered as {tag} (received {recv})")
            row = {**r, "tag": tag, "received_on": recv, "sold_on": sold, "sale_batch": num}
            resolved_rows.append(row)
            sales_rows[tag].append(row)
        if resolved_rows:
            sold_on = Counter(r["sold_on"] for r in resolved_rows).most_common(1)[0][0]
            fields = dict(sold_on=sold_on, price_per_kg=D(pw.sale_prices[num]) if num in pw.sale_prices else None)
            sb = existing_sb.get(num)
            if sb is None:
                sb = SaleBatch(organization_id=org_id, batch_number=num, **fields)
                db.add(sb); report["created"]["sale_batches"] += 1
            else:
                ch = False
                for k, v in fields.items():
                    if v is not None and getattr(sb, k) != v:
                        setattr(sb, k, v); ch = True
                report["updated" if ch else "unchanged"]["sale_batches"] += 1
            sale_batches[num] = sb
            if num not in pw.sale_prices:
                warn("no_price", ss.sheet, f"No price per kg found for sale batch {num}; sale amounts will be 0 until it is set")
    await db.flush()

    # ----------------------------------------------------------- animal universe
    plan: dict[str, dict] = {}                         # tag -> {batch, received_on, entry, weights}
    for num, sh in sorted(pw.intake.items()):
        for r in sh.rows:
            if r["tag"] in plan:
                warn("duplicate_tag_in_intake", sh.sheet, f"{r['tag']} appears in more than one intake sheet; keeping the first")
                continue
            plan[r["tag"]] = {"batch": batches[num], "received_on": sh.delivered_on, "entry": r["entry_weight"], "weights": r["weights"]}
    for tag, rows in sales_rows.items():
        if tag in plan:
            continue
        r = rows[0]
        b = by_date.get(r["received_on"]) if r["received_on"] else None
        if not b:
            warn("animal_unplaced", r["where"], f"{tag}: received date {r['received_on']} matches no intake batch; skipped")
            continue
        plan[tag] = {"batch": b, "received_on": r["received_on"], "entry": r["entry_weight"], "weights": []}
        warn("animal_only_in_sales", r["where"], f"{tag} is in a sales sheet but no intake sheet; created from the sale row")

    # --------------------------------------------------------------- exits plan
    exits: dict[str, dict] = {}
    for tag, rows in sales_rows.items():
        if len(rows) > 1:
            rows = sorted(rows, key=lambda x: x["sold_on"])
            warn("duplicate_sale", ", ".join(x["where"] for x in rows),
                 f"{tag} is listed as sold {len(rows)} times (" + "; ".join(f"batch {x['sale_batch']} on {x['sold_on']} at {x['sale_weight']:g}kg" for x in rows)
                 + f"). Kept the earliest ({rows[0]['sold_on']}); the original worksheet counts this animal's revenue and costs more than once.")
        exits[tag] = {"type": "sold", **rows[0]}
    for tag, code in pw.register_sold.items():
        if code == "culled" and tag not in exits:
            exits[tag] = {"type": "culled"}
    # ------------------------------------------------------------ create/update
    ex_animals = {a.animal_number: a for a in (await db.execute(select(Animal).where(
        Animal.organization_id == org_id, Animal.animal_number.in_(list(plan))))).scalars()}
    from app.modules.billing.service import check_animal_limit
    link_rows = {fa.animal_id: fa for fa in (await db.execute(select(FeedlotAnimal).where(FeedlotAnimal.organization_id == org_id))).scalars()}
    sb_by_num = {**existing_sb, **sale_batches}
    for tag, p in sorted(plan.items()):
        b: IntakeBatch = p["batch"]
        animal = ex_animals.get(tag)
        if animal is None:
            try:
                await check_animal_limit(db, org_id)
            except HTTPException as e:
                fail("animal_limit", f"{e.detail} (needed for this import: {sum(1 for t in plan if t not in ex_animals)} new animals)")
            animal = Animal(organization_id=org_id, farm_id=farm_id, animal_number=tag, species="cattle",
                            category=b.sex_class if b.sex_class in ("bull", "steer", "heifer") else None,
                            sex="female" if b.sex_class == "heifer" else "male", acquisition_date=p["received_on"],
                            acquisition_method="purchased", acquisition_cost=D(b.landed_cost_per_head),
                            source=b.source, status="active", health_status="healthy")
            db.add(animal)
            await db.flush()
            db.add(AnimalEvent(animal_id=animal.id, event_type="acquired", event_at=_utc(p["received_on"]), recorded_by=user_id,
                               data={"acquisition_method": "purchased", "imported": True}))
            report["created"]["animals"] += 1
        else:
            report["unchanged"]["animals"] += 1
        fa = link_rows.get(animal.id)
        if fa is None:
            db.add(FeedlotAnimal(organization_id=org_id, animal_id=animal.id, intake_batch_id=b.id, received_on=p["received_on"],
                                 entry_weight_kg=D(p["entry"]) if p["entry"] else None))
            report["created"]["batch_links"] += 1
        # weights (skip dates already recorded -> idempotent append)
        have = {w.recorded_at.date() for w in (await db.execute(select(WeightRecord).where(WeightRecord.animal_id == animal.id))).scalars()}
        new_w = 0
        for d, kg in sorted(p["weights"]):
            if d in have:
                continue
            db.add(WeightRecord(animal_id=animal.id, weight_kg=D(kg), recorded_at=_utc(d), recorded_by=user_id, notes="Imported from worksheet"))
            db.add(AnimalEvent(animal_id=animal.id, event_type="weighed", event_at=_utc(d), recorded_by=user_id,
                               data={"weight_kg": str(kg), "imported": True}))
            have.add(d); new_w += 1
        report["created"]["weight_records"] += new_w
        if p["weights"]:
            latest = max(have)
            if animal.status in ("active",) or animal.current_weight is None:
                kg_latest = next((kg for d, kg in sorted(p["weights"], reverse=True) if d == latest), None)
                if kg_latest is not None:
                    animal.current_weight = D(kg_latest)
        # exits
        ex = exits.get(tag)
        has_exit = (await db.execute(select(FeedlotExit.id).where(FeedlotExit.animal_id == animal.id))).first()
        if ex and not has_exit:
            if ex["type"] == "sold":
                sb = sb_by_num.get(ex["sale_batch"])
                price = sb.price_per_kg if sb and sb.price_per_kg else None
                amount = metrics.q2(D(ex["sale_weight"]) * D(price)) if price else D(0)
                db.add(FeedlotExit(organization_id=org_id, animal_id=animal.id, exit_type="sold", exit_date=ex["sold_on"],
                                   sale_batch_id=sb.id if sb else None, exit_weight_kg=D(ex["sale_weight"]),
                                   price_per_kg=price, amount=amount, created_by=user_id))
                animal.status = "sold"
                report["created"]["sales"] += 1
            else:
                last = max((d for d, _ in p["weights"]), default=p["received_on"])
                db.add(FeedlotExit(organization_id=org_id, animal_id=animal.id, exit_type="culled", exit_date=last,
                                   amount=D(0), reason="Marked 'culled' in the Bull Inventory register", created_by=user_id))
                animal.status = "culled"
                report["created"]["culls"] += 1
                warn("cull_date_unknown", tag, f"{tag} is 'culled' in the register without a date; used its last weigh date {last}")
        elif ex and has_exit:
            report["unchanged"]["exits"] += 1
    await db.flush()

    # ---------------------------------------------------------- reconciliation
    sold_tags, culled = set(exits) - {t for t, e in exits.items() if e["type"] == "culled"}, {t for t, e in exits.items() if e["type"] == "culled"}
    in_sheets = set(plan)
    rec = {"intake_animals": len(in_sheets), "sold": len(sold_tags), "culled": len(culled),
           "active": len(in_sheets - sold_tags - culled)}
    if pw.register_present:
        stock = pw.register_stock
        rec["register_current_stock_listed"] = len(stock)
        sold_but_stock = sorted(sold_tags & stock)
        stock_missing = sorted(stock - in_sheets)
        unaccounted = sorted(in_sheets - sold_tags - culled - stock)
        if sold_but_stock:
            warn("register_mismatch", "Bull Inventory register", f"{len(sold_but_stock)} animal(s) are in CURRENT STOCK but also have a sale row: {sold_but_stock[:12]}")
        if stock_missing:
            warn("register_mismatch", "Bull Inventory register", f"{len(stock_missing)} CURRENT STOCK tag(s) match no intake sheet row: {stock_missing[:12]}")
        if unaccounted:
            warn("unaccounted_animals", "Bull Inventory register", f"{len(unaccounted)} animal(s) are neither sold, culled nor listed in current stock (kept active): {unaccounted[:12]}")
        rec.update({"in_stock_and_sold": sold_but_stock, "stock_without_intake_row": stock_missing, "unaccounted": unaccounted})
    for num, b in sorted(batches.items()):
        listed = sum(1 for p in plan.values() if p["batch"].batch_number == num)
        if b.head_purchased and listed and listed != b.head_purchased:
            warn("headcount_mismatch", f"BATCH {num}", f"Batch {num}: {b.head_purchased} bulls purchased but {listed} listed on its sheet")
    report["reconciliation"] = rec

    if include_costing:
        for kind, name, data in pw.docs:
            await upsert_costing_doc(db, org_id, kind, name, data)
            report["created"]["costing_documents"] += 1

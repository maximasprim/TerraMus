import io
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer
from app.modules.identity.models import Organization
from app.modules.receivables.models import AccountEntry
from app.modules.training import schemas
from app.modules.training.models import TrainingAttendance, TrainingCourse, TrainingEnrolment, TrainingSession

MIN_ATTENDANCE = 0.75
D = lambda x: Decimal(str(x))


def _nf(what): return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


async def _one(db, model, org_id, id_, what):
    r = (await db.execute(select(model).where(model.id == id_, model.organization_id == org_id))).scalar_one_or_none()
    if not r:
        raise _nf(what)
    return r


def _course_out(c: TrainingCourse) -> dict:
    return {"id": str(c.id), "title": c.title, "description": c.description, "category": c.category,
            "duration_days": c.duration_days, "fee": float(c.fee), "capacity": c.capacity, "trainer": c.trainer, "is_active": c.is_active}


async def list_courses(db, org_id, active_only=False):
    q = select(TrainingCourse).where(TrainingCourse.organization_id == org_id).order_by(TrainingCourse.title)
    if active_only:
        q = q.where(TrainingCourse.is_active.is_(True))
    return [_course_out(c) for c in (await db.execute(q)).scalars()]


async def create_course(db, org_id, req: schemas.CourseCreate):
    c = TrainingCourse(organization_id=org_id, **req.model_dump())
    db.add(c); await db.commit()
    return _course_out(c)


async def update_course(db, org_id, course_id, req: schemas.CourseUpdate):
    c = await _one(db, TrainingCourse, org_id, course_id, "Course")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    await db.commit()
    return _course_out(c)


async def _counts(db, session_ids):
    rows = await db.execute(select(TrainingEnrolment.session_id, TrainingEnrolment.status, func.count(), func.coalesce(func.sum(TrainingEnrolment.fee_charged), 0))
                            .where(TrainingEnrolment.session_id.in_(session_ids)).group_by(TrainingEnrolment.session_id, TrainingEnrolment.status))
    out = {}
    for sid, st, n, fee in rows.all():
        d = out.setdefault(sid, {"by_status": {}, "enrolled": 0, "charged": Decimal("0")})
        d["by_status"][st] = n
        if st != "cancelled":
            d["enrolled"] += n; d["charged"] += D(fee)
    return out


def _session_out(s: TrainingSession, course: TrainingCourse, c: dict | None) -> dict:
    cap = s.capacity or course.capacity
    c = c or {"by_status": {}, "enrolled": 0, "charged": Decimal("0")}
    return {"id": str(s.id), "course_id": str(s.course_id), "course_title": course.title, "start_date": s.start_date.isoformat(),
            "end_date": s.end_date.isoformat(), "venue": s.venue, "farm_id": str(s.farm_id) if s.farm_id else None,
            "capacity": cap, "fee": float(s.fee if s.fee is not None else course.fee), "status": s.status, "notes": s.notes,
            "enrolled": c["enrolled"], "seats_left": (cap - c["enrolled"]) if cap else None, "by_status": c["by_status"],
            "fees_charged": float(c["charged"])}


async def create_session(db, org_id, req: schemas.SessionCreate):
    course = await _one(db, TrainingCourse, org_id, req.course_id, "Course")
    end = req.end_date or (req.start_date + timedelta(days=course.duration_days - 1))
    if end < req.start_date:
        raise HTTPException(422, "end_date cannot be before start_date")
    s = TrainingSession(organization_id=org_id, course_id=course.id, farm_id=req.farm_id, start_date=req.start_date, end_date=end,
                        venue=req.venue, capacity=req.capacity, fee=req.fee, notes=req.notes)
    db.add(s); await db.commit()
    return _session_out(s, course, None)


async def list_sessions(db, org_id, status_: str | None, start: date | None, end: date | None, course_id=None):
    q = (select(TrainingSession, TrainingCourse).join(TrainingCourse, TrainingCourse.id == TrainingSession.course_id)
         .where(TrainingSession.organization_id == org_id).order_by(TrainingSession.start_date.desc()))
    if status_: q = q.where(TrainingSession.status == status_)
    if start: q = q.where(TrainingSession.end_date >= start)
    if end: q = q.where(TrainingSession.start_date <= end)
    if course_id: q = q.where(TrainingSession.course_id == course_id)
    rows = (await db.execute(q)).all()
    counts = await _counts(db, [s.id for s, _ in rows]) if rows else {}
    return [_session_out(s, c, counts.get(s.id)) for s, c in rows]


async def _paid_for(db, org_id, enrolment_ids):
    if not enrolment_ids:
        return {}, {}
    rows = await db.execute(select(AccountEntry.reference_id, AccountEntry.entry_type, func.sum(AccountEntry.amount))
                            .where(AccountEntry.organization_id == org_id, AccountEntry.reference_type == "training_enrolment",
                                   AccountEntry.reference_id.in_(enrolment_ids)).group_by(AccountEntry.reference_id, AccountEntry.entry_type))
    paid, wo = {}, {}
    for rid, t, tot in rows.all():
        if t == "payment": paid[rid] = D(tot)
        elif t == "writeoff": wo[rid] = D(tot)
    return paid, wo


async def session_detail(db, org_id, session_id):
    s = await _one(db, TrainingSession, org_id, session_id, "Session")
    course = await _one(db, TrainingCourse, org_id, s.course_id, "Course")
    enrs = list((await db.execute(select(TrainingEnrolment).where(TrainingEnrolment.session_id == s.id)
                                  .order_by(TrainingEnrolment.participant_name))).scalars())
    paid, wo = await _paid_for(db, org_id, [e.id for e in enrs])
    days = {}
    for a in (await db.execute(select(TrainingAttendance).where(TrainingAttendance.enrolment_id.in_([e.id for e in enrs] or [None])))).scalars():
        days.setdefault(a.enrolment_id, []).append(a)
    total_days = (s.end_date - s.start_date).days + 1
    roster, charged, collected = [], Decimal("0"), Decimal("0")
    for e in enrs:
        pd = paid.get(e.id, Decimal("0")); due = D(e.fee_charged) - pd - wo.get(e.id, Decimal("0")) if e.status != "cancelled" else Decimal("0")
        present = sum(1 for a in days.get(e.id, []) if a.present)
        if e.status != "cancelled":
            charged += D(e.fee_charged); collected += pd
        roster.append({"id": str(e.id), "participant_name": e.participant_name, "phone": e.phone, "email": e.email,
                       "customer_id": str(e.customer_id) if e.customer_id else None, "status": e.status,
                       "fee_charged": float(e.fee_charged), "paid": float(pd), "outstanding": float(max(due, 0)),
                       "days_present": present, "attendance_pct": round(present / total_days, 2) if days.get(e.id) else None,
                       "certificate_number": e.certificate_number})
    out = _session_out(s, course, (await _counts(db, [s.id])).get(s.id))
    out.update({"roster": roster, "total_days": total_days, "collected": float(collected), "outstanding": float(max(charged - collected, 0))})
    return out


async def update_session(db, org_id, session_id, req: schemas.SessionUpdate):
    s = await _one(db, TrainingSession, org_id, session_id, "Session")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    if s.end_date < s.start_date:
        raise HTTPException(422, "end_date cannot be before start_date")
    await db.commit()
    return await session_detail(db, org_id, s.id)


async def enrol(db, org_id, user_id, session_id, req: schemas.EnrolRequest):
    s = await _one(db, TrainingSession, org_id, session_id, "Session")
    course = await _one(db, TrainingCourse, org_id, s.course_id, "Course")
    if s.status in ("completed", "cancelled"):
        raise HTTPException(409, f"Session is {s.status}; enrolment is closed")
    live = list((await db.execute(select(TrainingEnrolment).where(TrainingEnrolment.session_id == s.id,
                                                                  TrainingEnrolment.status != "cancelled"))).scalars())
    cap = s.capacity or course.capacity
    if cap and len(live) >= cap:
        raise HTTPException(409, f"Session is full ({cap} seats)")
    key = (req.email or req.phone or req.participant_name).strip().lower()
    for e in live:
        if key in {(e.email or "").lower(), (e.phone or "").lower(), e.participant_name.strip().lower()}:
            raise HTTPException(409, f"{req.participant_name} is already enrolled in this session")
    fee = D(req.fee_override if req.fee_override is not None else (s.fee if s.fee is not None else course.fee))
    customer_id = req.customer_id
    if customer_id:
        await _one(db, Customer, org_id, customer_id, "Customer")
    elif req.bill and fee > 0:
        cust = Customer(organization_id=org_id, name=req.participant_name, phone=req.phone, email=req.email, notes="Created from training enrolment")
        db.add(cust); await db.flush(); customer_id = cust.id
    e = TrainingEnrolment(organization_id=org_id, session_id=s.id, customer_id=customer_id, participant_name=req.participant_name,
                          phone=req.phone, email=req.email, fee_charged=fee)
    db.add(e); await db.flush()
    if req.bill and fee > 0 and customer_id:   # same transaction as the enrolment
        db.add(AccountEntry(organization_id=org_id, customer_id=customer_id, entry_type="charge", amount=fee, entry_date=date.today(),
                            reference_type="training_enrolment", reference_id=e.id, farm_id=s.farm_id, activity="training",
                            description=f"{course.title} ({s.start_date:%d/%m/%Y}) - {req.participant_name}", created_by=user_id))
    await db.commit()
    return {"id": str(e.id), "status": e.status, "fee_charged": float(fee), "customer_id": str(customer_id) if customer_id else None,
            "seats_left": (cap - len(live) - 1) if cap else None}


async def set_enrolment_status(db, org_id, user_id, enrolment_id, new: str):
    e = await _one(db, TrainingEnrolment, org_id, enrolment_id, "Enrolment")
    if e.status == "cancelled":
        raise HTTPException(409, "Cancelled enrolments cannot be changed")
    out = {"id": str(e.id), "status": new}
    if new == "cancelled" and e.customer_id and D(e.fee_charged) > 0:
        paid, wo = await _paid_for(db, org_id, [e.id])
        owed = D(e.fee_charged) - paid.get(e.id, Decimal("0")) - wo.get(e.id, Decimal("0"))
        if owed > 0:      # reverse the unpaid part of the charge
            db.add(AccountEntry(organization_id=org_id, customer_id=e.customer_id, entry_type="writeoff", amount=owed,
                                entry_date=date.today(), reference_type="training_enrolment", reference_id=e.id,
                                description=f"Enrolment cancelled: {e.participant_name}", created_by=user_id))
        if paid.get(e.id, 0) > 0:
            out["refund_due"] = float(paid[e.id])
    e.status = new
    await db.commit()
    return out


async def mark_attendance(db, org_id, enrolment_id, req: schemas.AttendanceMark):
    e = await _one(db, TrainingEnrolment, org_id, enrolment_id, "Enrolment")
    s = await _one(db, TrainingSession, org_id, e.session_id, "Session")
    if not (s.start_date <= req.day <= s.end_date):
        raise HTTPException(422, f"{req.day} is outside the session ({s.start_date} to {s.end_date})")
    row = (await db.execute(select(TrainingAttendance).where(TrainingAttendance.enrolment_id == e.id, TrainingAttendance.day == req.day))).scalar_one_or_none()
    if row: row.present = req.present
    else: db.add(TrainingAttendance(organization_id=org_id, enrolment_id=e.id, day=req.day, present=req.present))
    if req.present and e.status == "registered":
        e.status = "attended"
    await db.commit()
    return {"enrolment_id": str(e.id), "day": req.day.isoformat(), "present": req.present, "status": e.status}


async def issue_certificate(db, org_id, enrolment_id, force: bool):
    e = await _one(db, TrainingEnrolment, org_id, enrolment_id, "Enrolment")
    s = await _one(db, TrainingSession, org_id, e.session_id, "Session")
    if e.certificate_number:
        return {"certificate_number": e.certificate_number, "already_issued": True}
    if e.status in ("cancelled", "no_show"):
        raise HTTPException(409, f"Cannot issue a certificate to a {e.status} enrolment")
    att = list((await db.execute(select(TrainingAttendance).where(TrainingAttendance.enrolment_id == e.id))).scalars())
    total = (s.end_date - s.start_date).days + 1
    pct = sum(1 for a in att if a.present) / total if att else None
    if not force and (pct is None or pct < MIN_ATTENDANCE):
        raise HTTPException(409, f"Attendance {'not recorded' if pct is None else f'{pct:.0%}'}; at least {MIN_ATTENDANCE:.0%} is required (use force to override)")
    year = date.today().year
    for _ in range(3):
        n = (await db.execute(select(func.count()).select_from(TrainingEnrolment).where(
            TrainingEnrolment.organization_id == org_id, TrainingEnrolment.certificate_number.like(f"CERT-{year}-%")))).scalar_one() + 1
        e.certificate_number, e.certificate_issued_on, e.status = f"CERT-{year}-{n:04d}", date.today(), "completed"
        try:
            await db.commit()
            return {"certificate_number": e.certificate_number, "already_issued": False, "attendance_pct": pct}
        except IntegrityError:
            await db.rollback()
            e = await _one(db, TrainingEnrolment, org_id, enrolment_id, "Enrolment")
    raise HTTPException(409, "Could not allocate a certificate number; try again")


async def certificate_pdf(db, org_id, enrolment_id) -> bytes:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
    e = await _one(db, TrainingEnrolment, org_id, enrolment_id, "Enrolment")
    if not e.certificate_number:
        raise HTTPException(409, "No certificate has been issued for this enrolment yet")
    s = await _one(db, TrainingSession, org_id, e.session_id, "Session")
    c = await _one(db, TrainingCourse, org_id, s.course_id, "Course")
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one()
    buf = io.BytesIO(); w, h = landscape(A4); p = canvas.Canvas(buf, pagesize=(w, h))
    p.setLineWidth(3); p.rect(25, 25, w - 50, h - 50); p.setLineWidth(1); p.rect(35, 35, w - 70, h - 70)
    p.setFont("Helvetica-Bold", 16); p.drawCentredString(w / 2, h - 90, org.name.upper())
    p.setFont("Helvetica-Bold", 34); p.drawCentredString(w / 2, h - 150, "CERTIFICATE OF COMPLETION")
    p.setFont("Helvetica", 15); p.drawCentredString(w / 2, h - 205, "This is to certify that")
    p.setFont("Helvetica-Bold", 28); p.drawCentredString(w / 2, h - 250, e.participant_name)
    p.setFont("Helvetica", 15); p.drawCentredString(w / 2, h - 295, "has successfully completed the training course")
    p.setFont("Helvetica-Bold", 22); p.drawCentredString(w / 2, h - 335, c.title)
    p.setFont("Helvetica", 13)
    p.drawCentredString(w / 2, h - 370, f"{s.start_date:%d %B %Y}" + (f" - {s.end_date:%d %B %Y}" if s.end_date != s.start_date else "") + (f"  |  {s.venue}" if s.venue else ""))
    if c.trainer: p.drawCentredString(w / 2, h - 395, f"Trainer: {c.trainer}")
    p.setFont("Helvetica", 11); p.drawString(60, 60, f"Certificate No: {e.certificate_number}")
    p.drawRightString(w - 60, 60, f"Issued: {e.certificate_issued_on:%d %B %Y}")
    p.showPage(); p.save()
    return buf.getvalue()


async def summary(db, org_id, start: date, end: date) -> dict:
    sessions = await list_sessions(db, org_id, None, start, end)
    sids = [uuid.UUID(s["id"]) for s in sessions]
    enrs = list((await db.execute(select(TrainingEnrolment).where(TrainingEnrolment.session_id.in_(sids or [None]),
                                                                  TrainingEnrolment.status != "cancelled"))).scalars())
    paid, _ = await _paid_for(db, org_id, [e.id for e in enrs])
    charged = sum((D(e.fee_charged) for e in enrs), Decimal("0")); collected = sum(paid.values(), Decimal("0"))
    return {"start_date": start.isoformat(), "end_date": end.isoformat(), "sessions": len(sessions),
            "participants": len(enrs), "completed": sum(e.status == "completed" for e in enrs),
            "certificates_issued": sum(bool(e.certificate_number) for e in enrs), "fees_charged": float(charged),
            "fees_collected": float(collected), "outstanding": float(charged - collected),
            "by_course": [{"course": s["course_title"], "start_date": s["start_date"], "enrolled": s["enrolled"], "fees_charged": s["fees_charged"]} for s in sessions]}

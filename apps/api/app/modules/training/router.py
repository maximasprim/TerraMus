import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.training import schemas, service

router = APIRouter(prefix="/api/v1/training", tags=["training"])
R, M = require_permission("training.read"), require_permission("training.manage")


@router.get("/courses")
async def courses(active_only: bool = Query(False), user: User = Depends(R), db: AsyncSession = Depends(get_db)):
    return await service.list_courses(db, user.organization_id, active_only)


@router.post("/courses", status_code=201)
async def create_course(req: schemas.CourseCreate, user: User = Depends(M), db: AsyncSession = Depends(get_db)):
    return await service.create_course(db, user.organization_id, req)


@router.patch("/courses/{course_id}")
async def update_course(course_id: uuid.UUID, req: schemas.CourseUpdate, user: User = Depends(M), db: AsyncSession = Depends(get_db)):
    return await service.update_course(db, user.organization_id, course_id, req)


@router.get("/sessions")
async def sessions(status: str | None = Query(None, pattern="^(scheduled|in_progress|completed|cancelled)$"), start_date: date | None = Query(None),
                   end_date: date | None = Query(None), course_id: uuid.UUID | None = Query(None), user: User = Depends(R), db: AsyncSession = Depends(get_db)):
    return await service.list_sessions(db, user.organization_id, status, start_date, end_date, course_id)


@router.post("/sessions", status_code=201)
async def create_session(req: schemas.SessionCreate, user: User = Depends(M), db: AsyncSession = Depends(get_db)):
    return await service.create_session(db, user.organization_id, req)


@router.get("/sessions/{session_id}")
async def session_detail(session_id: uuid.UUID, user: User = Depends(R), db: AsyncSession = Depends(get_db)):
    return await service.session_detail(db, user.organization_id, session_id)


@router.patch("/sessions/{session_id}")
async def update_session(session_id: uuid.UUID, req: schemas.SessionUpdate, user: User = Depends(M), db: AsyncSession = Depends(get_db)):
    return await service.update_session(db, user.organization_id, session_id, req)


@router.post("/sessions/{session_id}/enrolments", status_code=201)
async def enrol(session_id: uuid.UUID, req: schemas.EnrolRequest, user: User = Depends(M), db: AsyncSession = Depends(get_db)):
    return await service.enrol(db, user.organization_id, user.id, session_id, req)


@router.patch("/enrolments/{enrolment_id}/status")
async def set_status(enrolment_id: uuid.UUID, req: schemas.EnrolmentStatusUpdate, user: User = Depends(M), db: AsyncSession = Depends(get_db)):
    return await service.set_enrolment_status(db, user.organization_id, user.id, enrolment_id, req.status)


@router.post("/enrolments/{enrolment_id}/attendance")
async def attendance(enrolment_id: uuid.UUID, req: schemas.AttendanceMark, user: User = Depends(M), db: AsyncSession = Depends(get_db)):
    return await service.mark_attendance(db, user.organization_id, enrolment_id, req)


@router.post("/enrolments/{enrolment_id}/certificate")
async def issue_certificate(enrolment_id: uuid.UUID, req: schemas.CertificateRequest, user: User = Depends(M), db: AsyncSession = Depends(get_db)):
    return await service.issue_certificate(db, user.organization_id, enrolment_id, req.force)


@router.get("/enrolments/{enrolment_id}/certificate.pdf")
async def certificate_pdf(enrolment_id: uuid.UUID, user: User = Depends(R), db: AsyncSession = Depends(get_db)):
    pdf = await service.certificate_pdf(db, user.organization_id, enrolment_id)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="certificate.pdf"'})


@router.get("/summary")
async def summary(start_date: date = Query(...), end_date: date = Query(...), user: User = Depends(R), db: AsyncSession = Depends(get_db)):
    return await service.summary(db, user.organization_id, start_date, end_date)

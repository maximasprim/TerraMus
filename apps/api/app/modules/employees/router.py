import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.employees import schemas, service

router = APIRouter(prefix="/api/v1/employees", tags=["employees"])


@router.get("", response_model=list[schemas.EmployeeOut])
async def list_employees(
    employment_status: str | None = Query(None),
    department: str | None = Query(None),
    assigned_farm_id: uuid.UUID | None = Query(None),
    search: str | None = Query(None),
    user: User = Depends(require_permission("employees.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_employees(db, user.organization_id, employment_status, department, assigned_farm_id, search)


@router.post("", response_model=schemas.EmployeeOut, status_code=201)
async def create_employee(
    req: schemas.EmployeeCreate,
    user: User = Depends(require_permission("employees.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_employee(db, user.organization_id, req)


@router.get("/{employee_id}", response_model=schemas.EmployeeDetailOut)
async def get_employee(
    employee_id: uuid.UUID,
    user: User = Depends(require_permission("employees.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_employee_detail(db, user.organization_id, employee_id)


@router.patch("/{employee_id}", response_model=schemas.EmployeeOut)
async def update_employee(
    employee_id: uuid.UUID,
    req: schemas.EmployeeUpdate,
    user: User = Depends(require_permission("employees.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_employee(db, user.organization_id, employee_id, req)


@router.patch("/{employee_id}/status", response_model=schemas.EmployeeOut)
async def update_employment_status(
    employee_id: uuid.UUID,
    req: schemas.EmployeeStatusUpdate,
    user: User = Depends(require_permission("employees.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_employment_status(db, user.organization_id, employee_id, user.id, req)


@router.get("/{employee_id}/shifts", response_model=list[schemas.WorkShiftOut])
async def list_shifts(
    employee_id: uuid.UUID,
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    user: User = Depends(require_permission("employees.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_shifts(db, user.organization_id, employee_id, from_date, to_date)


@router.post("/{employee_id}/shifts", response_model=schemas.WorkShiftOut, status_code=201)
async def create_shift(
    employee_id: uuid.UUID,
    req: schemas.WorkShiftCreate,
    user: User = Depends(require_permission("employees.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_shift(db, user.organization_id, employee_id, req)

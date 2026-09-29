import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import User
from app.modules.employees.models import (
    Employee, EmployeeStatusEvent, WorkShift, EmployeeCounter, _STATUS_TRANSITIONS,
)
from app.modules.employees import schemas


async def _next_employee_number(db: AsyncSession, org_id: uuid.UUID) -> str:
    """Row-locked per-org counter - same mechanism as finance.InvoiceCounter /
    procurement.PurchaseOrderCounter."""
    result = await db.execute(
        select(EmployeeCounter).where(EmployeeCounter.organization_id == org_id).with_for_update()
    )
    counter = result.scalar_one_or_none()
    if not counter:
        counter = EmployeeCounter(organization_id=org_id, next_number=1)
        db.add(counter)
        await db.flush()
    number = counter.next_number
    counter.next_number += 1
    from app.modules.identity.service import get_organization
    org = await get_organization(db, org_id)
    return f"{org.employee_prefix}-{number:06d}"  # spec §60 - prefix is now org-configurable


async def create_employee(db: AsyncSession, org_id: uuid.UUID, req: schemas.EmployeeCreate) -> Employee:
    if req.user_id is not None:
        user = await db.execute(select(User).where(User.id == req.user_id, User.organization_id == org_id))
        if not user.scalar_one_or_none():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found in this organization")

    employee_number = await _next_employee_number(db, org_id)
    employee = Employee(organization_id=org_id, employee_number=employee_number, **req.model_dump())
    db.add(employee)
    await db.commit()
    await db.refresh(employee)
    return employee


async def get_employee(db: AsyncSession, org_id: uuid.UUID, employee_id: uuid.UUID) -> Employee:
    result = await db.execute(
        select(Employee).where(Employee.id == employee_id, Employee.organization_id == org_id)
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    return employee


async def get_employee_detail(db: AsyncSession, org_id: uuid.UUID, employee_id: uuid.UUID) -> schemas.EmployeeDetailOut:
    employee = await get_employee(db, org_id, employee_id)
    history = await db.execute(
        select(EmployeeStatusEvent)
        .where(EmployeeStatusEvent.employee_id == employee_id)
        .order_by(EmployeeStatusEvent.changed_at)
    )
    return schemas.EmployeeDetailOut(
        **schemas.EmployeeOut.model_validate(employee).model_dump(),
        status_history=list(history.scalars().all()),
    )


async def list_employees(
    db: AsyncSession, org_id: uuid.UUID, employment_status: str | None = None,
    department: str | None = None, assigned_farm_id: uuid.UUID | None = None, search: str | None = None,
) -> list[Employee]:
    query = select(Employee).where(Employee.organization_id == org_id)
    if employment_status:
        query = query.where(Employee.employment_status == employment_status)
    if department:
        query = query.where(Employee.department == department)
    if assigned_farm_id:
        query = query.where(Employee.assigned_farm_id == assigned_farm_id)
    if search:
        like = f"%{search}%"
        query = query.where(
            (Employee.full_name.ilike(like))
            | (Employee.employee_number.ilike(like))
            | (Employee.phone.ilike(like))
        )
    result = await db.execute(query.order_by(Employee.full_name))
    return list(result.scalars().all())


async def update_employee(
    db: AsyncSession, org_id: uuid.UUID, employee_id: uuid.UUID, req: schemas.EmployeeUpdate,
) -> Employee:
    employee = await get_employee(db, org_id, employee_id)
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(employee, field, value)
    await db.commit()
    await db.refresh(employee)
    return employee


async def update_employment_status(
    db: AsyncSession, org_id: uuid.UUID, employee_id: uuid.UUID, user_id: uuid.UUID,
    req: schemas.EmployeeStatusUpdate,
) -> Employee:
    employee = await get_employee(db, org_id, employee_id)

    allowed = _STATUS_TRANSITIONS.get(employee.employment_status, set())
    if req.status == employee.employment_status:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Employee is already in that status")
    if req.status not in allowed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot transition employee from '{employee.employment_status}' to '{req.status}'",
        )

    previous_status = employee.employment_status
    employee.employment_status = req.status
    if req.status == "terminated":
        employee.termination_date = req.effective_date or date.today()

    db.add(EmployeeStatusEvent(
        employee_id=employee.id, from_status=previous_status, to_status=req.status,
        reason=req.reason, changed_by=user_id, changed_at=datetime.now(timezone.utc),
    ))
    await db.commit()
    await db.refresh(employee)
    return employee


# ---- Work shifts (spec §27 "work schedules" - a lightweight rota, not full
# attendance/scheduling; see models.py docstring) ----------------------------

async def create_shift(
    db: AsyncSession, org_id: uuid.UUID, employee_id: uuid.UUID, req: schemas.WorkShiftCreate,
) -> WorkShift:
    await get_employee(db, org_id, employee_id)  # 404s if not in this org
    shift = WorkShift(employee_id=employee_id, **req.model_dump())
    db.add(shift)
    await db.commit()
    await db.refresh(shift)
    return shift


async def list_shifts(
    db: AsyncSession, org_id: uuid.UUID, employee_id: uuid.UUID,
    from_date: date | None = None, to_date: date | None = None,
) -> list[WorkShift]:
    await get_employee(db, org_id, employee_id)
    query = select(WorkShift).where(WorkShift.employee_id == employee_id)
    if from_date:
        query = query.where(WorkShift.shift_date >= from_date)
    if to_date:
        query = query.where(WorkShift.shift_date <= to_date)
    result = await db.execute(query.order_by(WorkShift.shift_date))
    return list(result.scalars().all())

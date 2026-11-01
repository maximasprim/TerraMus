"""Light-weight helpers every module can import without import cycles (this file imports no service code).

  * CycleSel / cycle_filter  - the shared `production_cycle_id` query parameter
  * apply_col                - filter a plain `production_cycle_id` column
  * ensure_writable          - validate a cycle a user is explicitly assigning a NEW record to
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cycles.models import ProductionCycle

UNASSIGNED = "unassigned"


@dataclass(frozen=True)
class CycleSel:
    """id=None means 'records that belong to no cycle'."""
    id: uuid.UUID | None

    @property
    def unassigned(self) -> bool:
        return self.id is None


def parse_cycle(value: str | None) -> CycleSel | None:
    if value is None or value == "" or value.lower() == "all":
        return None
    if value.lower() == UNASSIGNED:
        return CycleSel(None)
    try:
        return CycleSel(uuid.UUID(value))
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "production_cycle_id must be a cycle id, 'unassigned' or 'all'")


def cycle_filter(production_cycle_id: str | None = Query(
        None, description="Limit to one production cycle (its id), to records in no cycle ('unassigned'), or all ('all'/omitted)")
                 ) -> CycleSel | None:
    return parse_cycle(production_cycle_id)


def apply_col(query, column, sel: CycleSel | None):
    """Add the cycle condition for a plain nullable cycle column. No selection = query unchanged."""
    if sel is None:
        return query
    return query.where(column.is_(None)) if sel.unassigned else query.where(column == sel.id)


def cond(column, sel: CycleSel):
    return column.is_(None) if sel.unassigned else column == sel.id


async def get_cycle(db: AsyncSession, org_id: uuid.UUID, cycle_id: uuid.UUID) -> ProductionCycle:
    c = (await db.execute(select(ProductionCycle).where(ProductionCycle.id == cycle_id,
                                                        ProductionCycle.organization_id == org_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production cycle not found")
    return c


async def ensure_writable(db: AsyncSession, org_id: uuid.UUID, cycle_id: uuid.UUID | None) -> ProductionCycle | None:
    """For a user explicitly putting a NEW record into a cycle: it must exist in this organisation and
    must not be closed (a closed cycle's books are frozen until someone reopens it). None -> no cycle."""
    if cycle_id is None:
        return None
    c = await get_cycle(db, org_id, cycle_id)
    if c.status == "closed":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Production cycle '{c.name}' is closed. Reopen it before adding records to it.")
    return c

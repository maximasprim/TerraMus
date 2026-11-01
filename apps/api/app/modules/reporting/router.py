import csv
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.livestock.models import Animal
from app.modules.crops import economics as crop_economics
from app.modules.crops.economics_schemas import CropEconomicsReport
from app.modules.reporting import analytics, analytics_schemas, schemas, service
from app.modules.cycles import resolve as cyc_resolve
from app.modules.cycles.deps import CycleSel, cycle_filter

router = APIRouter(prefix="/api/v1/reports", tags=["reporting"])


@router.get("/dashboard", response_model=schemas.DashboardSummary)
async def dashboard(
    user: User = Depends(require_permission("reports.view")),
    db: AsyncSession = Depends(get_db),
    cycle: CycleSel | None = Depends(cycle_filter),
):
    return await service.dashboard_summary(db, user.organization_id, cycle)


@router.get("/analytics", response_model=analytics_schemas.AnalyticsReport)
async def analytics_report(
    months: int = Query(6, ge=1, le=24, description="How many calendar months to chart, ending with the current one"),
    user: User = Depends(require_permission("reports.view")),
    db: AsyncSession = Depends(get_db),
    cycle: CycleSel | None = Depends(cycle_filter),
):
    """Chart-ready aggregates (finance, sales, herd, dairy, crops, inventory, health)
    for the dashboard and the reports page. Read-only; scoped to the caller's org."""
    return await analytics.analytics_report(db, user.organization_id, months, cycle)


@router.get("/profitability", response_model=schemas.ProfitabilityReport)
async def profitability(
    user: User = Depends(require_permission("reports.view")),
    db: AsyncSession = Depends(get_db),
    cycle: CycleSel | None = Depends(cycle_filter),
):
    return await service.profitability_report(db, user.organization_id, cycle)


@router.get("/profitability/crops", response_model=CropEconomicsReport)
async def crops_profitability(
    user: User = Depends(require_permission("reports.view")),
    db: AsyncSession = Depends(get_db),
    cycle: CycleSel | None = Depends(cycle_filter),
):
    """Per-planting cost, revenue (web orders + sales made off the web) and profit so far."""
    return await crop_economics.all_economics(db, user.organization_id, cycle)


@router.get("/profitability/animals/{animal_id}", response_model=schemas.AnimalProfitabilityBreakdown)
async def animal_profitability(
    animal_id: uuid.UUID,
    user: User = Depends(require_permission("reports.view")),
    db: AsyncSession = Depends(get_db),
):
    """One animal line by line: what was used, what came back (or was lost)."""
    breakdown = await service.animal_profitability_breakdown(db, user.organization_id, animal_id)
    if breakdown is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Animal not found")
    return breakdown


@router.get("/export/livestock.csv")
async def export_livestock_csv(
    user: User = Depends(require_permission("reports.view")),
    db: AsyncSession = Depends(get_db),
    cycle: CycleSel | None = Depends(cycle_filter),
):
    """Spec §44 - CSV export. Excel (.xlsx) export is still deferred - no
    spreadsheet-writing dependency exists in this build yet - but PDF export
    is now available at the sibling `.pdf` endpoint below (this session)."""
    aq = select(Animal).where(Animal.organization_id == user.organization_id)
    if cycle is not None:
        aq = aq.where(Animal.id.in_(cyc_resolve.animal_ids_in(user.organization_id, cycle)))
    result = await db.execute(aq)
    animals = result.scalars().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "animal_number", "ear_tag", "species", "breed", "category", "sex", "status",
        "health_status", "current_weight", "acquisition_date", "acquisition_cost",
        "expected_sale_price", "current_value",
    ])
    for a in animals:
        writer.writerow([
            a.animal_number, a.ear_tag or "", a.species, a.breed or "", a.category or "", a.sex, a.status,
            a.health_status, a.current_weight or "", a.acquisition_date, a.acquisition_cost,
            a.expected_sale_price or "", a.current_value or "",
        ])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=livestock_export.csv"},
    )


@router.get("/export/livestock.pdf")
async def export_livestock_pdf(
    user: User = Depends(require_permission("reports.view")),
    db: AsyncSession = Depends(get_db),
    cycle: CycleSel | None = Depends(cycle_filter),
):
    """Spec §44 PDF export, added this session - see
    docs/architecture.md for the reportlab dependency's verification-status
    caveat (written/reviewed, not run - same as finance/pdf.py)."""
    from fastapi.responses import Response
    from app.modules.identity.models import Organization
    pdf_bytes = await service.render_livestock_report_pdf(db, user.organization_id, cycle)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=livestock_report.pdf"},
    )

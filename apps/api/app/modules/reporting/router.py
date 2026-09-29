import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.livestock.models import Animal
from app.modules.reporting import schemas, service

router = APIRouter(prefix="/api/v1/reports", tags=["reporting"])


@router.get("/dashboard", response_model=schemas.DashboardSummary)
async def dashboard(
    user: User = Depends(require_permission("reports.view")),
    db: AsyncSession = Depends(get_db),
):
    return await service.dashboard_summary(db, user.organization_id)


@router.get("/profitability", response_model=schemas.ProfitabilityReport)
async def profitability(
    user: User = Depends(require_permission("reports.view")),
    db: AsyncSession = Depends(get_db),
):
    return await service.profitability_report(db, user.organization_id)


@router.get("/export/livestock.csv")
async def export_livestock_csv(
    user: User = Depends(require_permission("reports.view")),
    db: AsyncSession = Depends(get_db),
):
    """Spec §44 - CSV export. Excel (.xlsx) export is still deferred - no
    spreadsheet-writing dependency exists in this build yet - but PDF export
    is now available at the sibling `.pdf` endpoint below (this session)."""
    result = await db.execute(select(Animal).where(Animal.organization_id == user.organization_id))
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
):
    """Spec §44 PDF export, added this session - see
    docs/architecture.md for the reportlab dependency's verification-status
    caveat (written/reviewed, not run - same as finance/pdf.py)."""
    from fastapi.responses import Response
    from app.modules.identity.models import Organization
    pdf_bytes = await service.render_livestock_report_pdf(db, user.organization_id)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=livestock_report.pdf"},
    )

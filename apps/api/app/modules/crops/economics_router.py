import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.crops import economics, economics_schemas as schemas
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User

# Registered BEFORE the main crops router so these fixed paths are never mistaken for /{planting_id}.
router = APIRouter(prefix="/api/v1/crops", tags=["crops"])

MAX_IMPORT_BYTES = 5 * 1024 * 1024


async def _read_upload(file: UploadFile) -> bytes:
    content = await file.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is larger than 5 MB")
    return content


@router.post("/sales/import", response_model=schemas.CropImportResult)
async def import_sales(
    file: UploadFile = File(...),
    dry_run: bool = Query(True, description="Preview only: shows what would be created and saves nothing."),
    post_to_finance: bool = Query(True, description="Also record each sale in Finance (once only)."),
    user: User = Depends(require_permission("crops.update")),
    db: AsyncSession = Depends(get_db),
):
    """Sales made outside the web shop, from a spreadsheet (.xlsx) or CSV. Columns: planting_number, date, quantity,
    unit (optional), unit_price or amount, buyer (optional), notes (optional). Importing the same file again adds nothing."""
    return await economics.import_rows(db, user.organization_id, user.id, kind="sales", content=await _read_upload(file),
                                       filename=file.filename or "", dry_run=dry_run, post_to_finance=post_to_finance)


@router.post("/costs/import", response_model=schemas.CropImportResult)
async def import_costs(
    file: UploadFile = File(...),
    dry_run: bool = Query(True),
    post_to_finance: bool = Query(True),
    user: User = Depends(require_permission("crops.update")),
    db: AsyncSession = Depends(get_db),
):
    """Costs per planting, from a spreadsheet or CSV. Columns: planting_number, date, category, amount, notes (optional)."""
    return await economics.import_rows(db, user.organization_id, user.id, kind="costs", content=await _read_upload(file),
                                       filename=file.filename or "", dry_run=dry_run, post_to_finance=post_to_finance)


@router.post("/ledger-sync")
async def sync_ledger(
    dry_run: bool = Query(True, description="Preview only. Set false to post."),
    confirm_overlap: bool = Query(False, description="Post even though Finance holds hand-typed crops entries."),
    user: User = Depends(require_permission("crops.update")),
    db: AsyncSession = Depends(get_db),
):
    """Catch-up: books crop sales, costs and planting purchase costs that exist but never reached Finance. Each is
    posted at most once, so it is safe to repeat; it refuses to post over hand-typed crops entries in Finance unless
    you confirm they are different."""
    return await economics.reconcile(db, user.organization_id, user.id, dry_run=dry_run, confirm_overlap=confirm_overlap)


@router.post("/sales/{sale_id}/void", response_model=schemas.CropSaleOut)
async def void_sale(
    sale_id: uuid.UUID, req: schemas.VoidRequest,
    user: User = Depends(require_permission("crops.update")), db: AsyncSession = Depends(get_db),
):
    """Correct a wrong sale: it is kept (flagged, with the reason) and its Finance entry is reversed."""
    return await economics.void_sale(db, user.organization_id, user.id, sale_id, req.reason)


@router.post("/costs/{cost_id}/void", response_model=schemas.CropCostOut)
async def void_cost(
    cost_id: uuid.UUID, req: schemas.VoidRequest,
    user: User = Depends(require_permission("crops.update")), db: AsyncSession = Depends(get_db),
):
    return await economics.void_cost(db, user.organization_id, user.id, cost_id, req.reason)


@router.post("/{planting_id}/sales", response_model=schemas.CropSaleResult, status_code=status.HTTP_201_CREATED)
async def add_sale(
    planting_id: uuid.UUID, req: schemas.CropSaleCreate,
    user: User = Depends(require_permission("crops.update")), db: AsyncSession = Depends(get_db),
):
    return await economics.record_sale(db, user.organization_id, user.id, planting_id, req)


@router.get("/{planting_id}/sales", response_model=list[schemas.CropSaleOut])
async def list_sales(
    planting_id: uuid.UUID, user: User = Depends(require_permission("crops.read")), db: AsyncSession = Depends(get_db),
):
    return await economics.list_sales(db, user.organization_id, planting_id)


@router.post("/{planting_id}/costs", response_model=schemas.CropCostOut, status_code=status.HTTP_201_CREATED)
async def add_cost(
    planting_id: uuid.UUID, req: schemas.CropCostCreate,
    user: User = Depends(require_permission("crops.update")), db: AsyncSession = Depends(get_db),
):
    return await economics.record_cost(db, user.organization_id, user.id, planting_id, req)


@router.get("/{planting_id}/costs", response_model=list[schemas.CropCostOut])
async def list_costs(
    planting_id: uuid.UUID, user: User = Depends(require_permission("crops.read")), db: AsyncSession = Depends(get_db),
):
    return await economics.list_costs(db, user.organization_id, planting_id)


@router.get("/{planting_id}/economics", response_model=schemas.PlantingBreakdown)
async def planting_economics(
    planting_id: uuid.UUID, user: User = Depends(require_permission("crops.read")), db: AsyncSession = Depends(get_db),
):
    """One planting line by line: what it cost, what it sold for (web and direct), stock left, profit so far."""
    return await economics.planting_breakdown(db, user.organization_id, planting_id)

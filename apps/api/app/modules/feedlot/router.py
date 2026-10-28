import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.feedlot import schemas, service
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User

router = APIRouter(prefix="/api/v1/feedlot", tags=["feedlot"])


# ---- intake batches
@router.get("/intake-batches", response_model=list[schemas.IntakeBatchOut])
async def list_intake_batches(user: User = Depends(require_permission("feedlot.read")), db: AsyncSession = Depends(get_db)):
    return await service.list_intake_batches(db, user.organization_id)


@router.post("/intake-batches", response_model=schemas.IntakeBatchOut, status_code=201)
async def create_intake_batch(req: schemas.IntakeBatchCreate, user: User = Depends(require_permission("feedlot.manage")),
                              db: AsyncSession = Depends(get_db)):
    return await service.create_intake_batch(db, user.organization_id, req)


@router.patch("/intake-batches/{batch_id}", response_model=schemas.IntakeBatchOut)
async def update_intake_batch(batch_id: uuid.UUID, req: schemas.IntakeBatchUpdate,
                              user: User = Depends(require_permission("feedlot.manage")), db: AsyncSession = Depends(get_db)):
    return await service.update_intake_batch(db, user.organization_id, batch_id, req)


@router.delete("/intake-batches/{batch_id}", status_code=204)
async def delete_intake_batch(batch_id: uuid.UUID, user: User = Depends(require_permission("feedlot.manage")),
                              db: AsyncSession = Depends(get_db)):
    await service.delete_intake_batch(db, user.organization_id, batch_id)


@router.post("/intake-batches/{batch_id}/animals", status_code=201)
async def register_animals(batch_id: uuid.UUID, req: schemas.RegisterAnimalsRequest,
                           user: User = Depends(require_permission("feedlot.manage")), db: AsyncSession = Depends(get_db)):
    batch = await service.get_intake_batch(db, user.organization_id, batch_id)
    return await service.register_batch_animals(db, user.organization_id, user.id, batch, req)


@router.post("/intake-batches/{batch_id}/link")
async def link_animals(batch_id: uuid.UUID, req: schemas.LinkExistingRequest,
                       user: User = Depends(require_permission("feedlot.manage")), db: AsyncSession = Depends(get_db)):
    batch = await service.get_intake_batch(db, user.organization_id, batch_id)
    return await service.link_existing_animals(db, user.organization_id, batch, req)


# ---- sale batches
@router.get("/sale-batches", response_model=list[schemas.SaleBatchOut])
async def list_sale_batches(user: User = Depends(require_permission("feedlot.read")), db: AsyncSession = Depends(get_db)):
    return await service.list_sale_batches(db, user.organization_id)


@router.post("/sale-batches", response_model=schemas.SaleBatchOut, status_code=201)
async def create_sale_batch(req: schemas.SaleBatchCreate, user: User = Depends(require_permission("livestock.sell")),
                            db: AsyncSession = Depends(get_db)):
    return await service.create_sale_batch(db, user.organization_id, req)


@router.patch("/sale-batches/{batch_id}", response_model=schemas.SaleBatchOut)
async def update_sale_batch(batch_id: uuid.UUID, req: schemas.SaleBatchUpdate,
                            user: User = Depends(require_permission("livestock.sell")), db: AsyncSession = Depends(get_db)):
    return await service.update_sale_batch(db, user.organization_id, batch_id, req)


@router.post("/sale-batches/{batch_id}/sales")
async def record_batch_sales(batch_id: uuid.UUID, req: schemas.BatchSaleRequest,
                             user: User = Depends(require_permission("livestock.sell")), db: AsyncSession = Depends(get_db)):
    batch = await service.get_sale_batch(db, user.organization_id, batch_id)
    return await service.record_batch_sales(db, user.organization_id, user.id, batch, req)


# ---- single-animal exits
@router.post("/animals/{animal_id}/sale", status_code=201)
async def sell_animal(animal_id: uuid.UUID, req: schemas.SaleRequest,
                      user: User = Depends(require_permission("livestock.sell")), db: AsyncSession = Depends(get_db)):
    animal = await service._resolve_animal(db, user.organization_id, animal_id=animal_id)
    if not animal:
        raise service._404("Animal")
    batch = await service.get_sale_batch(db, user.organization_id, req.sale_batch_id) if req.sale_batch_id else None
    ex = await service.record_sale(db, user.organization_id, user.id, animal, exit_date=req.exit_date,
                                   weight=req.exit_weight_kg, price=req.price_per_kg, sale_batch=batch,
                                   customer_id=req.customer_id, salesperson=req.salesperson)
    return {"animal_id": str(animal.id), "amount": float(ex.amount), "price_per_kg": float(ex.price_per_kg)}


@router.post("/animals/{animal_id}/cull", status_code=201)
async def cull_animal(animal_id: uuid.UUID, req: schemas.CullRequest,
                      user: User = Depends(require_permission("feedlot.manage")), db: AsyncSession = Depends(get_db)):
    animal = await service._resolve_animal(db, user.organization_id, animal_id=animal_id)
    if not animal:
        raise service._404("Animal")
    ex = await service.record_cull(db, user.organization_id, user.id, animal, req)
    return {"animal_id": str(animal.id), "exit_type": ex.exit_type}


# ---- weigh days
@router.post("/weigh-days", status_code=201)
async def record_weigh_day(req: schemas.BulkWeighRequest, user: User = Depends(require_permission("feedlot.weigh")),
                           db: AsyncSession = Depends(get_db)):
    return await service.bulk_weigh(db, user.organization_id, user.id, req)


@router.get("/weigh-days")
async def list_weigh_days(user: User = Depends(require_permission("feedlot.read")), db: AsyncSession = Depends(get_db)):
    return await service.list_weigh_sessions(db, user.organization_id)


# ---- analytics
@router.get("/performance")
async def performance(as_of: date | None = Query(None), intake_batch_id: uuid.UUID | None = Query(None),
                      sale_batch_id: uuid.UUID | None = Query(None), state: str | None = Query(None, pattern="^(active|sold|culled|died)$"),
                      user: User = Depends(require_permission("feedlot.read")), db: AsyncSession = Depends(get_db)):
    return await service.performance(db, user.organization_id, as_of, intake_batch_id, sale_batch_id, state)


@router.get("/profitability")
async def profitability(as_of: date | None = Query(None), intake_batch_id: uuid.UUID | None = Query(None),
                        sale_batch_id: uuid.UUID | None = Query(None),
                        user: User = Depends(require_permission("feedlot.read")), db: AsyncSession = Depends(get_db)):
    return await service.profitability(db, user.organization_id, as_of, intake_batch_id, sale_batch_id)


# ---- costing documents
@router.get("/costing", response_model=list[schemas.CostingDocumentOut])
async def list_costing(kind: str | None = Query(None), user: User = Depends(require_permission("feedlot.read")),
                       db: AsyncSession = Depends(get_db)):
    return await service.list_costing_docs(db, user.organization_id, kind)


@router.post("/costing", response_model=schemas.CostingDocumentOut, status_code=201)
async def create_costing(req: schemas.CostingDocumentCreate, user: User = Depends(require_permission("feedlot.manage")),
                         db: AsyncSession = Depends(get_db)):
    return await service.create_costing_doc(db, user.organization_id, req)


@router.patch("/costing/{doc_id}", response_model=schemas.CostingDocumentOut)
async def update_costing(doc_id: uuid.UUID, req: schemas.CostingDocumentUpdate,
                         user: User = Depends(require_permission("feedlot.manage")), db: AsyncSession = Depends(get_db)):
    return await service.update_costing_doc(db, user.organization_id, doc_id, req)


@router.delete("/costing/{doc_id}", status_code=204)
async def delete_costing(doc_id: uuid.UUID, user: User = Depends(require_permission("feedlot.manage")),
                         db: AsyncSession = Depends(get_db)):
    await service.delete_costing_doc(db, user.organization_id, doc_id)


# ---- worksheet import / export (Sahara Oasis "Bulls WG Worksheet" format)
from fastapi import File, HTTPException, UploadFile  # noqa: E402

MAX_WORKSHEET_BYTES = 15 * 1024 * 1024


@router.post("/worksheet/import")
async def import_worksheet(
    file: UploadFile = File(...),
    dry_run: bool = Query(True, description="Preview only: nothing is saved. Set false to commit."),
    farm_id: uuid.UUID | None = Query(None),
    include_costing: bool = Query(True),
    post_to_finance: bool = Query(True, description="Also record the NEW sales and purchases in Finance (each at most once)."),
    user: User = Depends(require_permission("feedlot.manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.modules.feedlot.worksheet_import import import_worksheet as run_import
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Upload an Excel .xlsx workbook")
    content = await file.read(MAX_WORKSHEET_BYTES + 1)
    if len(content) > MAX_WORKSHEET_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Workbook is larger than 15 MB")
    return await run_import(db, user.organization_id, user.id, content, farm_id=farm_id,
                            dry_run=dry_run, include_costing=include_costing, post_to_finance=post_to_finance)


@router.post("/ledger-sync")
async def sync_ledger(
    dry_run: bool = Query(True, description="Preview only: shows what would be posted. Set false to post."),
    include_purchases: bool = Query(True, description="Also book purchase costs of feedlot animals."),
    confirm_overlap: bool = Query(False, description="Post even though Finance already holds manually typed entries of the same kind."),
    user: User = Depends(require_permission("feedlot.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Catch-up: books feedlot sales/purchases that exist but never reached Finance (for example
    worksheets imported before the importer posted to Finance). Each sale/purchase is posted at most
    once, so this is safe to repeat; it refuses to apply over manually typed Finance entries of the
    same kind unless you confirm they are different."""
    from app.modules.feedlot import ledger_sync
    return await ledger_sync.reconcile(db, user.organization_id, user.id, dry_run=dry_run,
                                       include_purchases=include_purchases, confirm_overlap=confirm_overlap)


@router.get("/worksheet/export")
async def export_worksheet(
    as_of: date | None = Query(None, description="Report as at this date (default: latest weigh/sale date)"),
    user: User = Depends(require_permission("feedlot.read")),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response
    from app.modules.feedlot.worksheet_export import export_worksheet as build
    content, meta = await build(db, user.organization_id, as_of)
    name = f"Bulls_WG_Worksheet_{meta['as_of']}.xlsx"
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "X-Worksheet-As-Of": meta["as_of"]})

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.modules.procurement.models import (
    Supplier, PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatusEvent, PurchaseOrderCounter,
)
from app.modules.procurement import schemas
from app.modules.inventory import schemas as inventory_schemas
from app.modules.inventory.service import record_movement as record_stock_movement

# Spec §26: REQUEST -> APPROVAL -> PURCHASE ORDER -> RECEIVED -> INVOICED -> PAID.
# Same shape as commerce._ORDER_TRANSITIONS / livestock._ALLOWED_TRANSITIONS:
# an explicit table the router/service enforce, never a hard-coded if-chain.
_PO_TRANSITIONS: dict[str, set[str]] = {
    "requested": {"approved", "rejected", "cancelled"},
    "approved": {"ordered", "cancelled"},
    "ordered": {"received", "cancelled"},
    "received": {"invoiced"},
    "invoiced": {"paid"},
    "paid": set(),
    "rejected": set(),
    "cancelled": set(),
}


# ---- Suppliers -------------------------------------------------------------

async def create_supplier(db: AsyncSession, org_id: uuid.UUID, req: schemas.SupplierCreate) -> Supplier:
    supplier = Supplier(organization_id=org_id, **req.model_dump())
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return supplier


async def get_supplier(db: AsyncSession, org_id: uuid.UUID, supplier_id: uuid.UUID) -> Supplier:
    result = await db.execute(
        select(Supplier).where(Supplier.id == supplier_id, Supplier.organization_id == org_id)
    )
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier not found")
    return supplier


async def list_suppliers(
    db: AsyncSession, org_id: uuid.UUID, is_active: bool | None = None, search: str | None = None,
) -> list[Supplier]:
    query = select(Supplier).where(Supplier.organization_id == org_id)
    if is_active is not None:
        query = query.where(Supplier.is_active == is_active)
    if search:
        like = f"%{search}%"
        query = query.where((Supplier.name.ilike(like)) | (Supplier.email.ilike(like)) | (Supplier.phone.ilike(like)))
    result = await db.execute(query.order_by(Supplier.name))
    return list(result.scalars().all())


async def update_supplier(
    db: AsyncSession, org_id: uuid.UUID, supplier_id: uuid.UUID, req: schemas.SupplierUpdate,
) -> Supplier:
    supplier = await get_supplier(db, org_id, supplier_id)
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(supplier, field, value)
    await db.commit()
    await db.refresh(supplier)
    return supplier


# ---- Purchase orders --------------------------------------------------------

async def _next_po_number(db: AsyncSession, org_id: uuid.UUID) -> str:
    """Row-locked per-org counter - identical pattern to
    finance.service._next_invoice_number."""
    result = await db.execute(
        select(PurchaseOrderCounter).where(PurchaseOrderCounter.organization_id == org_id).with_for_update()
    )
    counter = result.scalar_one_or_none()
    if not counter:
        counter = PurchaseOrderCounter(organization_id=org_id, next_number=1)
        db.add(counter)
        await db.flush()
    number = counter.next_number
    counter.next_number += 1
    from app.modules.identity.service import get_organization
    org = await get_organization(db, org_id)
    return f"{org.po_prefix}-{number:06d}"  # spec §60 - prefix is now org-configurable


def _total(items: list[PurchaseOrderItem] | list[schemas.PurchaseOrderItemCreate]) -> Decimal:
    # Quantized to money precision explicitly: unlike inventory's current_stock
    # (a DB Numeric(12,2) column with a guaranteed scale), this total is
    # computed in Python from arbitrary-exponent Decimal inputs, so left
    # unquantized it could serialize as e.g. "450" or "450.0000" depending on
    # the exponents of the multiplied operands.
    total = sum((Decimal(str(i.quantity)) * Decimal(str(i.unit_cost)) for i in items), Decimal("0"))
    return total.quantize(Decimal("0.01"))


def _to_out(po: PurchaseOrder) -> schemas.PurchaseOrderOut:
    # total_amount is derived, not stored (same reasoning as inventory's
    # current_stock - a stored total could drift from its line items).
    return schemas.PurchaseOrderOut(
        id=po.id, organization_id=po.organization_id, supplier_id=po.supplier_id,
        po_number=po.po_number, status=po.status, order_date=po.order_date,
        expected_delivery_date=po.expected_delivery_date, notes=po.notes,
        requested_by=po.requested_by, approved_by=po.approved_by,
        total_amount=_total(po.items), items=list(po.items), created_at=po.created_at,
    )


async def create_purchase_order(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, req: schemas.PurchaseOrderCreate,
) -> schemas.PurchaseOrderOut:
    await get_supplier(db, org_id, req.supplier_id)  # 404s if it doesn't belong to this org

    po_number = await _next_po_number(db, org_id)
    po = PurchaseOrder(
        organization_id=org_id, supplier_id=req.supplier_id, po_number=po_number,
        status="requested", expected_delivery_date=req.expected_delivery_date,
        notes=req.notes, requested_by=user_id,
    )
    db.add(po)
    await db.flush()
    for item in req.items:
        db.add(PurchaseOrderItem(
            purchase_order_id=po.id, inventory_item_id=item.inventory_item_id,
            description=item.description, quantity=item.quantity, unit_cost=item.unit_cost,
        ))
    db.add(PurchaseOrderStatusEvent(
        purchase_order_id=po.id, from_status=None, to_status="requested",
        changed_by=user_id, changed_at=datetime.now(timezone.utc),
    ))
    await db.commit()
    await db.refresh(po)
    return _to_out(po)


async def get_purchase_order(db: AsyncSession, org_id: uuid.UUID, po_id: uuid.UUID) -> PurchaseOrder:
    result = await db.execute(
        select(PurchaseOrder).where(PurchaseOrder.id == po_id, PurchaseOrder.organization_id == org_id)
    )
    po = result.scalar_one_or_none()
    if not po:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Purchase order not found")
    return po


async def get_purchase_order_detail(db: AsyncSession, org_id: uuid.UUID, po_id: uuid.UUID) -> schemas.PurchaseOrderDetailOut:
    po = await get_purchase_order(db, org_id, po_id)
    history = await db.execute(
        select(PurchaseOrderStatusEvent)
        .where(PurchaseOrderStatusEvent.purchase_order_id == po_id)
        .order_by(PurchaseOrderStatusEvent.changed_at)
    )
    base = _to_out(po)
    return schemas.PurchaseOrderDetailOut(**base.model_dump(), status_history=list(history.scalars().all()))


async def list_purchase_orders(
    db: AsyncSession, org_id: uuid.UUID, status_filter: str | None = None, supplier_id: uuid.UUID | None = None,
) -> list[schemas.PurchaseOrderOut]:
    query = select(PurchaseOrder).where(PurchaseOrder.organization_id == org_id)
    if status_filter:
        query = query.where(PurchaseOrder.status == status_filter)
    if supplier_id:
        query = query.where(PurchaseOrder.supplier_id == supplier_id)
    result = await db.execute(query.order_by(PurchaseOrder.created_at.desc()))
    return [_to_out(po) for po in result.scalars().all()]


async def update_status(
    db: AsyncSession, org_id: uuid.UUID, po_id: uuid.UUID, user_id: uuid.UUID, req: schemas.PurchaseOrderStatusUpdate,
) -> schemas.PurchaseOrderOut:
    po = await get_purchase_order(db, org_id, po_id)

    allowed = _PO_TRANSITIONS.get(po.status, set())
    if req.status == po.status:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Purchase order is already in that status")
    if req.status not in allowed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot transition purchase order from '{po.status}' to '{req.status}'",
        )

    previous_status = po.status
    po.status = req.status
    if req.status == "approved":
        po.approved_by = user_id
    if req.status == "ordered" and not po.order_date:
        po.order_date = date.today()

    db.add(PurchaseOrderStatusEvent(
        purchase_order_id=po.id, from_status=previous_status, to_status=req.status,
        reason=req.reason, changed_by=user_id, changed_at=datetime.now(timezone.utc),
    ))

    # Spec §26 "RECEIVED" step + spec §9 "goods received" - this is the seam
    # that ties Procurement into the Inventory ledger, the same way
    # breeding.service reuses livestock.service.create_animal directly rather
    # than duplicating its logic (see docs/architecture.md shared-kernel note).
    # Only PO lines linked to a tracked InventoryItem create a movement; an
    # untracked line (e.g. a service charge) is received without one.
    if req.status == "received":
        for item in po.items:
            if item.inventory_item_id is None:
                continue
            await record_stock_movement(
                db, org_id, item.inventory_item_id, user_id,
                inventory_schemas.StockMovementCreate(
                    movement_type="purchase", quantity=item.quantity, unit_cost=item.unit_cost,
                    reference=po.po_number, notes=f"Received against {po.po_number}",
                ),
            )
        await publish("PurchaseOrderReceived", {
            "organization_id": str(org_id), "purchase_order_id": str(po.id), "po_number": po.po_number,
        })

    await db.commit()
    await db.refresh(po)
    return _to_out(po)

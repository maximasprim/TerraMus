"""Cross-tenant CRUD for every module besides livestock (which lives in
router.py as the original worked example). Same pattern throughout: each
service function already takes org_id explicitly, so every endpoint here
just resolves org_id from the URL path (behind get_current_platform_admin)
instead of from a tenant's own TenantContext, then calls the identical
service function a normal tenant route would call. No business logic is
duplicated anywhere in this file.

Split into one file rather than folded into router.py purely for length -
router.py already carries the auth/org-management endpoints plus the
livestock example and worked-out reasoning; this file is the mechanical
continuation of that same pattern across the other 13 modules.
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.modules.platform_admin.deps import get_current_platform_admin, require_write_access
from app.modules.platform_admin.models import PlatformAdmin

from app.modules.farm import schemas as farm_schemas
from app.modules.farm.models import Farm, Branch
from app.modules.health import schemas as health_schemas, service as health_service
from app.modules.breeding import schemas as breeding_schemas, service as breeding_service
from app.modules.dairy import schemas as dairy_schemas, service as dairy_service
from app.modules.crops import schemas as crops_schemas, service as crops_service
from app.modules.inventory import schemas as inventory_schemas, service as inventory_service
from app.modules.customers import schemas as customers_schemas, service as customers_service
from app.modules.procurement import schemas as procurement_schemas, service as procurement_service
from app.modules.employees import schemas as employees_schemas, service as employees_service
from app.modules.assets import schemas as assets_schemas, service as assets_service
from app.modules.commerce import schemas as commerce_schemas, service as commerce_service
from app.modules.payments import schemas as payments_schemas, service as payments_service
from app.modules.finance import schemas as finance_schemas, service as finance_service
from app.modules.notifications import schemas as notifications_schemas, service as notifications_service
from app.modules.reporting import schemas as reporting_schemas, service as reporting_service
from app.modules.cms import schemas as cms_schemas, service as cms_service

router = APIRouter(
    prefix="/api/v1/platform/organizations/{org_id}",
    tags=["platform-admin"],
    dependencies=[Depends(require_write_access)],
)

Admin = PlatformAdmin  # local alias for brevity in signatures below


# ------------------------------------------------------------------ farms --
# Added specifically to back the UI's farm/location picker fields (see
# platform-modules.ts and platform-resource-browser.tsx) - before this, the
# UI's create/edit forms had no way to know an org's farm/branch/location
# IDs at all, so relational fields (livestock.farm_id, etc.) could only be
# raw UUID text inputs. Returns the same nested Farm -> Branch -> Location
# shape as the tenant's own GET /api/v1/farms (farm/router.py's list_farms),
# just scoped by org_id from the path instead of the caller's own org.
@router.get("/farms", response_model=list[farm_schemas.FarmOut])
async def list_org_farms(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Farm)
        .options(selectinload(Farm.branches).selectinload(Branch.locations))
        .where(Farm.organization_id == org_id)
    )
    return result.scalars().all()


# ---------------------------------------------------------------- health ---
@router.get("/livestock/{animal_id}/health", response_model=list[health_schemas.HealthRecordOut])
async def list_health_records(org_id: uuid.UUID, animal_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await health_service.list_health_records(db, org_id, animal_id)


@router.post("/livestock/{animal_id}/health", response_model=health_schemas.HealthRecordOut)
async def create_health_record(
    org_id: uuid.UUID, animal_id: uuid.UUID, req: health_schemas.HealthRecordCreate,
    admin: Admin = Depends(get_current_platform_admin), db: AsyncSession = Depends(get_db),
):
    return await health_service.create_health_record(db, org_id, animal_id, admin.id, req)


@router.patch("/health/{record_id}/complete-follow-up", response_model=health_schemas.HealthRecordOut)
async def complete_follow_up(
    org_id: uuid.UUID, record_id: uuid.UUID,
    admin: Admin = Depends(get_current_platform_admin), db: AsyncSession = Depends(get_db),
):
    return await health_service.complete_follow_up(db, org_id, record_id, admin.id)


# -------------------------------------------------------------- breeding ---
@router.post("/breeding", response_model=breeding_schemas.BreedingRecordOut)
async def create_breeding_record(
    org_id: uuid.UUID, req: breeding_schemas.BreedingRecordCreate,
    admin: Admin = Depends(get_current_platform_admin), db: AsyncSession = Depends(get_db),
):
    return await breeding_service.create_breeding_record(db, org_id, admin.id, req)


@router.get("/breeding/{record_id}", response_model=breeding_schemas.BreedingRecordOut)
async def get_breeding_record(org_id: uuid.UUID, record_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await breeding_service.get_breeding_record(db, org_id, record_id)


@router.post("/breeding/{record_id}/pregnancy-checks", response_model=breeding_schemas.BreedingRecordOut)
async def add_pregnancy_check(
    org_id: uuid.UUID, record_id: uuid.UUID, req: breeding_schemas.PregnancyCheckCreate,
    admin: Admin = Depends(get_current_platform_admin), db: AsyncSession = Depends(get_db),
):
    return await breeding_service.add_pregnancy_check(db, org_id, record_id, admin.id, req)


@router.post("/breeding/{record_id}/delivery", response_model=breeding_schemas.BreedingRecordOut)
async def record_delivery(
    org_id: uuid.UUID, record_id: uuid.UUID, req: breeding_schemas.DeliveryRecord,
    admin: Admin = Depends(get_current_platform_admin), db: AsyncSession = Depends(get_db),
):
    return await breeding_service.record_delivery(db, org_id, record_id, admin.id, req)


@router.get("/livestock/{animal_id}/breeding", response_model=list[breeding_schemas.BreedingRecordOut])
async def list_breeding_records_for_animal(org_id: uuid.UUID, animal_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await breeding_service.list_breeding_records_for_animal(db, org_id, animal_id)


# ----------------------------------------------------------------- dairy ---
@router.post("/livestock/{animal_id}/lactation-cycles", response_model=dairy_schemas.LactationCycleOut)
async def start_lactation_cycle(
    org_id: uuid.UUID, animal_id: uuid.UUID, req: dairy_schemas.LactationCycleCreate, db: AsyncSession = Depends(get_db),
):
    return await dairy_service.start_lactation_cycle(db, org_id, animal_id, req)


@router.get("/livestock/{animal_id}/lactation-cycles/active", response_model=dairy_schemas.LactationCycleOut | None)
async def get_active_cycle(org_id: uuid.UUID, animal_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await dairy_service.get_active_cycle(db, org_id, animal_id)


@router.post("/livestock/{animal_id}/dry-off", response_model=dairy_schemas.LactationCycleOut)
async def dry_off(
    org_id: uuid.UUID, animal_id: uuid.UUID, req: dairy_schemas.DryOffRequest, db: AsyncSession = Depends(get_db),
):
    return await dairy_service.dry_off(db, org_id, animal_id, req)


@router.post("/livestock/{animal_id}/milk-records", response_model=dairy_schemas.MilkRecordOut)
async def record_milk(
    org_id: uuid.UUID, animal_id: uuid.UUID, req: dairy_schemas.MilkRecordCreate,
    admin: Admin = Depends(get_current_platform_admin), db: AsyncSession = Depends(get_db),
):
    return await dairy_service.record_milk(db, org_id, animal_id, admin.id, req)


@router.get("/livestock/{animal_id}/milk-records", response_model=list[dairy_schemas.MilkRecordOut])
async def get_animal_production_history(org_id: uuid.UUID, animal_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await dairy_service.get_animal_production_history(db, org_id, animal_id)


@router.get("/dairy/herd-summary", response_model=dairy_schemas.HerdMilkSummary)
async def herd_summary(org_id: uuid.UUID, for_date: date | None = Query(None), db: AsyncSession = Depends(get_db)):
    return await dairy_service.herd_summary(db, org_id, for_date)


# ------------------------------------------------------------------ crops --
# Base crops CRUD (list/get/create/patch/status) lives in router.py, same
# convention as livestock - this file only carries the harvests
# sub-resource, mirroring health/breeding/dairy's per-parent-entity records
# above.
@router.get("/crops/{planting_id}/harvests", response_model=list[crops_schemas.HarvestRecordOut])
async def list_org_crop_harvests(org_id: uuid.UUID, planting_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    planting = await crops_service.get_planting(db, planting_id, org_id)
    return crops_service.compute_harvest_history_with_cumulative(planting.harvests)


@router.post("/crops/{planting_id}/harvests", response_model=crops_schemas.HarvestRecordOut)
async def record_org_crop_harvest(
    org_id: uuid.UUID, planting_id: uuid.UUID, req: crops_schemas.HarvestRecordCreate,
    admin: Admin = Depends(get_current_platform_admin), db: AsyncSession = Depends(get_db),
):
    planting = await crops_service.get_planting(db, planting_id, org_id)
    return await crops_service.record_harvest(db, planting, req, admin.id)


# -------------------------------------------------------------- inventory --
@router.post("/inventory/items", response_model=inventory_schemas.InventoryItemOut)
async def create_item(org_id: uuid.UUID, req: inventory_schemas.InventoryItemCreate, db: AsyncSession = Depends(get_db)):
    return await inventory_service.create_item(db, org_id, req)


@router.get("/inventory/items", response_model=list[inventory_schemas.InventoryItemOut])
async def list_items(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await inventory_service.list_items(db, org_id)


@router.get("/inventory/items/{item_id}")
async def get_item(org_id: uuid.UUID, item_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await inventory_service.get_item(db, org_id, item_id)


@router.post("/inventory/items/{item_id}/movements", response_model=inventory_schemas.StockMovementOut)
async def record_movement(
    org_id: uuid.UUID, item_id: uuid.UUID, req: inventory_schemas.StockMovementCreate,
    admin: Admin = Depends(get_current_platform_admin), db: AsyncSession = Depends(get_db),
):
    return await inventory_service.record_movement(db, org_id, item_id, admin.id, req)


@router.get("/inventory/items/{item_id}/movements", response_model=list[inventory_schemas.StockMovementOut])
async def list_movements(org_id: uuid.UUID, item_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await inventory_service.list_movements(db, org_id, item_id)


# -------------------------------------------------------------- customers --
@router.post("/customers", response_model=customers_schemas.CustomerOut)
async def create_customer(org_id: uuid.UUID, req: customers_schemas.CustomerCreate, db: AsyncSession = Depends(get_db)):
    return await customers_service.create_customer(db, org_id, req)


@router.get("/customers", response_model=list[customers_schemas.CustomerOut])
async def list_customers(org_id: uuid.UUID, search: str | None = Query(None), db: AsyncSession = Depends(get_db)):
    return await customers_service.list_customers(db, org_id, search=search)


@router.get("/customers/{customer_id}", response_model=customers_schemas.CustomerOut)
async def get_customer(org_id: uuid.UUID, customer_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await customers_service.get_customer(db, org_id, customer_id)


@router.patch("/customers/{customer_id}", response_model=customers_schemas.CustomerOut)
async def update_customer(
    org_id: uuid.UUID, customer_id: uuid.UUID, req: customers_schemas.CustomerUpdate, db: AsyncSession = Depends(get_db),
):
    return await customers_service.update_customer(db, org_id, customer_id, req)


# ------------------------------------------------------------ procurement --
@router.post("/procurement/suppliers", response_model=procurement_schemas.SupplierOut)
async def create_supplier(org_id: uuid.UUID, req: procurement_schemas.SupplierCreate, db: AsyncSession = Depends(get_db)):
    return await procurement_service.create_supplier(db, org_id, req)


@router.get("/procurement/suppliers", response_model=list[procurement_schemas.SupplierOut])
async def list_suppliers(
    org_id: uuid.UUID, is_active: bool | None = Query(None), search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await procurement_service.list_suppliers(db, org_id, is_active, search)


@router.get("/procurement/suppliers/{supplier_id}", response_model=procurement_schemas.SupplierOut)
async def get_supplier(org_id: uuid.UUID, supplier_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await procurement_service.get_supplier(db, org_id, supplier_id)


@router.patch("/procurement/suppliers/{supplier_id}", response_model=procurement_schemas.SupplierOut)
async def update_supplier(
    org_id: uuid.UUID, supplier_id: uuid.UUID, req: procurement_schemas.SupplierUpdate, db: AsyncSession = Depends(get_db),
):
    return await procurement_service.update_supplier(db, org_id, supplier_id, req)


@router.post("/procurement/purchase-orders", response_model=procurement_schemas.PurchaseOrderOut)
async def create_purchase_order(
    org_id: uuid.UUID, req: procurement_schemas.PurchaseOrderCreate,
    admin: Admin = Depends(get_current_platform_admin), db: AsyncSession = Depends(get_db),
):
    return await procurement_service.create_purchase_order(db, org_id, admin.id, req)


@router.get("/procurement/purchase-orders", response_model=list[procurement_schemas.PurchaseOrderOut])
async def list_purchase_orders(
    org_id: uuid.UUID, status_filter: str | None = Query(None, alias="status"),
    supplier_id: uuid.UUID | None = Query(None), db: AsyncSession = Depends(get_db),
):
    return await procurement_service.list_purchase_orders(db, org_id, status_filter, supplier_id)


@router.get("/procurement/purchase-orders/{po_id}", response_model=procurement_schemas.PurchaseOrderDetailOut)
async def get_purchase_order(org_id: uuid.UUID, po_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await procurement_service.get_purchase_order_detail(db, org_id, po_id)


@router.patch("/procurement/purchase-orders/{po_id}/status", response_model=procurement_schemas.PurchaseOrderOut)
async def update_purchase_order_status(
    org_id: uuid.UUID, po_id: uuid.UUID, req: procurement_schemas.PurchaseOrderStatusUpdate,
    admin: Admin = Depends(get_current_platform_admin), db: AsyncSession = Depends(get_db),
):
    return await procurement_service.update_status(db, org_id, po_id, admin.id, req)


# -------------------------------------------------------------- employees --
@router.post("/employees", response_model=employees_schemas.EmployeeOut)
async def create_employee(org_id: uuid.UUID, req: employees_schemas.EmployeeCreate, db: AsyncSession = Depends(get_db)):
    return await employees_service.create_employee(db, org_id, req)


@router.get("/employees", response_model=list[employees_schemas.EmployeeOut])
async def list_employees(
    org_id: uuid.UUID, employment_status: str | None = Query(None), department: str | None = Query(None),
    assigned_farm_id: uuid.UUID | None = Query(None), search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await employees_service.list_employees(db, org_id, employment_status, department, assigned_farm_id, search)


@router.get("/employees/{employee_id}", response_model=employees_schemas.EmployeeDetailOut)
async def get_employee(org_id: uuid.UUID, employee_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await employees_service.get_employee_detail(db, org_id, employee_id)


@router.patch("/employees/{employee_id}", response_model=employees_schemas.EmployeeOut)
async def update_employee(
    org_id: uuid.UUID, employee_id: uuid.UUID, req: employees_schemas.EmployeeUpdate, db: AsyncSession = Depends(get_db),
):
    return await employees_service.update_employee(db, org_id, employee_id, req)


@router.patch("/employees/{employee_id}/status", response_model=employees_schemas.EmployeeOut)
async def update_employment_status(
    org_id: uuid.UUID, employee_id: uuid.UUID, req: employees_schemas.EmployeeStatusUpdate,
    admin: Admin = Depends(get_current_platform_admin), db: AsyncSession = Depends(get_db),
):
    return await employees_service.update_employment_status(db, org_id, employee_id, admin.id, req)


@router.post("/employees/{employee_id}/shifts", response_model=employees_schemas.WorkShiftOut)
async def create_shift(
    org_id: uuid.UUID, employee_id: uuid.UUID, req: employees_schemas.WorkShiftCreate, db: AsyncSession = Depends(get_db),
):
    return await employees_service.create_shift(db, org_id, employee_id, req)


@router.get("/employees/{employee_id}/shifts", response_model=list[employees_schemas.WorkShiftOut])
async def list_shifts(
    org_id: uuid.UUID, employee_id: uuid.UUID, from_date: date | None = Query(None), to_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await employees_service.list_shifts(db, org_id, employee_id, from_date, to_date)


# ----------------------------------------------------------------- assets --
@router.post("/assets", response_model=assets_schemas.AssetOut)
async def create_asset(org_id: uuid.UUID, req: assets_schemas.AssetCreate, db: AsyncSession = Depends(get_db)):
    return await assets_service.create_asset(db, org_id, req)


@router.get("/assets", response_model=list[assets_schemas.AssetOut])
async def list_assets(
    org_id: uuid.UUID, asset_type: str | None = Query(None), status_filter: str | None = Query(None, alias="status"),
    assigned_farm_id: uuid.UUID | None = Query(None), search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await assets_service.list_assets(db, org_id, asset_type, status_filter, assigned_farm_id, search)


@router.get("/assets/{asset_id}", response_model=assets_schemas.AssetDetailOut)
async def get_asset(org_id: uuid.UUID, asset_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await assets_service.get_asset_detail(db, org_id, asset_id)


@router.patch("/assets/{asset_id}", response_model=assets_schemas.AssetOut)
async def update_asset(
    org_id: uuid.UUID, asset_id: uuid.UUID, req: assets_schemas.AssetUpdate, db: AsyncSession = Depends(get_db),
):
    return await assets_service.update_asset(db, org_id, asset_id, req)


@router.post("/assets/{asset_id}/maintenance", response_model=assets_schemas.MaintenanceRecordOut)
async def add_maintenance_record(
    org_id: uuid.UUID, asset_id: uuid.UUID, req: assets_schemas.MaintenanceRecordCreate, db: AsyncSession = Depends(get_db),
):
    return await assets_service.add_maintenance_record(db, org_id, asset_id, req)


@router.get("/assets/{asset_id}/maintenance", response_model=list[assets_schemas.MaintenanceRecordOut])
async def list_maintenance_records(org_id: uuid.UUID, asset_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await assets_service.list_maintenance_records(db, org_id, asset_id)


# --------------------------------------------------------------- commerce --
@router.post("/commerce/listings", response_model=commerce_schemas.ListingOut)
async def create_listing(org_id: uuid.UUID, req: commerce_schemas.ListingCreate, db: AsyncSession = Depends(get_db)):
    return await commerce_service.create_listing(db, org_id, req)


@router.get("/commerce/listings", response_model=list[commerce_schemas.ListingOut])
async def list_listings(
    org_id: uuid.UUID, species: str | None = Query(None), min_price: float | None = Query(None),
    max_price: float | None = Query(None), featured_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    filters = commerce_schemas.ListingFilter(
        species=species, min_price=min_price, max_price=max_price, featured_only=featured_only,
    )
    return await commerce_service.list_listings(db, org_id, filters)


@router.get("/commerce/listings/{listing_id}", response_model=commerce_schemas.ListingOut)
async def get_listing(org_id: uuid.UUID, listing_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await commerce_service.get_listing(db, org_id, listing_id)


@router.patch("/commerce/listings/{listing_id}", response_model=commerce_schemas.ListingOut)
async def update_listing(
    org_id: uuid.UUID, listing_id: uuid.UUID, req: commerce_schemas.ListingUpdate, db: AsyncSession = Depends(get_db),
):
    return await commerce_service.update_listing(db, org_id, listing_id, req)


@router.post("/commerce/listings/{listing_id}/deactivate", response_model=commerce_schemas.ListingOut)
async def deactivate_listing(org_id: uuid.UUID, listing_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await commerce_service.deactivate_listing(db, org_id, listing_id)


@router.get("/commerce/reservations", response_model=list[commerce_schemas.ReservationOut])
async def list_reservations(
    org_id: uuid.UUID, status_filter: str | None = Query(None, alias="status"), db: AsyncSession = Depends(get_db),
):
    return await commerce_service.list_reservations(db, org_id, status_filter)


@router.get("/commerce/orders", response_model=list[commerce_schemas.OrderOut])
async def list_orders(
    org_id: uuid.UUID, customer_id: uuid.UUID | None = Query(None), db: AsyncSession = Depends(get_db),
):
    return await commerce_service.list_orders(db, org_id, customer_id)


@router.get("/commerce/orders/{order_id}", response_model=commerce_schemas.OrderOut)
async def get_order(org_id: uuid.UUID, order_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await commerce_service.get_order(db, org_id, order_id)


@router.patch("/commerce/orders/{order_id}/status", response_model=commerce_schemas.OrderOut)
async def change_order_status(
    org_id: uuid.UUID, order_id: uuid.UUID, req: commerce_schemas.OrderStatusChange,
    admin: Admin = Depends(get_current_platform_admin), db: AsyncSession = Depends(get_db),
):
    return await commerce_service.change_order_status(db, org_id, order_id, admin.id, req)


# --------------------------------------------------------------- payments --
@router.get("/payments/{payment_id}", response_model=payments_schemas.PaymentOut)
async def get_payment(org_id: uuid.UUID, payment_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await payments_service.get_payment(db, org_id, payment_id)


@router.get("/payments/by-order/{order_id}", response_model=list[payments_schemas.PaymentOut])
async def list_payments_for_order(org_id: uuid.UUID, order_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await payments_service.list_payments_for_order(db, org_id, order_id)


# ---------------------------------------------------------------- finance --
@router.get("/finance/transactions", response_model=list[finance_schemas.FinanceTransactionOut])
async def list_transactions(
    org_id: uuid.UUID, start_date: date | None = Query(None), end_date: date | None = Query(None),
    transaction_type: str | None = Query(None), category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await finance_service.list_transactions(db, org_id, start_date, end_date, transaction_type, category)


@router.get("/finance/summary", response_model=finance_schemas.FinanceSummary)
async def get_summary(
    org_id: uuid.UUID, start_date: date = Query(...), end_date: date = Query(...), db: AsyncSession = Depends(get_db),
):
    return await finance_service.get_summary(db, org_id, start_date, end_date)


@router.get("/finance/invoices/by-order/{order_id}", response_model=finance_schemas.InvoiceOut)
async def get_invoice_for_order(org_id: uuid.UUID, order_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await finance_service.get_invoice_for_order(db, org_id, order_id)


# ---------------------------------------------------------- notifications --
@router.get("/notifications/email-outbox", response_model=list[notifications_schemas.EmailOutboxOut])
async def list_email_outbox(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await notifications_service.list_email_outbox(db, org_id)


# -------------------------------------------------------------- reporting --
@router.get("/reporting/dashboard-summary", response_model=reporting_schemas.DashboardSummary)
async def dashboard_summary(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await reporting_service.dashboard_summary(db, org_id)


@router.get("/reporting/profitability", response_model=reporting_schemas.ProfitabilityReport)
async def profitability_report(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await reporting_service.profitability_report(db, org_id)


# -------------------------------------------------------------------- cms --
@router.get("/cms/profile", response_model=cms_schemas.FarmProfileOut)
async def get_profile(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await cms_service.get_or_create_profile(db, org_id)


@router.patch("/cms/profile", response_model=cms_schemas.FarmProfileOut)
async def update_profile(org_id: uuid.UUID, req: cms_schemas.FarmProfileUpdate, db: AsyncSession = Depends(get_db)):
    return await cms_service.update_profile(db, org_id, req)


@router.get("/cms/testimonials", response_model=list[cms_schemas.TestimonialOut])
async def list_testimonials(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await cms_service.list_testimonials(db, org_id)


@router.get("/cms/blog-posts", response_model=list[cms_schemas.BlogPostOut])
async def list_blog_posts(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await cms_service.list_blog_posts(db, org_id)


@router.get("/cms/faqs", response_model=list[cms_schemas.FAQOut])
async def list_faqs(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await cms_service.list_faqs(db, org_id)


@router.get("/cms/banners", response_model=list[cms_schemas.BannerOut])
async def list_banners(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await cms_service.list_banners(db, org_id)

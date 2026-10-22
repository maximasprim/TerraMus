import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import get_db
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.security_checks import security_warnings
from app.modules.commerce.storage import config_from_settings as storage_config, config_warning as storage_warning
from app.core.observability import PrometheusMiddleware, register_metrics_endpoint, setup_tracing
from app.modules.identity.router import router as auth_router, users_router, audit_router, organization_router
from app.modules.farm.router import router as farm_router
from app.modules.livestock.router import router as livestock_router
from app.modules.crops.router import router as crops_router
from app.modules.catalog.router import router as catalog_router
from app.modules.health.router import animal_health_router, health_router
from app.modules.breeding.router import router as breeding_router, animal_breeding_router
from app.modules.dairy.router import router as dairy_router, herd_router as dairy_herd_router
from app.modules.inventory.router import router as inventory_router
from app.modules.customers.router import router as customers_router
from app.modules.procurement.router import router as procurement_router
from app.modules.employees.router import router as employees_router
from app.modules.assets.router import router as assets_router
from app.modules.commerce.router import listings_router, reservations_router, orders_router, media_router
from app.modules.payments.router import router as payments_router, webhooks_router as payments_webhooks_router
from app.modules.finance.router import router as finance_router
from app.modules.finance.handlers import register_finance_event_handlers
from app.modules.notifications.router import router as notifications_router
from app.modules.notifications.handlers import register_notification_event_handlers
from app.modules.reporting.router import router as reporting_router
from app.modules.cms.router import router as cms_router
from app.modules.public.router import router as public_router, domain_router
from app.modules.accounts.router import public_account_router, account_router
from app.modules.search.router import router as search_router
from app.modules.bulk_import.router import router as bulk_import_router
from app.modules.inquiries.router import router as inquiries_router, public_router as inquiries_public_router

# --- platform-admin / billing (superuser console + subscriptions) ---------
from app.modules.platform_admin.router import router as platform_admin_router
from app.modules.platform_admin.tenant_crud_router import router as platform_tenant_crud_router
from app.modules.platform_admin.audit_middleware import PlatformAuditMiddleware
from app.modules.billing.router import router as billing_router, webhooks_router as billing_webhooks_router
from app.modules.feedlot.router import router as feedlot_router
from app.modules.receivables.router import router as receivables_router
from app.modules.training.router import router as training_router
from app.modules.groups.router import router as groups_router
from app.modules.fuel.router import router as fuel_router
from app.modules.feedback.router import public as feedback_public_router, staff as feedback_staff_router
from app.modules.livestock.photo import router as animal_photo_router

settings = get_settings()

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# Loud (but non-fatal) startup warnings for insecure production-like config.
for _warning in security_warnings(
    settings.ENV, settings.JWT_SECRET, settings.MOCK_PAYMENT_SECRET, settings.ALLOW_MOCK_PAYMENTS,
):
    logging.getLogger("app.security").warning(_warning)

_storage_warning = storage_warning(storage_config(settings))
if _storage_warning:
    logging.getLogger("app.storage").warning(_storage_warning)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Subscription-lifecycle scheduler (billing/service.py's
    expire_overdue_subscriptions). No cron/Celery/APScheduler infra exists
    in this codebase, so this is a plain in-process asyncio loop that runs
    once a day for as long as the process is up. Safe across multiple
    replicas: expire_overdue_subscriptions takes a Postgres advisory lock
    internally, so only one replica's invocation actually does the work
    per tick - no new infrastructure needed for that guarantee."""
    from app.core.database import AsyncSessionLocal
    from app.modules.billing.service import expire_overdue_subscriptions

    async def _lifecycle_loop():
        while True:
            await asyncio.sleep(24 * 60 * 60)  # once a day
            try:
                async with AsyncSessionLocal() as db:
                    await expire_overdue_subscriptions(db)
            except Exception:
                logging.getLogger("app.billing").exception("subscription lifecycle check failed")

    async def _order_expiry_loop():
        """Cancels abandoned guest orders so they can't hold inventory
        forever (commerce/expiry.py). Every 10 minutes; safe on several
        replicas (a second runner just sees the order already cancelled)."""
        from app.modules.commerce.expiry import expire_stale_guest_orders

        while True:
            await asyncio.sleep(10 * 60)
            try:
                async with AsyncSessionLocal() as db:
                    await expire_stale_guest_orders(db)
            except Exception:
                logging.getLogger("app.orders").exception("stale guest order expiry failed")

    task = asyncio.create_task(_lifecycle_loop())
    order_task = asyncio.create_task(_order_expiry_loop())
    yield
    task.cancel()
    order_task.cancel()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Livestock Farm Management, ERP & E-Commerce Platform - "
                 "Identity/RBAC, Livestock, Health, Breeding/Dairy/Inventory, Commerce, "
                 "Payments/Finance, Reporting/Notifications, CMS/Public Site, Procurement, "
                 "Employees, Assets, Customer Accounts. "
                 "See docs/architecture.md for the full phase-by-phase build history.",
    lifespan=lifespan,
)

# Order matters: Starlette applies middleware in reverse registration order,
# so CORS (which needs to run first on the way in / last on the way out to
# correctly attach headers even to error responses) is added last here.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(PrometheusMiddleware)  # spec §47 - before CORS so every response (including CORS-rejected ones) is counted
# Audit-logs every write under /api/v1/platform/organizations/{org_id}/...
# - no-ops instantly for every other path, so its position relative to the
# other custom middleware doesn't matter for correctness. Grouped here with
# the rest of the app's own middleware, ahead of CORS, for consistency.
app.add_middleware(PlatformAuditMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_metrics_endpoint(app)  # spec §47 - GET /metrics, Prometheus exposition format
setup_tracing(app)  # spec §47 - no-op unless OTEL_EXPORTER_OTLP_ENDPOINT is set, see core/observability.py

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(audit_router)
app.include_router(organization_router)
app.include_router(farm_router)
app.include_router(livestock_router)
app.include_router(crops_router)
app.include_router(catalog_router)
app.include_router(animal_health_router)
app.include_router(health_router)
app.include_router(breeding_router)
app.include_router(animal_breeding_router)
app.include_router(dairy_router)
app.include_router(dairy_herd_router)
app.include_router(inventory_router)
app.include_router(customers_router)
app.include_router(procurement_router)
app.include_router(employees_router)
app.include_router(assets_router)
app.include_router(listings_router)
app.include_router(reservations_router)
app.include_router(orders_router)
app.include_router(payments_router)
app.include_router(payments_webhooks_router)
app.include_router(finance_router)
app.include_router(notifications_router)
app.include_router(reporting_router)
app.include_router(cms_router)
app.include_router(public_router)
app.include_router(domain_router)
app.include_router(public_account_router)
app.include_router(account_router)
app.include_router(search_router)
app.include_router(bulk_import_router)
app.include_router(media_router)
app.include_router(feedlot_router)
app.include_router(receivables_router)
app.include_router(training_router)
app.include_router(groups_router)
app.include_router(fuel_router)
app.include_router(feedback_public_router)
app.include_router(feedback_staff_router)
app.include_router(animal_photo_router)
app.include_router(inquiries_router)
app.include_router(inquiries_public_router)

# --- platform-admin / billing ----------------------------------------------
app.include_router(platform_admin_router)
app.include_router(platform_tenant_crud_router)
app.include_router(billing_router)
app.include_router(billing_webhooks_router)

register_finance_event_handlers()
register_notification_event_handlers()


@app.get("/health", tags=["system"])
async def health():
    """Liveness probe - process is up. Does NOT check dependencies; use
    /health/ready for that. Kubernetes/ECS-style liveness vs readiness split
    (spec §47)."""
    return {"status": "ok", "service": settings.APP_NAME, "env": settings.ENV}


@app.get("/health/ready", tags=["system"])
async def readiness(db=Depends(get_db)):
    """Readiness probe - checks the actual DB connection works, not just that
    the process is running. A load balancer should stop routing traffic here
    if this fails, even though /health still returns ok."""
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    status_str = "ok" if db_ok else "degraded"
    return {"status": status_str, "database": "ok" if db_ok else "unreachable"}

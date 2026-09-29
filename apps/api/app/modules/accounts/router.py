import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token
from app.core.middleware import rate_limit_auth
from app.modules.identity import schemas as identity_schemas, service as identity_service
from app.modules.public.service import get_org_by_slug
from app.modules.accounts import schemas, service
from app.modules.accounts.deps import get_current_customer

# Registration is org-scoped (a customer account belongs to one farm's
# storefront) and lives under the same {org_slug} prefix as the rest of
# modules/public - but unlike that router, this file's other two endpoints
# genuinely require auth, so it is deliberately its own router rather than
# added to public/router.py's "no auth dependency anywhere in this router"
# contract.
public_account_router = APIRouter(prefix="/api/v1/public/{org_slug}/account", tags=["customer-account"])
account_router = APIRouter(prefix="/api/v1/account", tags=["customer-account"])


@public_account_router.post("/register", response_model=identity_schemas.TokenPair, status_code=201)
async def register_customer_account(
    org_slug: str, req: schemas.CustomerRegisterRequest, request: Request, db: AsyncSession = Depends(get_db),
):
    await rate_limit_auth(request)  # same brute-force-relevant limiter as /auth/register (spec §29)
    org = await get_org_by_slug(db, org_slug)
    try:
        user = await service.register_customer_account(db, org.id, req)
    except ValueError as exc:
        if str(exc) == "email_already_registered":
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
        raise
    access_token = create_access_token(str(user.id), str(org.id))
    refresh_token = await identity_service.issue_refresh_token(db, user.id)
    return identity_schemas.TokenPair(access_token=access_token, refresh_token=refresh_token)


@account_router.get("/me", response_model=schemas.MyAccountOut)
async def my_account(
    user=Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_my_account(db, user)


@account_router.get("/orders", response_model=list[schemas.MyOrderOut])
async def my_orders(
    user=Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_my_orders(db, user.organization_id, user.customer_id)


@account_router.get("/orders/{order_id}", response_model=schemas.MyOrderDetailOut)
async def my_order_detail(
    order_id: uuid.UUID,
    user=Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_my_order(db, user.organization_id, user.customer_id, order_id)

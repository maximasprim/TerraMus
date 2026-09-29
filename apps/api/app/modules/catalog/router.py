from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import get_current_user
from app.modules.identity.models import User
from app.modules.catalog import schemas, service

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


@router.get("", response_model=schemas.EffectiveCatalogOut)
async def get_my_catalog(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """What species/crop types this tenant currently has visible - open to
    any authenticated user of the org (not permission-gated) since it's just
    the option list the frontend needs to build livestock/crop creation
    forms and navigation, not sensitive data."""
    return await service.get_effective_catalog(db, user.organization_id)

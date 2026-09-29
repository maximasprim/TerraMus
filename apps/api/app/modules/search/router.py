from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.search import schemas, service

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.get("", response_model=list[schemas.SearchResult])
async def global_search(
    q: str = Query(..., min_length=2, description="Search text - matched against IDs, tags, names, etc."),
    user: User = Depends(require_permission("search.use")),
    db: AsyncSession = Depends(get_db),
):
    return await service.search(db, user.organization_id, q)

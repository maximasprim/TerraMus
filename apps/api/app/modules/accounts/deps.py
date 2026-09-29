from fastapi import Depends, HTTPException, status

from app.modules.identity.deps import get_current_user
from app.modules.identity.models import User


async def get_current_customer(user: User = Depends(get_current_user)) -> User:
    """Staff accounts (customer_id is None) are correctly rejected by
    require_permission on every staff endpoint because 'Customer'-role users
    hold zero RBAC permissions (see identity/permissions.py's comment on the
    Customer role) - but the reverse isn't automatically true: nothing
    stopped a staff user from hitting /account/* before this check existed,
    since get_current_user alone doesn't know what kind of account it is."""
    if user.customer_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This endpoint is for customer accounts only")
    return user

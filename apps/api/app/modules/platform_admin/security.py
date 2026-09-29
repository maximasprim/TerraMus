"""Token issuance for platform admins.

Reuses the same JWT secret/algorithm/hashing primitives as the tenant auth
path (app/core/security.py) - there is no cryptographic reason to run two
separate secrets - but every token minted here carries "type":
"platform_admin" instead of "access". app.modules.identity.deps.get_current_user
explicitly checks for `type == "access"` and app.modules.platform_admin.deps
.get_current_platform_admin explicitly checks for `type == "platform_admin"`,
so a tenant user's token can never be used against a /api/v1/platform/*
route and a platform admin's token can never be used against a normal
tenant-scoped route, even though both are just JWTs signed with the same key.
"""
from app.core.security import create_access_token, decode_token  # noqa: F401 re-exported for callers


def create_platform_admin_token(admin_id: str) -> str:
    # org_id has no meaning for a platform admin; pass an empty string
    # rather than omitting it, since create_access_token's signature
    # requires it and downstream token consumers may look for an "org" key.
    return create_access_token(subject=admin_id, org_id="", extra={"type": "platform_admin"})

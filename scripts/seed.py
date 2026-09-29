"""Phase 1 demo seed data (spec §61): a demo organization/farm plus one user per
standard role, so the RBAC matrix can be exercised end-to-end.

Run with:  python -m scripts.seed   (from apps/api, with DATABASE_URL configured)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.core.database import AsyncSessionLocal
from app.modules.identity import service, schemas
from app.modules.identity.models import Role, User
from app.core.security import hash_password
from sqlalchemy import select
# Every module's models must be imported at least once so their tables
# register on Base.metadata - otherwise a cross-module foreign key (e.g.
# users.customer_id -> customers.id) can't resolve at flush time.
from app.modules.farm import models as farm_models  # noqa: F401
from app.modules.livestock import models as livestock_models  # noqa: F401
from app.modules.health import models as health_models  # noqa: F401
from app.modules.breeding import models as breeding_models  # noqa: F401
from app.modules.dairy import models as dairy_models  # noqa: F401
from app.modules.inventory import models as inventory_models  # noqa: F401
from app.modules.customers import models as customers_models  # noqa: F401
from app.modules.commerce import models as commerce_models  # noqa: F401
from app.modules.payments import models as payments_models  # noqa: F401
from app.modules.finance import models as finance_models  # noqa: F401
from app.modules.notifications import models as notifications_models  # noqa: F401
from app.modules.cms import models as cms_models  # noqa: F401


DEMO_USERS = [
    ("Farm Manager", "manager@demo.farm"),
    ("Livestock Manager", "livestock@demo.farm"),
    ("Veterinarian", "vet@demo.farm"),
    ("Farm Worker", "worker@demo.farm"),
    ("Inventory Manager", "inventory@demo.farm"),
    ("Accountant", "accountant@demo.farm"),
    ("Sales Manager", "sales@demo.farm"),
]

DEMO_PASSWORD = "DemoPass123!"


async def main():
    async with AsyncSessionLocal() as db:
        org, owner = await service.register_organization(
            db,
            schemas.RegisterRequest(
                organization_name="Demo Farm (Kenya)",
                full_name="Demo Owner",
                email="owner@demo.farm",
                password=DEMO_PASSWORD,
            ),
        )
        print(f"Created org: {org.name} ({org.id}); owner: owner@demo.farm / {DEMO_PASSWORD}")

        roles = (await db.execute(select(Role).where(Role.organization_id == org.id))).scalars().all()
        roles_by_name = {r.name: r for r in roles}

        for role_name, email in DEMO_USERS:
            user = User(
                organization_id=org.id,
                email=email,
                full_name=role_name,
                password_hash=hash_password(DEMO_PASSWORD),
                roles=[roles_by_name[role_name]],
            )
            db.add(user)
            print(f"  + {email} ({role_name}) / {DEMO_PASSWORD}")

        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())

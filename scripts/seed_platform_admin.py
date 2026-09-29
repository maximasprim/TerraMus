"""Creates the first platform admin (superuser) account, plus the default
subscription tiers, so there's an operator who can log in to /api/v1/platform.

Run with:  python -m scripts.seed_platform_admin   (from the repo root)

Deliberately a separate script from scripts/seed.py - that one creates DEMO
TENANT data (a sample org + its users) and is meant to be safe to re-run
against a throwaway dev database; this one creates a real operator account
and is meant to be run once per environment, typically with a real email/
password you choose interactively rather than a hard-coded demo password.
"""
import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.modules.platform_admin.models import PlatformAdmin
from app.modules.billing.service import ensure_default_tiers

# Same reasoning as scripts/seed.py: every module's models must be imported
# at least once so their tables register on Base.metadata before any FK
# involving them is flushed.
from app.modules.identity import models as identity_models  # noqa: F401
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
from app.modules.billing import models as billing_models  # noqa: F401


async def main():
    email = input("Platform admin email: ").strip()
    full_name = input("Platform admin full name: ").strip()
    password = getpass.getpass("Platform admin password: ")

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(PlatformAdmin).where(PlatformAdmin.email == email))
        if existing.scalar_one_or_none():
            print(f"A platform admin with email {email} already exists - nothing to do.")
            return

        admin = PlatformAdmin(email=email, full_name=full_name, password_hash=hash_password(password))
        db.add(admin)
        await ensure_default_tiers(db)
        await db.commit()
        await db.refresh(admin)

        print(f"Created platform admin {admin.email} (id={admin.id})")
        print("Default subscription tiers ensured: free, basic, pro, enterprise")
        print("Log in at POST /api/v1/platform/auth/login")


if __name__ == "__main__":
    asyncio.run(main())

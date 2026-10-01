import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.database import Base
# Import all module models so they register on Base.metadata for autogenerate
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.farm import models as farm_models  # noqa: F401
from app.modules.livestock import models as livestock_models  # noqa: F401
from app.modules.health import models as health_models  # noqa: F401
from app.modules.breeding import models as breeding_models  # noqa: F401
from app.modules.dairy import models as dairy_models  # noqa: F401
from app.modules.inventory import models as inventory_models  # noqa: F401
from app.modules.customers import models as customers_models  # noqa: F401
from app.modules.commerce import models as commerce_models  # noqa: F401
from app.modules.inquiries import models as inquiries_models  # noqa: F401
from app.modules.payments import models as payments_models  # noqa: F401
from app.modules.finance import models as finance_models  # noqa: F401
from app.modules.notifications import models as notifications_models  # noqa: F401
from app.modules.cms import models as cms_models  # noqa: F401
from app.modules.billing import models as billing_models  # noqa: F401
from app.modules.platform_admin import models as platform_admin_models  # noqa: F401

config = context.config
settings = get_settings()
# Alembic runs migrations synchronously; use the psycopg (sync) URL here.
# configparser (which backs alembic's Config) treats "%" as interpolation
# syntax, so a URL-encoded password (e.g. "%40" for "@") must have its "%"
# doubled to "%%" before being handed to set_main_option, or configparser
# raises "invalid interpolation syntax".
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

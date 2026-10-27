"""Emails are case-insensitive: normalise stored addresses and enforce uniqueness on lower(email).

Before this, `Jane@Farm.com` and `jane@farm.com` could register as two accounts and sign-in was
case-sensitive. The app now normalises every address; this migration makes the DATABASE guarantee it
(which also closes the check-then-insert race where two simultaneous sign-ups both passed the check).

It will NOT guess. If two existing accounts already differ only by letter case, it stops with the list
and changes nothing, because deciding which person keeps the address is a human decision.

Revision ID: 0032
Revises: 0031
"""
from alembic import op
from sqlalchemy import text

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

TABLES = ("users", "platform_admins")


def upgrade() -> None:
    bind = op.get_bind()
    problems = []
    for t in TABLES:
        rows = bind.execute(text(
            f"SELECT lower(email) AS e, count(*) AS n, string_agg(email, ', ' ORDER BY created_at) AS shown "
            f"FROM {t} GROUP BY lower(email) HAVING count(*) > 1")).fetchall()
        problems += [f"{t}: {r.shown}" for r in rows]
    if problems:
        raise RuntimeError(
            "Cannot make emails case-insensitive: these accounts differ only by letter case. Decide who keeps each "
            "address (rename or deactivate the others), then run the migration again. Nothing was changed.\n  "
            + "\n  ".join(problems))
    for t in TABLES:
        op.execute(f"UPDATE {t} SET email = lower(btrim(email)) WHERE email <> lower(btrim(email))")
        op.create_index(f"uq_{t}_email_lower", t, [text("lower(email)")], unique=True)
    # CRM contact emails are not logins, but matching them case-insensitively stops duplicate customers
    op.execute("UPDATE customers SET email = lower(btrim(email)) WHERE email IS NOT NULL AND email <> lower(btrim(email))")


def downgrade() -> None:
    for t in TABLES:
        op.drop_index(f"uq_{t}_email_lower", table_name=t)
    # lower-cased addresses are not restored: the original casing was never meaningful

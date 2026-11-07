"""Role visibility switches: Notifications page and the tabs on an animal's page.

Revision ID: 0045
Revises: 0044

The farm owner already chooses, per role, which pages that role can open (Team > Roles). This adds seven more switches
to the same screen:

  * notifications.view      - the Notifications page (until now every signed-in user could open it)
  * animaltabs.timeline / .health / .weights / .movements / .breeding / .dairy
                            - the tabs on an animal's page (Overview is always shown)

Nothing may change for anyone on the day this runs, so every EXISTING role in every organization (built-in or custom)
is granted all seven. The one exception is the storefront "Customer" role, which never opens the admin app. From
then on the owner can untick any of them for any role.

Downgrade removes the seven permissions and every grant of them.
"""
import uuid

from alembic import op
from sqlalchemy import text

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

NEW_PERMISSIONS = [
    ("notifications.view", "Open the Notifications page"),
    ("animaltabs.timeline", "Show the Timeline tab on an animal's page"),
    ("animaltabs.health", "Show the Health tab on an animal's page"),
    ("animaltabs.weights", "Show the Weights tab on an animal's page"),
    ("animaltabs.movements", "Show the Movements tab on an animal's page"),
    ("animaltabs.breeding", "Show the Breeding tab on an animal's page"),
    ("animaltabs.dairy", "Show the Dairy tab on an animal's page"),
]


def upgrade() -> None:
    bind = op.get_bind()
    existing = {r[0] for r in bind.execute(text("SELECT code FROM permissions")).fetchall()}
    for code, description in NEW_PERMISSIONS:
        if code not in existing:
            bind.execute(
                text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"),
                {"i": str(uuid.uuid4()), "c": code, "d": description},
            )
    pid = {c: str(i) for i, c in bind.execute(text("SELECT id, code FROM permissions")).fetchall()}

    role_ids = [
        str(r[0]) for r in bind.execute(
            text("SELECT id FROM roles WHERE NOT (is_system = true AND name = 'Customer')")
        ).fetchall()
    ]
    for role_id in role_ids:
        for code, _ in NEW_PERMISSIONS:
            bind.execute(
                text(
                    "INSERT INTO role_permissions (role_id, permission_id) VALUES (:r, :p) "
                    "ON CONFLICT (role_id, permission_id) DO NOTHING"
                ),
                {"r": role_id, "p": pid[code]},
            )


def downgrade() -> None:
    bind = op.get_bind()
    for code, _ in NEW_PERMISSIONS:
        bind.execute(
            text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = :c)"),
            {"c": code},
        )
        bind.execute(text("DELETE FROM permissions WHERE code = :c"), {"c": code})

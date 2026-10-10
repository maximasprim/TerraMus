"""Custom-domain uniqueness applies to VERIFIED domains only.

Before: `ix_organizations_custom_domain` was a plain UNIQUE index, so whoever
typed a domain first blocked everyone else from using it - even without ever
proving they own it (a squatting/denial-of-service vector: an attacker could
claim a competitor's domain and the real owner would get "already in use").

After: any number of organizations may *claim* a domain, but only one can hold
it *verified* (partial unique index). Ownership is decided by DNS proof, not by
who claimed first. Nothing routes on an unverified domain, so coexisting
claims are harmless.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_organizations_custom_domain", table_name="organizations")
    op.create_index("ix_organizations_custom_domain", "organizations", ["custom_domain"], unique=False)
    op.create_index(
        "uq_organizations_verified_custom_domain", "organizations", ["custom_domain"],
        unique=True, postgresql_where=sa.text("domain_verified"),
    )


def downgrade() -> None:
    # The old schema allowed one holder per domain, so before restoring that
    # constraint drop the claims it could not have held: unverified duplicates.
    op.execute(
        """
        UPDATE organizations
           SET custom_domain = NULL, domain_verification_token = NULL, domain_added_at = NULL
         WHERE NOT domain_verified
           AND custom_domain IN (SELECT custom_domain FROM organizations
                                  WHERE custom_domain IS NOT NULL GROUP BY custom_domain HAVING COUNT(*) > 1)
        """
    )
    op.drop_index("uq_organizations_verified_custom_domain", table_name="organizations")
    op.drop_index("ix_organizations_custom_domain", table_name="organizations")
    op.create_index("ix_organizations_custom_domain", "organizations", ["custom_domain"], unique=True)

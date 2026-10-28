"""Feedlot ledger: a sale or a purchase can be posted to the ledger at most once.

The finance ledger is append-only (rows can never be edited or deleted), so a duplicate
posting could never be undone. These partial unique indexes make a duplicate impossible
at the database level, however it is attempted (re-import, retry, two clicks, two users):

  * cash feedlot sale        -> one finance_transactions row per exit
  * credit feedlot sale      -> one account_entries 'charge' per exit
  * animal purchase expense  -> one 'livestock_acquisition' row per animal

The purchase index is only created when the existing data has no duplicates (an
append-only ledger cannot be cleaned up), otherwise it is skipped and the application-level
check still prevents new ones. Additive only; nothing is modified or deleted.

Revision ID: 0036
Revises: 0035
"""
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM finance_transactions WHERE reference_type = 'feedlot_sale'
                         GROUP BY organization_id, reference_id HAVING count(*) > 1) THEN
            CREATE UNIQUE INDEX IF NOT EXISTS uq_fin_tx_feedlot_sale
              ON finance_transactions (organization_id, reference_id) WHERE reference_type = 'feedlot_sale';
          END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM account_entries WHERE reference_type = 'feedlot_sale' AND entry_type = 'charge'
                         GROUP BY organization_id, reference_id HAVING count(*) > 1) THEN
            CREATE UNIQUE INDEX IF NOT EXISTS uq_acct_entry_feedlot_sale_charge
              ON account_entries (organization_id, reference_id)
              WHERE reference_type = 'feedlot_sale' AND entry_type = 'charge';
          END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM finance_transactions
                         WHERE reference_type = 'animal' AND category = 'livestock_acquisition'
                         GROUP BY organization_id, reference_id HAVING count(*) > 1) THEN
            CREATE UNIQUE INDEX IF NOT EXISTS uq_fin_tx_animal_acquisition
              ON finance_transactions (organization_id, reference_id)
              WHERE reference_type = 'animal' AND category = 'livestock_acquisition';
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_fin_tx_animal_acquisition;")
    op.execute("DROP INDEX IF EXISTS uq_acct_entry_feedlot_sale_charge;")
    op.execute("DROP INDEX IF EXISTS uq_fin_tx_feedlot_sale;")

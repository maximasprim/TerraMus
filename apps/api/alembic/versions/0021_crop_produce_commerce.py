"""Crop-produce commerce: listings and orders can now sell quantity-based
crop produce (from harvest_records) alongside the existing per-animal
livestock sales.

Unlike an animal (a single unique unit that's reserved then sold exactly
once), crop produce is a *stock* concept - a customer buys some quantity out
of what's been harvested so far. So rather than force crop sales through
livestock's exclusive reserve/sell state machine, `listings` and
`order_items` gain a parallel, equally-valid product reference
(`crop_planting_id` + `unit`/`quantity`) alongside the existing
`animal_id` - exactly one of the two is set per row (enforced by CHECK
constraints below). `animal_id` therefore becomes nullable on both tables;
every existing row already has it set, so this changes nothing for them.

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------- listings --
    op.alter_column("listings", "animal_id", nullable=True)
    op.add_column("listings", sa.Column("crop_planting_id", pg.UUID(as_uuid=True), sa.ForeignKey("crop_plantings.id"), nullable=True))
    op.add_column("listings", sa.Column("unit", sa.String(16), nullable=True))
    op.create_index("ix_listings_crop_planting_id", "listings", ["crop_planting_id"])
    op.create_check_constraint(
        "listing_exactly_one_product",
        "listings",
        "(animal_id IS NOT NULL AND crop_planting_id IS NULL) OR (animal_id IS NULL AND crop_planting_id IS NOT NULL)",
    )
    # Same "one active listing per product" rule as animals (migration 0006's
    # uq_listings_active_animal), mirrored for crop plantings.
    op.execute("""
        CREATE UNIQUE INDEX uq_listings_active_crop_planting
        ON listings (crop_planting_id)
        WHERE is_active = true AND crop_planting_id IS NOT NULL;
    """)

    # -------------------------------------------------------- order_items --
    op.alter_column("order_items", "animal_id", nullable=True)
    op.add_column("order_items", sa.Column("crop_planting_id", pg.UUID(as_uuid=True), sa.ForeignKey("crop_plantings.id"), nullable=True))
    op.add_column("order_items", sa.Column("quantity", sa.Numeric(12, 2), nullable=False, server_default="1"))
    op.create_index("ix_order_items_crop_planting_id", "order_items", ["crop_planting_id"])
    op.create_check_constraint(
        "order_item_exactly_one_product",
        "order_items",
        "(animal_id IS NOT NULL AND crop_planting_id IS NULL) OR (animal_id IS NULL AND crop_planting_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("order_item_exactly_one_product", "order_items", type_="check")
    op.drop_index("ix_order_items_crop_planting_id", table_name="order_items")
    op.drop_column("order_items", "quantity")
    op.drop_column("order_items", "crop_planting_id")
    op.alter_column("order_items", "animal_id", nullable=False)

    op.execute("DROP INDEX IF EXISTS uq_listings_active_crop_planting;")
    op.drop_constraint("listing_exactly_one_product", "listings", type_="check")
    op.drop_index("ix_listings_crop_planting_id", table_name="listings")
    op.drop_column("listings", "unit")
    op.drop_column("listings", "crop_planting_id")
    op.alter_column("listings", "animal_id", nullable=False)

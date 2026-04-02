"""add provenance fields, tier and supplier_id

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-01 00:00:00.000000

Ergänzt ScrapBatch um Provenienz- und Wirtschaftsfelder,
Actor um relationship_tier und FieldAccessPolicy um relationship_tier.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── scrap_batches: Provenienzdaten ────────────────────────────────────────
    op.add_column("scrap_batches", sa.Column("origin_region", sa.String(255), nullable=True))
    op.add_column("scrap_batches", sa.Column("collection_period", sa.String(50), nullable=True))
    op.add_column("scrap_batches", sa.Column("preparation_degree", sa.String(100), nullable=True))
    op.add_column("scrap_batches", sa.Column("contamination_level", sa.String(50), nullable=True))

    # ── scrap_batches: Wirtschaftliche Felder ─────────────────────────────────
    op.add_column("scrap_batches", sa.Column("price_basis", sa.String(255), nullable=True))
    op.add_column("scrap_batches", sa.Column("pricing_formula_ref", sa.String(255), nullable=True))

    # ── scrap_batches: Lieferantenreferenz (FK auf actors) ────────────────────
    op.add_column("scrap_batches", sa.Column("supplier_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_scrap_batches_supplier_id",
        "scrap_batches", "actors",
        ["supplier_id"], ["id"],
    )

    # ── actors: Relationship-Tier ─────────────────────────────────────────────
    op.add_column("actors", sa.Column("relationship_tier", sa.String(20), nullable=True))

    # ── field_access_policies: Relationship-Tier ─────────────────────────────
    op.add_column(
        "field_access_policies",
        sa.Column("relationship_tier", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("field_access_policies", "relationship_tier")
    op.drop_column("actors", "relationship_tier")
    op.drop_constraint("fk_scrap_batches_supplier_id", "scrap_batches", type_="foreignkey")
    op.drop_column("scrap_batches", "supplier_id")
    op.drop_column("scrap_batches", "pricing_formula_ref")
    op.drop_column("scrap_batches", "price_basis")
    op.drop_column("scrap_batches", "contamination_level")
    op.drop_column("scrap_batches", "preparation_degree")
    op.drop_column("scrap_batches", "collection_period")
    op.drop_column("scrap_batches", "origin_region")

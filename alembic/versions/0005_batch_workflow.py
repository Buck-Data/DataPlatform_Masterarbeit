"""batch workflow: new fields on scrap_batches, new table batch_source_pickups

Revision ID: 0005
Revises: 0004
Create Date: 2025-04-01

Änderungen:
  - scrap_batches: + workflow_status, + created_by_trader_id, + offered_to_steel_mill_id,
                   + delivery_date, + confirmed_by_trader, + confirmed_by_steel_mill
  - Neue Tabelle batch_source_pickups (Verknüpfung Charge ↔ Abholhistorie)
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    # ── scrap_batches: Workflow-Felder hinzufügen ─────────────────────────────
    op.add_column("scrap_batches", sa.Column(
        "workflow_status", sa.String(20), nullable=True, server_default="entwurf"
    ))
    op.add_column("scrap_batches", sa.Column(
        "created_by_trader_id", sa.String(36),
        sa.ForeignKey("actors.id"), nullable=True
    ))
    op.add_column("scrap_batches", sa.Column(
        "offered_to_steel_mill_id", sa.String(36),
        sa.ForeignKey("actors.id"), nullable=True
    ))
    op.add_column("scrap_batches", sa.Column(
        "delivery_date", sa.Date(), nullable=True
    ))
    op.add_column("scrap_batches", sa.Column(
        "confirmed_by_trader", sa.Boolean(), nullable=False, server_default="false"
    ))
    op.add_column("scrap_batches", sa.Column(
        "confirmed_by_steel_mill", sa.Boolean(), nullable=False, server_default="false"
    ))

    # ── Neue Tabelle: Verknüpfung Charge ↔ Abholhistorie ─────────────────────
    op.create_table(
        "batch_source_pickups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("scrap_batches.id"), nullable=False),
        sa.Column(
            "pickup_history_entry_id", sa.String(36),
            sa.ForeignKey("pickup_history_entries.id"), nullable=False
        ),
    )


def downgrade():
    op.drop_table("batch_source_pickups")
    op.drop_column("scrap_batches", "confirmed_by_steel_mill")
    op.drop_column("scrap_batches", "confirmed_by_trader")
    op.drop_column("scrap_batches", "delivery_date")
    op.drop_column("scrap_batches", "offered_to_steel_mill_id")
    op.drop_column("scrap_batches", "created_by_trader_id")
    op.drop_column("scrap_batches", "workflow_status")

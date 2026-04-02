"""container logistics update: volume schema, confirmation, history

Revision ID: 0004
Revises: 0003
Create Date: 2025-04-01

Änderungen:
  - containers: capacity_kg -> capacity_m3 (Float), current_fill_kg -> fill_level (Integer 0-100)
  - pickup_requests: + initiator, + confirmed_by_metal_processor, + confirmed_by_trader
  - Neue Tabelle pickup_history_entries
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    # ── containers: Volumen-Schema-Umstellung ─────────────────────────────────
    # Neue Spalten hinzufügen
    op.add_column("containers", sa.Column("capacity_m3", sa.Float(), nullable=True))
    op.add_column("containers", sa.Column("fill_level", sa.Integer(), nullable=True))

    # Bestehende Daten konvertieren:
    # capacity_kg-Wert als capacity_m3 übernehmen (werden vom Seed ohnehin neu gesetzt)
    # fill_level aus current_fill_kg/capacity_kg * 100 berechnen
    op.execute("""
        UPDATE containers
        SET capacity_m3 = capacity_kg,
            fill_level = CASE
                WHEN capacity_kg > 0
                THEN LEAST(100, ROUND(current_fill_kg / capacity_kg * 100)::INTEGER)
                ELSE 0
            END
    """)

    # Spalten NOT NULL setzen
    op.alter_column("containers", "capacity_m3", nullable=False)
    op.alter_column("containers", "fill_level", nullable=False)

    # Alte Spalten entfernen
    op.drop_column("containers", "capacity_kg")
    op.drop_column("containers", "current_fill_kg")

    # ── pickup_requests: neue Felder ──────────────────────────────────────────
    op.add_column("pickup_requests", sa.Column(
        "initiator", sa.String(20), nullable=False, server_default="haendler"
    ))
    op.add_column("pickup_requests", sa.Column(
        "confirmed_by_metal_processor", sa.Boolean(), nullable=False, server_default="false"
    ))
    op.add_column("pickup_requests", sa.Column(
        "confirmed_by_trader", sa.Boolean(), nullable=False, server_default="false"
    ))

    # ── Neue Tabelle: Abholhistorie ───────────────────────────────────────────
    op.create_table(
        "pickup_history_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("container_id", sa.String(36), sa.ForeignKey("containers.id"), nullable=False),
        sa.Column("pickup_request_id", sa.String(36), sa.ForeignKey("pickup_requests.id"), nullable=False),
        sa.Column("trader_id", sa.String(36), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("metal_processor_id", sa.String(36), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=False),
        sa.Column("fill_level_at_pickup", sa.Integer(), nullable=False),
        sa.Column("estimated_volume_m3", sa.Float(), nullable=False),
        sa.Column("scrap_type", sa.String(20), nullable=True),
    )


def downgrade():
    op.drop_table("pickup_history_entries")

    op.drop_column("pickup_requests", "confirmed_by_trader")
    op.drop_column("pickup_requests", "confirmed_by_metal_processor")
    op.drop_column("pickup_requests", "initiator")

    op.add_column("containers", sa.Column("capacity_kg", sa.Float(), nullable=True))
    op.add_column("containers", sa.Column("current_fill_kg", sa.Float(), nullable=True))
    op.execute("""
        UPDATE containers
        SET capacity_kg = capacity_m3,
            current_fill_kg = fill_level / 100.0 * capacity_m3
    """)
    op.alter_column("containers", "capacity_kg", nullable=False)
    op.alter_column("containers", "current_fill_kg", nullable=False)
    op.drop_column("containers", "fill_level")
    op.drop_column("containers", "capacity_m3")

"""add container and pickup_request tables

Revision ID: 0003
Revises: 0002
Create Date: 2025-04-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "containers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("container_number", sa.String(100), unique=True, nullable=False),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("location", sa.String(255), nullable=False),
        sa.Column("capacity_kg", sa.Float(), nullable=False),
        sa.Column("current_fill_kg", sa.Float(), default=0.0),
        sa.Column("status", sa.String(50), default="leer"),
        sa.Column("scrap_class", sa.String(20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "pickup_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("container_id", sa.String(36), sa.ForeignKey("containers.id"), nullable=False),
        sa.Column("requesting_actor_id", sa.String(36), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("requested_pickup_date", sa.Date(), nullable=False),
        sa.Column("offered_price_per_ton", sa.Float(), nullable=True),
        sa.Column("status", sa.String(50), default="ausstehend"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("pickup_requests")
    op.drop_table("containers")

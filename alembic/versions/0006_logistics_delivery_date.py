"""add delivery_date to logistics_orders

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("logistics_orders", sa.Column("delivery_date", sa.Date(), nullable=True))


def downgrade():
    op.drop_column("logistics_orders", "delivery_date")

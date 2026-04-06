"""add receiving_actor_id to logistics_orders

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "logistics_orders",
        sa.Column(
            "receiving_actor_id",
            sa.String(length=36),
            sa.ForeignKey("actors.id"),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE logistics_orders lo
        SET receiving_actor_id = a.id
        FROM actors a
        WHERE a.role = 'stahlwerk'
          AND (
            lo.delivery_location ILIKE '%' || a.name || '%'
            OR lo.delivery_location ILIKE '%' || a.organization || '%'
          )
        """
    )


def downgrade():
    op.drop_column("logistics_orders", "receiving_actor_id")

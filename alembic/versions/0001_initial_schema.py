"""initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "actors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("organization", sa.String(255), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "scrap_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_number", sa.String(100), nullable=False, unique=True),
        sa.Column("scrap_class", sa.String(20), nullable=False),
        sa.Column("origin_type", sa.String(50), nullable=False),
        sa.Column("mass_kg", sa.Float(), nullable=False),
        sa.Column("volume_m3", sa.Float(), nullable=True),
        sa.Column("processing_degree", sa.String(100), nullable=True),
        sa.Column("eaf_compatibility", sa.String(50), nullable=True),
        sa.Column("supplier_source", sa.String(255), nullable=True),
        sa.Column("price_per_ton", sa.Float(), nullable=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "chemical_compositions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("scrap_batches.id"), nullable=False),
        sa.Column("element_values", postgresql.JSONB(), nullable=False),
        sa.Column("thresholds", postgresql.JSONB(), nullable=False),
        sa.Column("analysis_method", sa.String(100), nullable=False),
        sa.Column("measured_at", sa.DateTime(), nullable=False),
        sa.Column("measured_by", sa.String(255), nullable=False),
        sa.Column("threshold_exceeded", sa.Boolean(), default=False),
        sa.Column("exceeded_elements", postgresql.JSONB(), nullable=True),
    )

    op.create_table(
        "material_passports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("scrap_batches.id"), nullable=False),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("validation_status", sa.String(50), default="entwurf"),
        sa.Column("certification_ref", sa.String(255), nullable=True),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "traceability_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("scrap_batches.id"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("epcis_type", sa.String(100), nullable=True),
    )

    op.create_table(
        "quality_analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("scrap_batches.id"), nullable=False),
        sa.Column("physical_condition", sa.String(50), nullable=False),
        sa.Column("density_class", sa.String(50), nullable=False),
        sa.Column("dimension_class", sa.String(50), nullable=False),
        sa.Column("moisture_content", sa.Float(), nullable=True),
        sa.Column("oil_residue", sa.Boolean(), default=False),
        sa.Column("radioactive_cleared", sa.Boolean(), default=True),
        sa.Column("inspected_at", sa.DateTime(), nullable=False),
        sa.Column("inspector_id", sa.String(36), sa.ForeignKey("actors.id"), nullable=False),
    )

    op.create_table(
        "logistics_orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("scrap_batches.id"), nullable=False),
        sa.Column("requesting_actor_id", sa.String(36), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("pickup_date", sa.Date(), nullable=False),
        sa.Column("pickup_location", sa.String(255), nullable=False),
        sa.Column("delivery_location", sa.String(255), nullable=False),
        sa.Column("container_status", sa.String(50), default="leer"),
        sa.Column("delivery_status", sa.String(50), default="geplant"),
        sa.Column("carrier", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "cbam_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("scrap_batches.id"), nullable=False),
        sa.Column("scope1_emissions_kg", sa.Float(), nullable=False),
        sa.Column("scope2_emissions_kg", sa.Float(), nullable=False),
        sa.Column("scope3_emissions_kg", sa.Float(), nullable=True),
        sa.Column("calculation_method", sa.String(100), nullable=False),
        sa.Column("reporting_period", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "field_access_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("data_field", sa.String(255), nullable=False),
        sa.Column("actor_role", sa.String(50), nullable=False),
        sa.Column("access_rule", sa.String(10), nullable=False, default="allow"),
        sa.Column("is_default", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("field_access_policies")
    op.drop_table("cbam_records")
    op.drop_table("logistics_orders")
    op.drop_table("quality_analyses")
    op.drop_table("traceability_events")
    op.drop_table("material_passports")
    op.drop_table("chemical_compositions")
    op.drop_table("scrap_batches")
    op.drop_table("actors")

"""
ForestWatch Zambia

Revision: Create forest detection system tables
Revision ID: dff42c735d8c
Revises: da8e3b0a7357
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2

revision: str = "dff42c735d8c"
down_revision: Union[str, Sequence[str], None] = "da8e3b0a7357"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create forest detection system tables."""

    # Provinces
    op.create_table(
        "provinces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_provinces_id", "provinces", ["id"])
    op.create_index("ix_provinces_name", "provinces", ["name"], unique=True)

    # Districts
    op.create_table(
        "districts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("province_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["province_id"], ["provinces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_districts_id", "districts", ["id"])
    op.create_index("ix_districts_name", "districts", ["name"])
    op.create_index("ix_districts_province_id", "districts", ["province_id"])

    # Forest Areas
    op.create_table(
        "forest_areas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("forest_code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("district_id", sa.Integer(), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.types.Geometry(
                geometry_type="POLYGON",
                srid=4326,
                dimension=2,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("area_hectares", sa.Float(), nullable=False),
        sa.Column(
            "protected_status",
            sa.Enum(
                "PROTECTED_FOREST", "NATIONAL_PARK", "GAME_MANAGEMENT_AREA",
                "COMMUNITY_FOREST", "PRIVATE_FOREST", name="protectedstatus"
            ),
            nullable=False,
        ),
        sa.Column(
            "monitoring_frequency",
            sa.Enum(
                "DAILY", "EVERY_2_DAYS", "WEEKLY", "MONTHLY",
                name="monitoringfrequency"
            ),
            nullable=False,
        ),
        sa.Column(
            "priority_level",
            sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="prioritylevel"),
            nullable=False,
        ),
        sa.Column("monitoring_enabled", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["district_id"], ["districts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # IF NOT EXISTS prevents the duplicate index error seen in the database.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_forest_areas_geometry "
        "ON forest_areas USING gist (geometry)"
    )
    op.create_index("ix_forest_areas_district_id", "forest_areas", ["district_id"])
    op.create_index("ix_forest_areas_forest_code", "forest_areas", ["forest_code"], unique=True)
    op.create_index("ix_forest_areas_id", "forest_areas", ["id"])
    op.create_index("ix_forest_areas_name", "forest_areas", ["name"])

    # The remaining application tables are created by the model/migration set.
    # This migration deliberately does not touch PostGIS's spatial_ref_sys table.


def downgrade() -> None:
    """Drop forest detection system tables."""

    op.drop_index("ix_forest_areas_name", table_name="forest_areas")
    op.drop_index("ix_forest_areas_id", table_name="forest_areas")
    op.drop_index("ix_forest_areas_forest_code", table_name="forest_areas")
    op.drop_index("ix_forest_areas_district_id", table_name="forest_areas")
    op.execute("DROP INDEX IF EXISTS idx_forest_areas_geometry")
    op.drop_table("forest_areas")

    op.drop_index("ix_districts_province_id", table_name="districts")
    op.drop_index("ix_districts_name", table_name="districts")
    op.drop_index("ix_districts_id", table_name="districts")
    op.drop_table("districts")

    op.drop_index("ix_provinces_name", table_name="provinces")
    op.drop_index("ix_provinces_id", table_name="provinces")
    op.drop_table("provinces")

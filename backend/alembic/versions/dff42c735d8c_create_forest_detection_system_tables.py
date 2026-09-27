"""
Create forest detection system tables

===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Revision: Create forest detection system tables

Revision ID: dff42c735d8c
Revises: da8e3b0a7357

Purpose:
    Creates the administrative hierarchy the system is
    organised around, and the forest areas it monitors.

Creates:
    provinces      Zambian provinces.
    districts      Districts, each belonging to a province.
    forest_areas   Monitored areas, each in a district, with
                   a PostGIS geometry column.

Why this order matters:
    These three tables form the chain that jurisdiction-
    scoped access (requirement FR-04) is enforced along:

        Province -> District -> ForestArea -> Detection

    A provincial officer is assigned a province and sees
    every district within it; a district officer sees one
    district. The repository layer walks this chain to decide
    what a query may return, so the foreign keys created here
    are a security control as much as a data structure.

Geometry:
    forest_areas.geometry is a PostGIS POLYGON in EPSG:4326,
    which is longitude and latitude in degrees. It is indexed
    with GiST, without which a spatial query would scan every
    row.

    Note that this differs from detections, added later in
    c3f8a1d54b72, which use EPSG:32735 (UTM 35S, metres).
    Boundaries are stored in degrees because that is what
    the interface draws and exchanges; detection areas are
    stored in metres so that surface area comes out directly
    in square metres, and the half-hectare threshold can be
    applied without a projection step.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
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

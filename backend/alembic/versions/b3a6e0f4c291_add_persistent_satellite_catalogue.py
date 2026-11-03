"""Persist Sentinel-2 discovery metadata and search progress.

Revision ID: b3a6e0f4c291
Revises: a6b29b1042ef
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3a6e0f4c291"
down_revision: Union[str, Sequence[str], None] = "a6b29b1042ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "satellite_images",
        "cloud_cover_percentage",
        existing_type=sa.Float(),
        nullable=True,
    )
    op.alter_column(
        "satellite_images",
        "product_id",
        existing_type=sa.String(length=120),
        type_=sa.String(length=150),
        existing_nullable=False,
    )
    op.create_table(
        "satellite_catalogue_products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("forest_area_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.String(length=150), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("tile_id", sa.String(length=20), nullable=True),
        sa.Column("acquisition_datetime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acquisition_timestamp", sa.String(length=40), nullable=True),
        sa.Column("cloud_cover_percentage", sa.Float(), nullable=True),
        sa.Column("processing_level", sa.String(length=30), nullable=True),
        sa.Column("product_type", sa.String(length=30), nullable=True),
        sa.Column("online", sa.Boolean(), nullable=True),
        sa.Column("content_length", sa.BigInteger(), nullable=True),
        sa.Column("footprint", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["forest_area_id"], ["forest_areas.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "forest_area_id",
            "product_id",
            name="uq_satellite_catalogue_product",
        ),
    )
    op.create_index(
        "ix_satellite_catalogue_products_forest_area_id",
        "satellite_catalogue_products",
        ["forest_area_id"],
    )
    op.create_index(
        "ix_sat_catalogue_area_acquisition",
        "satellite_catalogue_products",
        ["forest_area_id", "acquisition_datetime"],
    )
    op.create_index(
        "ix_sat_catalogue_product_tile",
        "satellite_catalogue_products",
        ["forest_area_id", "tile_id"],
    )

    op.create_table(
        "satellite_catalogue_search_jobs",
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("forest_area_id", sa.Integer(), nullable=False),
        sa.Column("started_by", sa.Integer(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("cloud_cover", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("pages_completed", sa.Integer(), nullable=False),
        sa.Column("products_found", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'PARTIAL', 'FAILED')",
            name="ck_satellite_catalogue_search_status",
        ),
        sa.ForeignKeyConstraint(["forest_area_id"], ["forest_areas.id"]),
        sa.ForeignKeyConstraint(["started_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index(
        "ix_satellite_catalogue_search_jobs_forest_area_id",
        "satellite_catalogue_search_jobs",
        ["forest_area_id"],
    )
    op.create_index(
        "ix_satellite_catalogue_search_jobs_started_by",
        "satellite_catalogue_search_jobs",
        ["started_by"],
    )
    op.create_index(
        "ix_satellite_catalogue_search_jobs_status",
        "satellite_catalogue_search_jobs",
        ["status"],
    )
    op.create_index(
        "ix_catalogue_search_area_created",
        "satellite_catalogue_search_jobs",
        ["forest_area_id", "created_at"],
    )
    op.create_index(
        "uq_active_catalogue_search_per_area",
        "satellite_catalogue_search_jobs",
        ["forest_area_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
        sqlite_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_active_catalogue_search_per_area",
        table_name="satellite_catalogue_search_jobs",
    )
    op.drop_index(
        "ix_catalogue_search_area_created",
        table_name="satellite_catalogue_search_jobs",
    )
    op.drop_index(
        "ix_satellite_catalogue_search_jobs_status",
        table_name="satellite_catalogue_search_jobs",
    )
    op.drop_index(
        "ix_satellite_catalogue_search_jobs_started_by",
        table_name="satellite_catalogue_search_jobs",
    )
    op.drop_index(
        "ix_satellite_catalogue_search_jobs_forest_area_id",
        table_name="satellite_catalogue_search_jobs",
    )
    op.drop_table("satellite_catalogue_search_jobs")
    op.drop_index(
        "ix_sat_catalogue_product_tile",
        table_name="satellite_catalogue_products",
    )
    op.drop_index(
        "ix_sat_catalogue_area_acquisition",
        table_name="satellite_catalogue_products",
    )
    op.drop_index(
        "ix_satellite_catalogue_products_forest_area_id",
        table_name="satellite_catalogue_products",
    )
    op.drop_table("satellite_catalogue_products")
    # Rows discovered without provider cloud metadata must be resolved before
    # reversing this nullable-column change on a database containing them.
    op.alter_column(
        "satellite_images",
        "cloud_cover_percentage",
        existing_type=sa.Float(),
        nullable=False,
    )
    op.alter_column(
        "satellite_images",
        "product_id",
        existing_type=sa.String(length=150),
        type_=sa.String(length=120),
        existing_nullable=False,
    )

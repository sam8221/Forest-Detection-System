"""Add persistent progress records for Copernicus downloads.

Revision ID: a6b29b1042ef
Revises: c81a6b2d9e47
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a6b29b1042ef"
down_revision: Union[str, Sequence[str], None] = "c81a6b2d9e47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "satellite_download_jobs",
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("forest_area_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.String(length=150), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("started_by", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="PREPARING",
            nullable=False,
        ),
        sa.Column(
            "downloaded_bytes",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("total_bytes", sa.BigInteger(), nullable=True),
        sa.Column("progress_percentage", sa.Float(), nullable=True),
        sa.Column("satellite_image_id", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('PREPARING', 'DOWNLOADING', 'VALIDATING', 'COMPLETED', 'FAILED')",
            name="ck_satellite_download_job_status",
        ),
        sa.CheckConstraint(
            "progress_percentage IS NULL OR "
            "(progress_percentage >= 0 AND progress_percentage <= 100)",
            name="ck_satellite_download_job_progress",
        ),
        sa.ForeignKeyConstraint(
            ["forest_area_id"], ["forest_areas.id"]
        ),
        sa.ForeignKeyConstraint(["started_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["satellite_image_id"], ["satellite_images.id"]
        ),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index(
        "ix_satellite_download_jobs_forest_area_id",
        "satellite_download_jobs",
        ["forest_area_id"],
    )
    op.create_index(
        "ix_satellite_download_jobs_started_by",
        "satellite_download_jobs",
        ["started_by"],
    )
    op.create_index(
        "ix_satellite_download_jobs_status",
        "satellite_download_jobs",
        ["status"],
    )
    op.create_index(
        "ix_satellite_download_jobs_satellite_image_id",
        "satellite_download_jobs",
        ["satellite_image_id"],
    )
    op.create_index(
        "ix_satellite_download_jobs_forest_created",
        "satellite_download_jobs",
        ["forest_area_id", "created_at"],
    )
    op.create_index(
        "uq_active_satellite_download_product",
        "satellite_download_jobs",
        ["forest_area_id", "product_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('PREPARING', 'DOWNLOADING', 'VALIDATING')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_active_satellite_download_product",
        table_name="satellite_download_jobs",
    )
    op.drop_index(
        "ix_satellite_download_jobs_forest_created",
        table_name="satellite_download_jobs",
    )
    op.drop_index(
        "ix_satellite_download_jobs_satellite_image_id",
        table_name="satellite_download_jobs",
    )
    op.drop_index(
        "ix_satellite_download_jobs_status",
        table_name="satellite_download_jobs",
    )
    op.drop_index(
        "ix_satellite_download_jobs_started_by",
        table_name="satellite_download_jobs",
    )
    op.drop_index(
        "ix_satellite_download_jobs_forest_area_id",
        table_name="satellite_download_jobs",
    )
    op.drop_table("satellite_download_jobs")

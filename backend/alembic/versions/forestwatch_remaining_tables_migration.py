"""
ForestWatch Zambia

Revision: Create remaining forest detection system tables
Revision ID: e91c6f2a4b7e
Revises: dff42c735d8c
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e91c6f2a4b7e"
down_revision: Union[str, Sequence[str], None] = "dff42c735d8c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the remaining ForestWatch Zambia application tables."""

    # ---------------------------------------------------------
    # Satellite Images
    # ---------------------------------------------------------
    op.create_table(
        "satellite_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("forest_area_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.String(length=120), nullable=False),
        sa.Column("tile_id", sa.String(length=20), nullable=False),
        sa.Column(
            "satellite_name",
            sa.String(length=20),
            nullable=False,
            server_default="Sentinel-2",
        ),
        sa.Column("acquisition_date", sa.Date(), nullable=False),
        sa.Column(
            "processing_level",
            sa.String(length=10),
            nullable=False,
            server_default="L2A",
        ),
        sa.Column(
            "cloud_cover_percentage",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("file_size_mb", sa.Float(), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column(
            "is_downloaded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_processed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["forest_area_id"],
            ["forest_areas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "forest_area_id",
            "product_id",
            name="uq_satellite_image_product",
        ),
    )

    op.create_index(
        "ix_satellite_images_id",
        "satellite_images",
        ["id"],
    )
    op.create_index(
        "ix_satellite_images_forest_area_id",
        "satellite_images",
        ["forest_area_id"],
    )
    op.create_index(
        "ix_satellite_images_product_id",
        "satellite_images",
        ["product_id"],
    )
    op.create_index(
        "ix_satellite_images_tile_id",
        "satellite_images",
        ["tile_id"],
    )
    op.create_index(
        "ix_satellite_images_acquisition_date",
        "satellite_images",
        ["acquisition_date"],
    )

    # ---------------------------------------------------------
    # Analysis Jobs
    # ---------------------------------------------------------
    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("forest_area_id", sa.Integer(), nullable=False),
        sa.Column("satellite_image_id", sa.Integer(), nullable=False),
        sa.Column("started_by", sa.Integer(), nullable=True),
        sa.Column(
            "job_type",
            sa.Enum(
                "MANUAL",
                "AUTOMATIC",
                name="analysisjobtype",
            ),
            nullable=False,
            server_default="AUTOMATIC",
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "RUNNING",
                "COMPLETED",
                "FAILED",
                "CANCELLED",
                name="analysisjobstatus",
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("cloud_cover_percentage", sa.Float(), nullable=True),
        sa.Column("ndvi_threshold", sa.Float(), nullable=True),
        sa.Column("vegetation_change_percentage", sa.Float(), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("execution_log", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["forest_area_id"],
            ["forest_areas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["satellite_image_id"],
            ["satellite_images.id"],
        ),
        sa.ForeignKeyConstraint(
            ["started_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_analysis_jobs_id", "analysis_jobs", ["id"])
    op.create_index(
        "ix_analysis_jobs_forest_area_id",
        "analysis_jobs",
        ["forest_area_id"],
    )
    op.create_index(
        "ix_analysis_jobs_satellite_image_id",
        "analysis_jobs",
        ["satellite_image_id"],
    )
    op.create_index(
        "ix_analysis_jobs_started_by",
        "analysis_jobs",
        ["started_by"],
    )

    # ---------------------------------------------------------
    # Detections
    # ---------------------------------------------------------
    op.create_table(
        "detections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("forest_area_id", sa.Integer(), nullable=False),
        sa.Column("satellite_image_id", sa.Integer(), nullable=False),
        sa.Column("analysis_job_id", sa.Integer(), nullable=False),
        sa.Column("verified_by", sa.Integer(), nullable=True),
        sa.Column("detected_area_hectares", sa.Float(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("ndvi_before", sa.Float(), nullable=False),
        sa.Column("ndvi_after", sa.Float(), nullable=False),
        sa.Column("vegetation_loss_percentage", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "VERIFIED",
                "REJECTED",
                "CLOSED",
                name="detectionstatus",
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["forest_area_id"],
            ["forest_areas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["satellite_image_id"],
            ["satellite_images.id"],
        ),
        sa.ForeignKeyConstraint(
            ["analysis_job_id"],
            ["analysis_jobs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_detections_id", "detections", ["id"])
    op.create_index(
        "ix_detections_forest_area_id",
        "detections",
        ["forest_area_id"],
    )
    op.create_index(
        "ix_detections_satellite_image_id",
        "detections",
        ["satellite_image_id"],
    )
    op.create_index(
        "ix_detections_analysis_job_id",
        "detections",
        ["analysis_job_id"],
    )
    op.create_index(
        "ix_detections_verified_by",
        "detections",
        ["verified_by"],
    )

    # ---------------------------------------------------------
    # Alerts
    # ---------------------------------------------------------
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("detection_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "alert_type",
            sa.Enum(
                "EMAIL",
                "DASHBOARD",
                name="alerttype",
            ),
            nullable=False,
            server_default="EMAIL",
        ),
        sa.Column(
            "priority",
            postgresql.ENUM(
                "LOW",
                "MEDIUM",
                "HIGH",
                "CRITICAL",
                name="prioritylevel",
                create_type=False,
            ),
            nullable=False,
            server_default="MEDIUM",
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "SENT",
                "FAILED",
                "READ",
                name="alertstatus",
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "is_resolved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["detection_id"],
            ["detections.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_alerts_id", "alerts", ["id"])
    op.create_index(
        "ix_alerts_detection_id",
        "alerts",
        ["detection_id"],
    )

    # ---------------------------------------------------------
    # Alert Recipients
    # ---------------------------------------------------------
    op.create_table(
        "alert_recipients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "is_read",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alerts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_alert_recipients_id",
        "alert_recipients",
        ["id"],
    )
    op.create_index(
        "ix_alert_recipients_alert_id",
        "alert_recipients",
        ["alert_id"],
    )
    op.create_index(
        "ix_alert_recipients_user_id",
        "alert_recipients",
        ["user_id"],
    )

    # ---------------------------------------------------------
    # Email Queue
    # ---------------------------------------------------------
    op.create_table(
        "email_queue",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_id", sa.Integer(), nullable=False),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("recipient_name", sa.String(length=150), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "PROCESSING",
                "SENT",
                "FAILED",
                name="emailqueuestatus",
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "max_retries",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alerts.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_email_queue_id", "email_queue", ["id"])
    op.create_index(
        "ix_email_queue_alert_id",
        "email_queue",
        ["alert_id"],
    )
    op.create_index(
        "ix_email_queue_recipient_email",
        "email_queue",
        ["recipient_email"],
    )


def downgrade() -> None:
    """Remove the remaining ForestWatch Zambia application tables."""

    op.drop_index(
        "ix_email_queue_recipient_email",
        table_name="email_queue",
    )
    op.drop_index(
        "ix_email_queue_alert_id",
        table_name="email_queue",
    )
    op.drop_index(
        "ix_email_queue_id",
        table_name="email_queue",
    )
    op.drop_table("email_queue")

    op.drop_index(
        "ix_alert_recipients_user_id",
        table_name="alert_recipients",
    )
    op.drop_index(
        "ix_alert_recipients_alert_id",
        table_name="alert_recipients",
    )
    op.drop_index(
        "ix_alert_recipients_id",
        table_name="alert_recipients",
    )
    op.drop_table("alert_recipients")

    op.drop_index(
        "ix_alerts_detection_id",
        table_name="alerts",
    )
    op.drop_index(
        "ix_alerts_id",
        table_name="alerts",
    )
    op.drop_table("alerts")

    op.drop_index(
        "ix_detections_verified_by",
        table_name="detections",
    )
    op.drop_index(
        "ix_detections_analysis_job_id",
        table_name="detections",
    )
    op.drop_index(
        "ix_detections_satellite_image_id",
        table_name="detections",
    )
    op.drop_index(
        "ix_detections_forest_area_id",
        table_name="detections",
    )
    op.drop_index(
        "ix_detections_id",
        table_name="detections",
    )
    op.drop_table("detections")

    op.drop_index(
        "ix_analysis_jobs_started_by",
        table_name="analysis_jobs",
    )
    op.drop_index(
        "ix_analysis_jobs_satellite_image_id",
        table_name="analysis_jobs",
    )
    op.drop_index(
        "ix_analysis_jobs_forest_area_id",
        table_name="analysis_jobs",
    )
    op.drop_index(
        "ix_analysis_jobs_id",
        table_name="analysis_jobs",
    )
    op.drop_table("analysis_jobs")

    op.drop_index(
        "ix_satellite_images_acquisition_date",
        table_name="satellite_images",
    )
    op.drop_index(
        "ix_satellite_images_tile_id",
        table_name="satellite_images",
    )
    op.drop_index(
        "ix_satellite_images_product_id",
        table_name="satellite_images",
    )
    op.drop_index(
        "ix_satellite_images_forest_area_id",
        table_name="satellite_images",
    )
    op.drop_index(
        "ix_satellite_images_id",
        table_name="satellite_images",
    )
    op.drop_table("satellite_images")

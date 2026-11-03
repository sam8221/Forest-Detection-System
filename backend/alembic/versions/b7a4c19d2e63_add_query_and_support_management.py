"""Add support queries, conversations, assignments and notices.

Revision ID: b7a4c19d2e63
Revises: e3b7d2f5a916
"""

from alembic import op
import sqlalchemy as sa


revision = "b7a4c19d2e63"
down_revision = ("e3b7d2f5a916", "b3a6e0f4c291")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_queries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reference", sa.String(32), nullable=False),
        sa.Column("officer_id", sa.Integer(), nullable=False),
        sa.Column("assigned_admin_id", sa.Integer(), nullable=True),
        sa.Column("district_id", sa.Integer(), nullable=True),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("priority", sa.String(12), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["officer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_admin_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["district_id"], ["districts.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("reference", name="uq_support_queries_reference"),
        sa.CheckConstraint(
            "category IN ('TECHNICAL_PROBLEM','SATELLITE_IMAGE_ISSUES','ANALYSIS_NDVI_ISSUES','DETECTION_ALERT_ISSUES','SMS_NOTIFICATION_ISSUES','ACCOUNT_LOGIN_ISSUES','DATA_ACCURACY_ISSUES','GENERAL_ENQUIRIES','OTHER')",
            name="ck_support_queries_category",
        ),
        sa.CheckConstraint("priority IN ('LOW','MEDIUM','HIGH','URGENT')", name="ck_support_queries_priority"),
        sa.CheckConstraint("status IN ('PENDING','UNDER_REVIEW','IN_PROGRESS','RESOLVED')", name="ck_support_queries_status"),
    )
    for column in ("officer_id", "assigned_admin_id", "district_id", "category", "priority", "status", "created_at"):
        op.create_index(f"ix_support_queries_{column}", "support_queries", [column])

    op.create_table(
        "support_query_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("query_id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("sender_role", sa.String(40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_internal_note", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["query_id"], ["support_queries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("sender_role IN ('ADMIN','PROVINCIAL_FORESTRY_OFFICER','DISTRICT_FORESTRY_OFFICER')", name="ck_support_message_sender_role"),
    )
    for column in ("query_id", "sender_id", "is_internal_note", "created_at"):
        op.create_index(f"ix_support_query_messages_{column}", "support_query_messages", [column])

    op.create_table(
        "support_query_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("query_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("uploader_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(80), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["query_id"], ["support_queries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["support_query_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploader_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("storage_key", name="uq_support_attachment_storage_key"),
        sa.CheckConstraint("size_bytes > 0", name="ck_support_attachment_size_positive"),
    )
    for column in ("query_id", "message_id", "uploader_id"):
        op.create_index(f"ix_support_query_attachments_{column}", "support_query_attachments", [column])

    op.create_table(
        "support_query_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("query_id", sa.Integer(), nullable=False),
        sa.Column("assigned_by_id", sa.Integer(), nullable=False),
        sa.Column("assigned_to_id", sa.Integer(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["query_id"], ["support_queries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_support_query_assignments_query_id", "support_query_assignments", ["query_id"])
    op.create_index("ix_support_query_assignments_assigned_to_id", "support_query_assignments", ["assigned_to_id"])
    op.create_index(
        "uq_support_query_assignment_active",
        "support_query_assignments",
        ["query_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
        sqlite_where=sa.text("ended_at IS NULL"),
    )

    op.create_table(
        "support_query_status_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("query_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["query_id"], ["support_queries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_support_query_status_history_query_id", "support_query_status_history", ["query_id"])
    op.create_index("ix_support_query_status_history_created_at", "support_query_status_history", ["created_at"])

    op.create_table(
        "support_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("query_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["query_id"], ["support_queries.id"], ondelete="CASCADE"),
    )
    for column in ("recipient_id", "query_id", "created_at"):
        op.create_index(f"ix_support_notifications_{column}", "support_notifications", [column])


def downgrade() -> None:
    for table, columns in (
        ("support_notifications", ("recipient_id", "query_id", "created_at")),
        ("support_query_status_history", ("query_id", "created_at")),
        ("support_query_assignments", ("query_id", "assigned_to_id", "active")),
        ("support_query_attachments", ("query_id", "message_id", "uploader_id")),
        ("support_query_messages", ("query_id", "sender_id", "is_internal_note", "created_at")),
        ("support_queries", ("officer_id", "assigned_admin_id", "district_id", "category", "priority", "status", "created_at")),
    ):
        for column in columns:
            if column == "active":
                op.drop_index("uq_support_query_assignment_active", table_name=table)
            else:
                op.drop_index(f"ix_{table}_{column}", table_name=table)
    for table in (
        "support_notifications", "support_query_status_history", "support_query_assignments",
        "support_query_attachments", "support_query_messages", "support_queries",
    ):
        op.drop_table(table)

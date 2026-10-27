"""
Add SMS alert notifications.

===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Revision: Add SMS alert notifications

Revision ID: f2c5d91a7e63
Revises: e7b3f1a92c04

Purpose:
    Adds the schema an SMS notification channel needs:
    a contact number on each account, a queue of outgoing
    messages with the provider's answer against each, and
    the SMS label on the alert-type enum.

What this migration does NOT do:
    It is entirely additive. No existing row is modified,
    no column is dropped or retyped, and no existing table
    is rewritten. The email queue is untouched, as are
    detections, analysis jobs and forest-area geometry.

Why sms_queue rather than widening email_queue:
    An SMS carries a provider message identifier, a status
    code and a per-message cost; an SMTP send produces none
    of those. Holding both in one table would mean renaming
    columns the email worker depends on and rewriting every
    existing email row, to no benefit.

Why the unique constraint matters:
    uq_sms_queue_alert_recipient allows one message per
    officer per alert. A duplicate SMS costs money per
    message and tells an officer twice about one clearing,
    which in a field report reads as two separate incidents.
    Retries increment retry_count on the existing row rather
    than inserting another, so the constraint cannot block a
    legitimate retry.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# ---------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------

revision = "f2c5d91a7e63"
down_revision = "e7b3f1a92c04"
branch_labels = None
depends_on = None


SMS_QUEUE_STATUS = "smsqueuestatus"


def upgrade() -> None:
    """Add the SMS queue, the contact number and the enums."""

    # -----------------------------------------------------
    # AlertType gains SMS
    #
    # ADD VALUE is additive and leaves every existing alert
    # untouched, following the approach taken in revision
    # d4a1c6e82b19. IF NOT EXISTS keeps the migration safe
    # to re-run and safe on a database where the label was
    # added by hand.
    # -----------------------------------------------------

    op.execute(
        "ALTER TYPE alerttype ADD VALUE IF NOT EXISTS 'SMS'"
    )

    # -----------------------------------------------------
    # Officer contact number
    #
    # Nullable, and nothing is backfilled. An officer with
    # no number is skipped when SMS is queued, exactly as
    # one with no email address is skipped today.
    # -----------------------------------------------------

    op.add_column(
        "users",
        sa.Column(
            "phone_number",
            sa.String(length=20),
            nullable=True,
            comment=(
                "Mobile number for SMS alerts, in E.164 "
                "form. Null when the officer has not "
                "supplied one."
            ),
        ),
    )

    # -----------------------------------------------------
    # The SMS queue status type
    #
    # Created explicitly, with create_type=False on the
    # column below, so the type exists exactly once and the
    # migration does not depend on the table creation
    # creating it as a side effect.
    #
    # There is deliberately no DELIVERED label: confirming
    # delivery needs a delivery-report callback the system
    # does not accept, so nothing could ever set it.
    # SUBMITTED means the provider accepted the message.
    # -----------------------------------------------------

    # postgresql.ENUM rather than sa.Enum, and create_type
    # False rather than left default, because that flag is a
    # PostgreSQL-dialect option. Generic sa.Enum accepts the
    # keyword and silently ignores it, so create_table then
    # emits CREATE TYPE a second time and the migration
    # fails with "type smsqueuestatus already exists".
    #
    # Created here explicitly, with checkfirst, so the type
    # exists exactly once and the migration is safe to
    # re-run after an interrupted attempt.

    sms_status = postgresql.ENUM(
        "PENDING",
        "PROCESSING",
        "SUBMITTED",
        "FAILED",
        name=SMS_QUEUE_STATUS,
        create_type=False,
    )

    sms_status.create(
        op.get_bind(),
        checkfirst=True,
    )

    op.create_table(
        "sms_queue",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "alert_id",
            sa.Integer(),
            nullable=False,
            comment="Alert this message notifies.",
        ),
        sa.Column(
            "recipient_phone",
            sa.String(length=20),
            nullable=False,
            comment=(
                "Recipient number in E.164 form, "
                "normalised before storage."
            ),
        ),
        sa.Column(
            "recipient_name",
            sa.String(length=150),
            nullable=False,
        ),
        sa.Column(
            "message",
            sa.Text(),
            nullable=False,
            comment="Body as submitted.",
        ),
        sa.Column(
            "status",
            sms_status,
            nullable=False,
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
            server_default="3",
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "provider_message_id",
            sa.String(length=100),
            nullable=True,
            comment=(
                "Provider identifier for the message."
            ),
        ),
        sa.Column(
            "provider_status_code",
            sa.Integer(),
            nullable=True,
            comment=(
                "Provider status code, stored as returned."
            ),
        ),
        sa.Column(
            "provider_status",
            sa.String(length=50),
            nullable=True,
            comment=(
                "Provider status text, stored as returned."
            ),
        ),
        sa.Column(
            "provider_cost",
            sa.String(length=30),
            nullable=True,
            comment=(
                "Charge the provider reported, including "
                "its currency."
            ),
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment=(
                "When the provider accepted the message. "
                "Acceptance is not receipt."
            ),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alerts.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "alert_id",
            "recipient_phone",
            name="uq_sms_queue_alert_recipient",
        ),
    )

    op.create_index(
        "ix_sms_queue_id",
        "sms_queue",
        ["id"],
    )

    op.create_index(
        "ix_sms_queue_alert_id",
        "sms_queue",
        ["alert_id"],
    )

    op.create_index(
        "ix_sms_queue_recipient_phone",
        "sms_queue",
        ["recipient_phone"],
    )

    # The worker's query is for pending rows, so the status
    # column is indexed.
    op.create_index(
        "ix_sms_queue_status",
        "sms_queue",
        ["status"],
    )


def downgrade() -> None:
    """
    Remove the SMS queue and the contact number.

    Dropping sms_queue discards the record of which messages
    were submitted to the provider. That is acceptable only
    because this revision introduced the table: no SMS
    predates it. Nothing belonging to an earlier revision is
    touched.

    The SMS label is left on the alerttype enum. Postgres
    cannot drop a single label, so removing it would mean
    rebuilding the type and rewriting the status of every
    alert row, which is a far heavier operation than the one
    being undone. An unused label is harmless; the Python
    AlertType enum simply stops offering it.
    """

    op.drop_index(
        "ix_sms_queue_status",
        table_name="sms_queue",
    )

    op.drop_index(
        "ix_sms_queue_recipient_phone",
        table_name="sms_queue",
    )

    op.drop_index(
        "ix_sms_queue_alert_id",
        table_name="sms_queue",
    )

    op.drop_index(
        "ix_sms_queue_id",
        table_name="sms_queue",
    )

    op.drop_table("sms_queue")

    postgresql.ENUM(
        name=SMS_QUEUE_STATUS,
        create_type=False,
    ).drop(
        op.get_bind(),
        checkfirst=True,
    )

    op.drop_column(
        "users",
        "phone_number",
    )

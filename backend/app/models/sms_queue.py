"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: SMS Queue Model

Purpose:
    Stores outgoing alert SMS messages waiting to be sent,
    and the provider's answer for each one.

Responsibilities:
    - Queue one outgoing message per officer per alert.
    - Record what the provider replied, verbatim.
    - Support bounded retries for transport failures.
    - Keep the record of attempts after an alert closes.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.database.session import Base
from app.models.base_model import AuditMixin
from app.models.enums import SmsQueueStatus

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.user import User


class SmsQueue(AuditMixin, Base):
    """
    One alert SMS addressed to one officer.

    Why this is a separate table from EmailQueue:

        The two channels share a shape but not their fields.
        An SMS carries a provider message identifier, a
        provider status code and a per-message cost, none of
        which an SMTP send produces. Widening email_queue to
        hold both would mean rewriting every existing email
        row and renaming columns the email worker depends
        on, for no gain: the email path works and is not
        what this table is for.

    Why the provider's answer is stored verbatim:

        provider_status_code and provider_status hold
        exactly what the provider returned, not an
        interpretation of it. The interpretation lives in
        app.services.sms_service, where it can be corrected
        without losing the evidence of what was actually
        said. For a dissertation that has to defend its
        claims, the raw answer is the record.

    What SUBMITTED does not mean:

        A row reaching SUBMITTED means the provider accepted
        the message. It does not mean an officer received
        it. The column is named submitted_at rather than
        sent_at for that reason; see SmsQueueStatus.
    """

    # ---------------------------------------------------------
    # Database Table
    # ---------------------------------------------------------
    __tablename__ = "sms_queue"

    __table_args__ = (
        # One message per officer per alert, enforced by the
        # database rather than only by the service that
        # writes these rows.
        #
        # A duplicate SMS is not a cosmetic problem: it costs
        # money per message, and it tells an officer twice
        # about one clearing, which in a field report reads
        # as two incidents. Retries increment retry_count on
        # the existing row and never insert a second, so this
        # constraint cannot block a legitimate retry.
        UniqueConstraint(
            "alert_id",
            "recipient_phone",
            name="uq_sms_queue_alert_recipient",
        ),
        Index(
            "uq_sms_queue_alert_user",
            "alert_id",
            "recipient_user_id",
            unique=True,
            postgresql_where=text("recipient_user_id IS NOT NULL"),
        ),
    )

    # ---------------------------------------------------------
    # Primary Key
    # ---------------------------------------------------------
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    # ---------------------------------------------------------
    # Alert
    # ---------------------------------------------------------
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("alerts.id"),
        nullable=False,
        index=True,
        comment="Alert this message notifies.",
    )

    # ---------------------------------------------------------
    # Recipient
    # ---------------------------------------------------------
    recipient_phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment=(
            "Recipient number in E.164 form, for example "
            "+260977123456. Normalised before it is stored, "
            "so the uniqueness constraint cannot be "
            "defeated by writing one number two ways. Null "
            "for a skipped recipient without a usable number."
        ),
    )

    recipient_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment=(
            "Officer account addressed. Null only for legacy "
            "queue rows whose account was not recorded."
        ),
    )

    skip_reason: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment=(
            "Non-sensitive reason a recipient was skipped, "
            "such as missing_phone_number."
        ),
    )

    recipient_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        comment="Officer the message was addressed to.",
    )

    # ---------------------------------------------------------
    # Message
    # ---------------------------------------------------------
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment=(
            "Body as submitted. Kept so the record shows "
            "what the officer was told, not merely that "
            "something was sent."
        ),
    )

    # ---------------------------------------------------------
    # Sending Status
    # ---------------------------------------------------------
    status: Mapped[SmsQueueStatus] = mapped_column(
        SqlEnum(SmsQueueStatus),
        default=SmsQueueStatus.PENDING,
        nullable=False,
        index=True,
        comment=(
            "Progress of this message. Indexed because the "
            "worker's query is for pending rows."
        ),
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Transport attempts made so far.",
    )

    max_retries: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
        comment=(
            "Attempts allowed before the message is failed. "
            "Lower than the email queue's five: each attempt "
            "may cost money, and a message the provider has "
            "already rejected will not be accepted later."
        ),
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment=(
            "Why the last attempt failed, in terms an "
            "administrator can act on. Truncated, and never "
            "contains credentials."
        ),
    )

    # ---------------------------------------------------------
    # Provider Response
    #
    # Recorded exactly as received. These columns are the
    # evidence of what the provider said; the system's
    # reading of them is the status column above.
    # ---------------------------------------------------------
    provider_message_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment=(
            "Provider identifier for the message, which is "
            "what a delivery query or a support request to "
            "the provider is made against."
        ),
    )

    provider_status_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment=(
            "Provider status code, stored as returned and "
            "not interpreted here."
        ),
    )

    provider_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment=(
            "Provider status text, stored as returned, for "
            "example Success."
        ),
    )

    provider_cost: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment=(
            "Charge the provider reported, including its "
            "currency. Kept as text because the currency is "
            "part of the figure and the sandbox reports a "
            "zero amount."
        ),
    )

    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment=(
            "When the provider accepted the message. Named "
            "submitted rather than sent because acceptance "
            "by the provider is not receipt by the officer."
        ),
    )

    # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------
    alert: Mapped["Alert"] = relationship(
        "Alert",
        back_populates="sms_queue",
        lazy="joined",
    )

    recipient_user: Mapped["User | None"] = relationship(
        "User",
        lazy="joined",
    )

    # ---------------------------------------------------------
    # String Representation
    # ---------------------------------------------------------
    def __repr__(self) -> str:
        """
        Return a readable representation of the row.

        The recipient number is deliberately left out: these
        appear in logs and exception output, and an officer's
        personal number does not belong there.
        """

        return (
            f"SmsQueue("
            f"id={self.id}, "
            f"alert_id={self.alert_id}, "
            f"status='{self.status.value}')"
        )

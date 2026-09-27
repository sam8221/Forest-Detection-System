"""
ForestWatch Zambia

Module: User Model

Purpose:
Defines the User entity responsible for
authentication and authorization.

Responsibilities:
- Store user account information.
- Support Role-Based Access Control (RBAC).
- Track account status.
- Maintain relationships with other entities.

Author:
Samuel Bikiloni

Project:
Web-Based Deforestation Detection and Alert System
Using Sentinel-2 Imagery in the Copperbelt, Zambia
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Integer,
    String,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.database.session import Base
from app.models.base_model import AuditMixin
from app.models.enums import UserRole


if TYPE_CHECKING:
    from app.models.alert_recipient import AlertRecipient
    from app.models.analysis_job import AnalysisJob
    from app.models.detection import Detection
    from app.models.district import District
    from app.models.forest_area import ForestArea
    from app.models.province import Province


class User(AuditMixin, Base):
    """
    Represents a system user.

    Users are Administrators, Provincial Forestry Officers
    or District Forestry Officers. The system is not
    public-facing: every account is provisioned by an
    administrator for a named Forestry Department officer.
    """

    # =========================================================
    # DATABASE TABLE
    # =========================================================

    __tablename__ = "users"

    # =========================================================
    # PRIMARY KEY
    # =========================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    # =========================================================
    # PERSONAL INFORMATION
    # =========================================================

    full_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        comment="Full name of the user.",
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
        comment="User email address.",
    )

    # =========================================================
    # AUTHENTICATION
    # =========================================================

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Encrypted password.",
    )

    must_change_password: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Force password change on first login.",
    )

    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful login.",
    )

    # =========================================================
    # AUTHORIZATION
    # =========================================================

    role: Mapped[UserRole] = mapped_column(
        SqlEnum(UserRole),
        default=UserRole.DISTRICT_FORESTRY_OFFICER,
        nullable=False,
        comment="Assigned user role.",
    )

    # =========================================================
    # JURISDICTION
    #
    # These fields are what jurisdiction-scoped access
    # (requirement FR-04) is enforced against.
    #
    # A district officer is assigned a district and sees only
    # forest areas inside it. A provincial officer is assigned
    # a province and sees every district within it. An
    # administrator has neither, because administration is
    # national and carries no operational alert duties.
    #
    # Enforcement happens in the repository layer, so an
    # out-of-jurisdiction record cannot be returned even if a
    # record ID is requested directly. Hiding data in the user
    # interface is not access control.
    # =========================================================

    province_id: Mapped[int | None] = mapped_column(
        ForeignKey("provinces.id"),
        nullable=True,
        index=True,
        comment=(
            "Province a provincial officer is responsible for."
        ),
    )

    district_id: Mapped[int | None] = mapped_column(
        ForeignKey("districts.id"),
        nullable=True,
        index=True,
        comment=(
            "District a district officer is responsible for."
        ),
    )

    # =========================================================
    # STATUS
    # =========================================================

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Account status.",
    )

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    # -----------------------------------------------------
    # Jurisdiction
    #
    # Loaded with a follow-up SELECT rather than a JOIN.
    #
    # A join looks cheaper for a single account, but User is
    # reachable from Detection, AnalysisJob and Alert, each
    # of which already joins its user eagerly. Joining the
    # province and district here multiplied through those
    # relationships: one query for the email queue was
    # arriving with six province joins and four district
    # joins attached.
    #
    # selectin keeps the jurisdiction available wherever an
    # account is shown, at the cost of one small extra
    # query, without widening every query that happens to
    # touch a user.
    # -----------------------------------------------------

    province: Mapped["Province | None"] = relationship(
        "Province",
        foreign_keys=[province_id],
        lazy="selectin",
    )

    district: Mapped["District | None"] = relationship(
        "District",
        foreign_keys=[district_id],
        lazy="selectin",
    )

    forest_areas: Mapped[list["ForestArea"]] = relationship(
        "ForestArea",
        back_populates="creator",
        foreign_keys="ForestArea.created_by",
        cascade="all, delete-orphan",
        lazy="select",
    )

    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(
        "AnalysisJob",
        back_populates="started_by_user",
        foreign_keys="AnalysisJob.started_by",
        lazy="select",
    )

    verified_detections: Mapped[list["Detection"]] = relationship(
        "Detection",
        back_populates="verified_by_user",
        foreign_keys="Detection.verified_by",
        lazy="select",
    )

    alert_recipients: Mapped[list["AlertRecipient"]] = relationship(
        "AlertRecipient",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )

    # =========================================================
    # STRING REPRESENTATION
    # =========================================================

    def __repr__(self) -> str:
        """
        Return a readable representation of the user.
        """

        return (
            f"User("
            f"id={self.id}, "
            f"full_name='{self.full_name}', "
            f"email='{self.email}', "
            f"role='{self.role.value}')"
        )
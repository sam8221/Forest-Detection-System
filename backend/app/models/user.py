"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
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

Version:
    1.0.0
===========================================================
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SqlEnum,
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
    from app.models.forest_area import ForestArea


class User(AuditMixin, Base):
    """
    Represents a system user.

    Users can be Administrators,
    Forestry Officers,
    or Researchers.
    """

    # ---------------------------------------------------------
    # Database Table
    # ---------------------------------------------------------
    __tablename__ = "users"

    # ---------------------------------------------------------
    # Primary Key
    # ---------------------------------------------------------
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    # ---------------------------------------------------------
    # Personal Information
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Authentication
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Authorization
    # ---------------------------------------------------------
    role: Mapped[UserRole] = mapped_column(
        SqlEnum(UserRole),
        default=UserRole.FORESTRY_OFFICER,
        nullable=False,
        comment="Assigned user role.",
    )

    # ---------------------------------------------------------
    # Status
    # ---------------------------------------------------------
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Account status.",
    )
        # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------

    forest_areas: Mapped[list["ForestArea"]] = relationship(
        "ForestArea",
        back_populates="creator",
        foreign_keys="ForestArea.created_by",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(
        "AnalysisJob",
        back_populates="started_by_user",
        foreign_keys="AnalysisJob.started_by",
        lazy="selectin",
    )

    verified_detections: Mapped[list["Detection"]] = relationship(
        "Detection",
        back_populates="verified_by_user",
        foreign_keys="Detection.verified_by",
        lazy="selectin",
    )

    alert_recipients: Mapped[list["AlertRecipient"]] = relationship(
        "AlertRecipient",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # ---------------------------------------------------------
    # String Representation
    # ---------------------------------------------------------
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
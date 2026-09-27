"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Jurisdiction Rules

Purpose:
    Decides whether an officer is permitted to see a
    record, based on the jurisdiction assigned to them.

Responsibilities:
    - Define the jurisdiction rule for each user role.
    - Provide a single decision used by both the API layer
      and the repository layer.

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

from app.models.enums import UserRole


# =========================================================
# JURISDICTION RULE
# =========================================================

def is_within_jurisdiction(
    role: UserRole,
    user_district_id: int | None,
    user_province_id: int | None,
    target_district_id: int | None,
    target_province_id: int | None,
) -> bool:
    """
    Decide whether a user may access a record.

    Args:
        role:
            Role held by the user requesting access.

        user_district_id:
            District assigned to the user, if any.

        user_province_id:
            Province assigned to the user, if any.

        target_district_id:
            District containing the record being requested.

        target_province_id:
            Province containing the record being requested.

    Returns:
        True when access is permitted.

    Rules:

        ADMIN
            Permitted everywhere. Administration is national.
            Administrators provision accounts and configure
            thresholds; they hold no operational alert duties.

        DISTRICT_FORESTRY_OFFICER
            Permitted only inside their assigned district.

        PROVINCIAL_FORESTRY_OFFICER
            Permitted anywhere inside their assigned province,
            which includes every district within it.

    This function is deliberately free of database and
    framework dependencies. It takes plain identifiers and
    returns a decision, which is what allows requirement
    FR-04 to be verified by test without a database.

    An officer with no jurisdiction assigned is refused
    rather than granted access. An unassigned account is
    treated as not yet authorised, never as unrestricted.
    """

    # -----------------------------------------------------
    # Administrators are unrestricted
    # -----------------------------------------------------

    if role == UserRole.ADMIN:
        return True

    # -----------------------------------------------------
    # District officers: exact district match
    # -----------------------------------------------------

    if role == UserRole.DISTRICT_FORESTRY_OFFICER:

        if user_district_id is None:
            return False

        return user_district_id == target_district_id

    # -----------------------------------------------------
    # Provincial officers: any district in their province
    # -----------------------------------------------------

    if role == UserRole.PROVINCIAL_FORESTRY_OFFICER:

        if user_province_id is None:
            return False

        return user_province_id == target_province_id

    # -----------------------------------------------------
    # Unknown role
    #
    # Refusing by default means adding a role to UserRole
    # without deciding its jurisdiction grants nothing.
    # -----------------------------------------------------

    return False

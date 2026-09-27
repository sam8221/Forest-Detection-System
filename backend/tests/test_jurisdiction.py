"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Jurisdiction Tests

Purpose:
    Verify jurisdiction-scoped access, requirement FR-04.

Responsibilities:
    - Confirm a district officer is refused a detection in
      another district.
    - Confirm a district officer is permitted their own
      district.
    - Confirm a provincial officer covers every district in
      their province.
    - Confirm a provincial officer is refused another
      province.
    - Confirm an administrator is unrestricted.
    - Confirm an officer with no jurisdiction is refused.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    The scenario used throughout is the one described in
    the dissertation: an officer assigned to Kitwe
    requesting a detection that lies in Ndola. Both are
    districts of the Copperbelt Province.
===========================================================
"""

from app.models.enums import UserRole
from app.services.jurisdiction import is_within_jurisdiction


# =========================================================
# TEST FIXTURES AS PLAIN IDENTIFIERS
# =========================================================

COPPERBELT = 1

NORTH_WESTERN = 2

KITWE = 10

NDOLA = 11

SOLWEZI = 20


# =========================================================
# DISTRICT OFFICER
# =========================================================

def test_district_officer_is_refused_another_district(
) -> None:
    """
    A Kitwe officer requesting a Ndola detection is refused,
    even though both districts share a province.

    This is the case demonstrated for Chapter Four: the
    officer requests the record by its identifier directly,
    and the server refuses it.
    """

    permitted = is_within_jurisdiction(
        role=UserRole.DISTRICT_FORESTRY_OFFICER,
        user_district_id=KITWE,
        user_province_id=None,
        target_district_id=NDOLA,
        target_province_id=COPPERBELT,
    )

    assert permitted is False


def test_district_officer_is_permitted_own_district(
) -> None:
    """
    A Kitwe officer is permitted a detection in Kitwe.
    """

    permitted = is_within_jurisdiction(
        role=UserRole.DISTRICT_FORESTRY_OFFICER,
        user_district_id=KITWE,
        user_province_id=None,
        target_district_id=KITWE,
        target_province_id=COPPERBELT,
    )

    assert permitted is True


def test_unassigned_district_officer_is_refused() -> None:
    """
    An officer whose district has not been set is refused.

    An account without a jurisdiction is treated as not yet
    authorised, never as unrestricted. Defaulting the other
    way would turn an incomplete account into a national
    one.
    """

    permitted = is_within_jurisdiction(
        role=UserRole.DISTRICT_FORESTRY_OFFICER,
        user_district_id=None,
        user_province_id=None,
        target_district_id=KITWE,
        target_province_id=COPPERBELT,
    )

    assert permitted is False


# =========================================================
# PROVINCIAL OFFICER
# =========================================================

def test_provincial_officer_covers_every_district(
) -> None:
    """
    A Copperbelt officer is permitted detections in both
    Kitwe and Ndola, because a province contains its
    districts.
    """

    for district in (KITWE, NDOLA):

        permitted = is_within_jurisdiction(
            role=UserRole.PROVINCIAL_FORESTRY_OFFICER,
            user_district_id=None,
            user_province_id=COPPERBELT,
            target_district_id=district,
            target_province_id=COPPERBELT,
        )

        assert permitted is True


def test_provincial_officer_is_refused_another_province(
) -> None:
    """
    A Copperbelt officer is refused a detection in Solwezi,
    which lies in North-Western Province.
    """

    permitted = is_within_jurisdiction(
        role=UserRole.PROVINCIAL_FORESTRY_OFFICER,
        user_district_id=None,
        user_province_id=COPPERBELT,
        target_district_id=SOLWEZI,
        target_province_id=NORTH_WESTERN,
    )

    assert permitted is False


def test_unassigned_provincial_officer_is_refused() -> None:
    """
    An officer whose province has not been set is refused.
    """

    permitted = is_within_jurisdiction(
        role=UserRole.PROVINCIAL_FORESTRY_OFFICER,
        user_district_id=None,
        user_province_id=None,
        target_district_id=KITWE,
        target_province_id=COPPERBELT,
    )

    assert permitted is False


# =========================================================
# ADMINISTRATOR
# =========================================================

def test_administrator_is_unrestricted() -> None:
    """
    An administrator is permitted everywhere, holding no
    district or province.

    Administration is national: the role provisions accounts
    and configures thresholds rather than reviewing alerts
    in a particular place.
    """

    permitted = is_within_jurisdiction(
        role=UserRole.ADMIN,
        user_district_id=None,
        user_province_id=None,
        target_district_id=SOLWEZI,
        target_province_id=NORTH_WESTERN,
    )

    assert permitted is True


# =========================================================
# ROLE COVERAGE
# =========================================================

def test_every_role_has_a_defined_decision() -> None:
    """
    Every role defined by the system produces a decision
    without raising.

    Adding a role to UserRole without deciding its
    jurisdiction grants it nothing, because the rule refuses
    anything it does not recognise.
    """

    for role in UserRole:

        decision = is_within_jurisdiction(
            role=role,
            user_district_id=KITWE,
            user_province_id=COPPERBELT,
            target_district_id=KITWE,
            target_province_id=COPPERBELT,
        )

        assert isinstance(decision, bool)

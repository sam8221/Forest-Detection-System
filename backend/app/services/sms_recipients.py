"""Recipient validation shared by SMS queueing and sending."""

from __future__ import annotations

from sqlalchemy import and_, or_

from app.models.enums import UserRole
from app.models.user import User
from app.services.sms_service import normalise_msisdn


def eligible_sms_officers_query(db, forest_area, district):
    """Build the active officer query for a forest area's jurisdiction."""

    return db.query(User).filter(
        User.is_active.is_(True),
        or_(
            and_(
                User.role == UserRole.DISTRICT_FORESTRY_OFFICER,
                User.district_id == forest_area.district_id,
            ),
            and_(
                User.role == UserRole.PROVINCIAL_FORESTRY_OFFICER,
                User.province_id == district.province_id,
            ),
        ),
    )


def sms_recipient_authorization_reason(user, forest_area) -> str | None:
    """Return why an account cannot receive this area's SMS alert."""

    if user is None:
        return "recipient_account_missing"

    if not user.is_active:
        return "recipient_inactive"

    if user.role == UserRole.DISTRICT_FORESTRY_OFFICER:
        if user.district_id == forest_area.district_id:
            return None
        return "outside_jurisdiction"

    district = getattr(forest_area, "district", None)

    if user.role == UserRole.PROVINCIAL_FORESTRY_OFFICER:
        if (
            district is not None
            and user.province_id == district.province_id
        ):
            return None
        return "outside_jurisdiction"

    return "role_not_authorized"


def sms_phone_skip_reason(raw_phone: str | None) -> str | None:
    """Return a non-sensitive reason when a phone cannot receive SMS."""

    if raw_phone is None or not raw_phone.strip():
        return "missing_phone_number"

    if normalise_msisdn(raw_phone) is None:
        return "invalid_phone_number"

    return None


def sms_queue_skip_reason(row) -> str | None:
    """Revalidate a queued recipient immediately before provider submission."""

    user = getattr(row, "recipient_user", None)

    # Legacy queue rows created before recipient_user_id was
    # introduced retain their recorded phone and original
    # eligibility decision.
    if user is None:
        return None

    alert = getattr(row, "alert", None)
    detection = getattr(alert, "detection", None)
    forest_area = getattr(detection, "forest_area", None)

    if forest_area is None:
        return "forest_area_unavailable"

    authorization_reason = sms_recipient_authorization_reason(
        user,
        forest_area,
    )

    if authorization_reason is not None:
        return authorization_reason

    phone_reason = sms_phone_skip_reason(user.phone_number)

    if phone_reason is not None:
        return phone_reason

    if normalise_msisdn(user.phone_number) != row.recipient_phone:
        return "phone_number_changed"

    return None

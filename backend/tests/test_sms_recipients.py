"""SMS jurisdiction, missing-number and queue idempotency tests."""

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.models.alert_recipient import AlertRecipient
from app.models.enums import PriorityLevel, SmsQueueStatus, UserRole
from app.models.sms_queue import SmsQueue
from app.services import alert_service as alert_service_module
from app.services.alert_service import AlertService
from app.services.sms_recipients import (
    eligible_sms_officers_query,
    sms_phone_skip_reason,
    sms_recipient_authorization_reason,
)


class QueryStub:
    def __init__(self, db, model):
        self.db = db
        self.model = model

    def filter(self, *criteria):
        return self

    def all(self):
        if self.model is AlertRecipient:
            return self.db.recipients
        if self.model is SmsQueue:
            return self.db.sms_rows
        return []


class MemorySmsDb:
    def __init__(self, recipients):
        self.recipients = recipients
        self.sms_rows = []
        self.statements = []
        self.query_count = 0

    def query(self, model):
        self.query_count += 1
        return QueryStub(self, model)

    def execute(self, statement):
        self.statements.append(statement)
        records = [
            {
                getattr(key, "key", key): value
                for key, value in record.items()
            }
            for record in statement._multi_values[0]
        ]

        for record in records:
            duplicate_user = any(
                row.alert_id == record["alert_id"]
                and row.recipient_user_id
                == record["recipient_user_id"]
                for row in self.sms_rows
            )
            duplicate_phone = (
                record["recipient_phone"] is not None
                and any(
                    row.alert_id == record["alert_id"]
                    and row.recipient_phone
                    == record["recipient_phone"]
                    for row in self.sms_rows
                )
            )

            if duplicate_user or duplicate_phone:
                continue

            self.sms_rows.append(SimpleNamespace(**record))

    def commit(self):
        pass


def officer(
    user_id,
    *,
    role=UserRole.DISTRICT_FORESTRY_OFFICER,
    active=True,
    district_id=7,
    province_id=None,
    phone_number="+260971234567",
):
    return SimpleNamespace(
        id=user_id,
        full_name=f"Officer {user_id}",
        role=role,
        is_active=active,
        district_id=district_id,
        province_id=province_id,
        phone_number=phone_number,
    )


def test_officer_query_is_scoped_to_active_district_and_province_roles():
    forest_area = SimpleNamespace(district_id=7)
    district = SimpleNamespace(province_id=3)

    query = eligible_sms_officers_query(
        Session(),
        forest_area,
        district,
    )
    sql = str(
        query.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "users.is_active IS true" in sql
    assert "users.district_id = 7" in sql
    assert "users.province_id = 3" in sql
    assert "DISTRICT_FORESTRY_OFFICER" in sql
    assert "PROVINCIAL_FORESTRY_OFFICER" in sql
    assert "ADMIN" not in sql


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        (officer(1), None),
        (
            officer(
                2,
                role=UserRole.PROVINCIAL_FORESTRY_OFFICER,
                district_id=None,
                province_id=3,
            ),
            None,
        ),
        (officer(3, district_id=8), "outside_jurisdiction"),
        (
            officer(
                4,
                role=UserRole.PROVINCIAL_FORESTRY_OFFICER,
                district_id=None,
                province_id=4,
            ),
            "outside_jurisdiction",
        ),
        (officer(5, active=False), "recipient_inactive"),
        (
            officer(6, role=UserRole.ADMIN, district_id=None),
            "role_not_authorized",
        ),
    ],
)
def test_sms_recipient_authorization(candidate, expected):
    area = SimpleNamespace(
        district_id=7,
        district=SimpleNamespace(province_id=3),
    )

    assert sms_recipient_authorization_reason(candidate, area) == expected


@pytest.mark.parametrize(
    ("phone_number", "expected"),
    [
        (None, "missing_phone_number"),
        ("   ", "missing_phone_number"),
        ("0211234567", "invalid_phone_number"),
        ("+260971234567", None),
    ],
)
def test_phone_skip_reason_is_specific_and_contains_no_number(
    phone_number,
    expected,
):
    assert sms_phone_skip_reason(phone_number) == expected


def test_queue_selects_jurisdiction_officers_and_records_number_skips(
    monkeypatch,
    caplog,
):
    caplog.set_level("INFO")

    forest_area = SimpleNamespace(
        id=5,
        name="Chichele",
        district_id=7,
        district=SimpleNamespace(name="Kitwe", province_id=3),
    )
    detection = SimpleNamespace(
        id=31,
        forest_area_id=5,
        forest_area=forest_area,
        detected_area_hectares=2.3,
    )
    alert = SimpleNamespace(
        id=41,
        detection_id=31,
        detection=detection,
        priority=PriorityLevel.CRITICAL,
    )

    candidates = [
        officer(1, phone_number="0971234567"),
        officer(
            2,
            role=UserRole.PROVINCIAL_FORESTRY_OFFICER,
            district_id=None,
            province_id=3,
            phone_number="0771234567",
        ),
        officer(3, phone_number=None),
        officer(4, phone_number="0211234567"),
        officer(5, district_id=8),
        officer(6, active=False),
        officer(7, role=UserRole.ADMIN, district_id=None),
    ]
    db = MemorySmsDb(
        [SimpleNamespace(user=user) for user in candidates]
    )
    monkeypatch.setattr(
        alert_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            sms_enabled=True,
            sms_min_priority="HIGH",
        ),
    )

    AlertService(db).queue_sms_notifications(alert)

    rows_by_user = {
        row.recipient_user_id: row
        for row in db.sms_rows
    }
    assert set(rows_by_user) == {1, 2, 3, 4}
    assert rows_by_user[1].status is SmsQueueStatus.PENDING
    assert rows_by_user[1].recipient_phone == "+260971234567"
    assert rows_by_user[2].status is SmsQueueStatus.PENDING
    assert rows_by_user[2].recipient_phone == "+260771234567"
    assert rows_by_user[3].status is SmsQueueStatus.SKIPPED
    assert rows_by_user[3].recipient_phone is None
    assert rows_by_user[3].skip_reason == "missing_phone_number"
    assert rows_by_user[4].status is SmsQueueStatus.SKIPPED
    assert rows_by_user[4].skip_reason == "invalid_phone_number"

    # Logs identify the row and reason without logging a phone.
    assert "missing_phone_number" in caplog.text
    assert "invalid_phone_number" in caplog.text
    assert "0971234567" not in caplog.text
    assert "0211234567" not in caplog.text

    statement_sql = str(
        db.statements[0].compile(dialect=postgresql.dialect())
    )
    assert "ON CONFLICT DO NOTHING" in statement_sql

    # Re-running the same alert is idempotent for queued and skipped rows.
    AlertService(db).queue_sms_notifications(alert)
    assert len(db.sms_rows) == 4
    assert len(db.statements) == 1


def test_low_priority_detection_does_not_queue_sms(monkeypatch):
    db = MemorySmsDb([])
    monkeypatch.setattr(
        alert_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            sms_enabled=True,
            sms_min_priority="HIGH",
        ),
    )
    alert = SimpleNamespace(priority=PriorityLevel.MEDIUM)

    AlertService(db).queue_sms_notifications(alert)

    assert db.query_count == 0

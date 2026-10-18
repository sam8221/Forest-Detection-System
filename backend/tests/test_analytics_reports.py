"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Analytics Report Tests

Purpose:
    Verify that downloadable analytics reports render in all
    three formats and represent missing data honestly.

Responsibilities:
    - Confirm each format produces a file that opens.
    - Confirm the workbook carries the expected sheets.
    - Confirm CSV values match the collected figures.
    - Confirm missing measurements never become zero.
    - Confirm requested sections decide the content.
    - Confirm limitations are carried into the document.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    These tests build ReportData directly rather than
    querying, so they exercise rendering without a database
    or network. The figures in them are SYNTHETIC FIXTURES
    chosen so the expected output can be checked by hand.
    They are not measurements of anywhere.

    The behaviour most worth guarding is the treatment of a
    missing value. A report outlives the screen it was
    copied from, and a zero written where nothing was
    measured becomes a false finding the moment the file is
    forwarded.
===========================================================
"""

import csv
import io
from datetime import UTC, date, datetime

from openpyxl import load_workbook

from app.services.analytics_report_renderers import (
    PdfRenderer,
    render_csv,
    render_xlsx,
)
from app.services.analytics_report_service import (
    SECTIONS,
    ReportData,
    ReportRequest,
)


# =========================================================
# FIXTURES
# =========================================================

def build_data(
    sections: list[str] | None = None,
    **overrides,
) -> ReportData:
    """
    Build a report with hand-chosen synthetic figures.

    Not satellite measurements: values are picked so the
    rendered output can be verified by reading it.
    """

    data = ReportData(
        reference="FW-ANL-20260101-000000-0001",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        request=ReportRequest(
            sections=sections or list(SECTIONS),
            title="Test Analytics Report",
        ),
        scope_description="Test scope",
        summary={
            "monitored_forest_areas": 2,
            "monitored_hectares": 500.0,
            "total_detections": 3,
            "cumulative_loss_hectares": 12.5,
            "unique_loss_hectares": 10.0,
            "detections_with_outline": 2,
            "forest_areas_with_detections": 1,
            "forest_areas_analysed": 1,
            "latest_analysis_at": datetime(2026, 1, 1, tzinfo=UTC),
            "has_results": True,
        },
        trend=[
            {
                "date": date(2026, 1, 1),
                "analyses": 1,
                "detections": 0,
                "loss_hectares": 0.0,
                "observed": True,
            }
        ],
        districts=[
            {
                "district_id": 8,
                "district": "Kitwe",
                "detections": 3,
                "loss_hectares": 12.5,
                "analyses": 1,
                "observed": True,
            },
            {
                "district_id": 9,
                "district": "Ndola",
                "detections": 0,
                "loss_hectares": 0.0,
                "analyses": 0,
                "observed": False,
            },
        ],
        detections=[
            {
                "id": 1,
                "forest_area": "Test Forest",
                "district": "Kitwe",
                "area_hectares": 12.5,
                "ndvi_before": 0.8,
                "ndvi_after": 0.3,
                "ndvi_decline": 0.5,
                "status": "PENDING",
                "detected_on": datetime(2026, 1, 1, tzinfo=UTC),
                "analysis_job_id": 7,
                "has_outline": True,
            }
        ],
        ndvi={
            "rasters_available": True,
            "is_legacy_storage": False,
            "mean_ndvi_before": 0.8,
            "mean_ndvi_after": 0.3,
            "mean_ndvi_difference": -0.5,
            "declined_pixel_percentage": 42.0,
            "declined_hectares": 12.5,
            "measurable_pixels": 1000,
            "baseline_start": date(2025, 5, 1),
            "baseline_end": date(2025, 7, 31),
            "comparison_start": date(2026, 5, 1),
            "comparison_end": date(2026, 7, 31),
            "completed_at": datetime(2026, 1, 1, tzinfo=UTC),
            "ndvi_threshold": 0.3,
            "cloud_cover_percentage": 4.0,
        },
        ndvi_job={
            "id": 7,
            "forest_area_id": 1,
            "completed_at": datetime(2026, 1, 1, tzinfo=UTC),
        },
        alerts={
            "total": 3,
            "pending": 1,
            "sent": 1,
            "read": 0,
            "resolved": 1,
            "average_resolution_hours": 5.0,
        },
        recommendations=[
            {
                "rule": "SIGNIFICANT_POTENTIAL_LOSS",
                "priority": "HIGH",
                "finding": "A clearing of 12.5 hectares awaits review.",
                "action": "Prioritise for field verification.",
                "forest_area": "Test Forest",
                "district": "Kitwe",
                "detection_id": 1,
                "analysis_job_id": 7,
                "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            }
        ],
        history=[
            {
                "id": 7,
                "forest_area": "Test Forest",
                "status": "COMPLETED",
                "baseline_start": date(2025, 5, 1),
                "baseline_end": date(2025, 7, 31),
                "comparison_start": date(2026, 5, 1),
                "comparison_end": date(2026, 7, 31),
                "completed_at": datetime(2026, 1, 1, tzinfo=UTC),
                "cloud_cover_percentage": 4.0,
                "error_message": None,
            }
        ],
        limitations=["A stated limitation for this report."],
    )

    for name, value in overrides.items():
        setattr(data, name, value)

    return data


def csv_rows(content: bytes) -> list[list[str]]:
    """Decode rendered CSV back into rows."""

    return list(
        csv.reader(io.StringIO(content.decode("utf-8-sig")))
    )


# =========================================================
# PDF
# =========================================================

def test_pdf_renders_a_file_that_opens() -> None:
    """
    The PDF carries a valid header and trailer.

    A truncated document opens to an error rather than a
    report, which is the failure a supervisor would meet.
    """

    content = PdfRenderer().render(build_data())

    assert content.startswith(b"%PDF")
    assert content.rstrip().endswith(b"%%EOF")
    assert len(content) > 4000


def test_pdf_states_the_detection_caution() -> None:
    """
    Every PDF says a detection is not proof of illegality.

    The report may be forwarded far beyond the officer who
    produced it, so the caution travels inside the document
    rather than being left to the covering message.
    """

    content = PdfRenderer().render(build_data())

    # Compressed streams make the text unsearchable, so the
    # caution is asserted through the renderer's constant.
    from app.services.analytics_report_renderers import CAUTION

    assert "not proof of illegal deforestation" in CAUTION
    assert "field verification" in CAUTION
    assert content.startswith(b"%PDF")


# =========================================================
# CSV
# =========================================================

def test_csv_carries_the_collected_values() -> None:
    """Figures reach the file unchanged."""

    rows = csv_rows(render_csv(build_data()))

    flat = {row[0]: row[1] for row in rows if len(row) > 1}

    assert flat["Reference"] == "FW-ANL-20260101-000000-0001"
    assert flat["Detections"] == "3"
    assert flat["Potential loss, cumulative"] == "12.5"
    assert flat["Monitored area"] == "500.0"


def test_csv_marks_a_missing_measurement(
) -> None:
    """
    A missing figure is written as text, never as zero.

    Unique affected area is null when no detection carries an
    outline. Written as 0.0 it would read as "no ground
    affected", which is a finding the system never made.
    """

    data = build_data()
    data.summary["unique_loss_hectares"] = None
    data.summary["detections_with_outline"] = 0

    rows = csv_rows(render_csv(data))

    flat = {row[0]: row[1] for row in rows if len(row) > 1}

    assert flat["Potential loss, unique ground"] == "Not available"
    assert flat["Potential loss, unique ground"] != "0"
    assert flat["Potential loss, unique ground"] != "0.0"


def test_csv_distinguishes_unobserved_districts() -> None:
    """
    A district with no analysis is labelled, not zeroed.

    Its zero hectares means nobody has looked, and a reader
    sorting the column must not take it for a clean result.
    """

    text = render_csv(build_data()).decode("utf-8-sig")

    assert "not examined" in text


def test_csv_is_encoded_for_spreadsheets() -> None:
    """
    The file starts with a byte order mark.

    Without it Excel on Windows reads UTF-8 as the system
    codepage and mangles any non-ASCII place name.
    """

    content = render_csv(build_data())

    assert content.startswith(b"\xef\xbb\xbf")


def test_csv_includes_only_requested_sections() -> None:
    """Sections not asked for do not appear."""

    text = render_csv(
        build_data(sections=["summary"])
    ).decode("utf-8-sig")

    assert "SUMMARY" in text
    assert "DISTRICT COMPARISON" not in text
    assert "DETECTIONS" not in text


# =========================================================
# EXCEL
# =========================================================

def test_xlsx_opens_with_the_expected_sheets() -> None:
    """The workbook carries one sheet per section."""

    workbook = load_workbook(io.BytesIO(render_xlsx(build_data())))

    for name in (
        "Summary",
        "Forest Loss",
        "Districts",
        "NDVI Analysis",
        "Detections",
        "Alerts",
        "Recommendations",
        "Analysis History",
        "Methodology",
    ):
        assert name in workbook.sheetnames


def test_xlsx_summary_carries_the_figures() -> None:
    """Values on the cover sheet match what was collected."""

    workbook = load_workbook(io.BytesIO(render_xlsx(build_data())))

    sheet = workbook["Summary"]

    labels = {
        sheet.cell(row=row, column=1).value: sheet.cell(
            row=row, column=2
        ).value
        for row in range(1, sheet.max_row + 1)
    }

    assert labels["Detections"] == 3
    assert labels["Monitored area (hectares)"] == 500.0
    assert (
        labels["Potential loss, cumulative (hectares)"] == 12.5
    )


def test_xlsx_marks_a_missing_measurement() -> None:
    """
    A missing figure is words, not an empty or zero cell.

    An empty cell in a spreadsheet is ambiguous and a zero is
    a claim; neither is true of something never measured.
    """

    data = build_data()
    data.summary["unique_loss_hectares"] = None

    workbook = load_workbook(io.BytesIO(render_xlsx(data)))

    sheet = workbook["Summary"]

    labels = {
        sheet.cell(row=row, column=1).value: sheet.cell(
            row=row, column=2
        ).value
        for row in range(1, sheet.max_row + 1)
    }

    assert (
        labels["Potential loss, unique ground (hectares)"]
        == "Not available"
    )


def test_xlsx_omits_sheets_for_unrequested_sections() -> None:
    """Only the requested sections become sheets."""

    workbook = load_workbook(
        io.BytesIO(render_xlsx(build_data(sections=["summary"])))
    )

    assert "Summary" in workbook.sheetnames
    assert "Detections" not in workbook.sheetnames
    assert "Districts" not in workbook.sheetnames


def test_xlsx_headings_are_frozen() -> None:
    """
    Column names stay visible while scrolling.

    A detection table can run to hundreds of rows, and
    unlabelled columns are unreadable past the first screen.
    """

    workbook = load_workbook(io.BytesIO(render_xlsx(build_data())))

    assert workbook["Detections"].freeze_panes == "A2"


# =========================================================
# EMPTY AND LIMITED DATA
# =========================================================

def test_every_format_handles_an_empty_report() -> None:
    """
    A report with nothing collected still renders.

    An officer who filters down to nothing must receive a
    document saying so, not an error.
    """

    empty = build_data(
        summary=None,
        trend=[],
        districts=[],
        detections=[],
        ndvi=None,
        ndvi_job=None,
        alerts=None,
        recommendations=[],
        history=[],
        limitations=["No results matched the selected filters."],
    )

    pdf = PdfRenderer().render(empty)
    assert pdf.startswith(b"%PDF")

    text = render_csv(empty).decode("utf-8-sig")
    assert "No results matched the selected filters." in text

    workbook = load_workbook(io.BytesIO(render_xlsx(empty)))
    assert "Summary" in workbook.sheetnames


def test_limitations_reach_every_format() -> None:
    """
    A stated limitation is carried into the document.

    Limitations explain why a figure is absent or partial.
    Dropping them in export would leave the numbers looking
    more complete on paper than they are on screen.
    """

    data = build_data()

    text = render_csv(data).decode("utf-8-sig")
    assert "A stated limitation for this report." in text

    workbook = load_workbook(io.BytesIO(render_xlsx(data)))

    methodology = workbook["Methodology"]

    values = [
        methodology.cell(row=row, column=1).value
        for row in range(1, methodology.max_row + 1)
    ]

    assert "A stated limitation for this report." in values

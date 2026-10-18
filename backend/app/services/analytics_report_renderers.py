"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Analytics Report Renderers

Purpose:
    Renders collected analytics as PDF, CSV or Excel.

Responsibilities:
    - Lay out a printable PDF report.
    - Export the same figures as CSV.
    - Export them as a multi-sheet workbook.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    Rendering is separated from collection so the three
    formats cannot disagree about the numbers: they all
    receive the same ReportData, gathered once.

    Nothing here queries the database or computes a
    statistic. If a value is missing it is written as
    "Not available" rather than as zero, in every format. A
    zero in a spreadsheet is a measurement, and whoever
    opens the file later will have no way to tell it was
    never measured.

    PDF styling is borrowed from ReportService so all the
    system's reports share a masthead, footer and page
    numbering.

Version:
    1.0.0
===========================================================
"""

from __future__ import annotations

import csv
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from app.services.analytics_report_service import (
    UNAVAILABLE,
    ReportData,
)
from app.services.report_service import ReportService


# =========================================================
# SHARED FORMATTING
# =========================================================

def number(value, places: int = 2) -> str:
    """Format a number, or say plainly that it is missing."""

    if value is None:
        return UNAVAILABLE

    return f"{float(value):,.{places}f}"


def plain(value, fallback: str = UNAVAILABLE) -> str:
    """Render a value as text without inventing one."""

    if value is None or value == "":
        return fallback

    return str(value)


METHODOLOGY = (
    "Vegetation is measured with the Normalised Difference "
    "Vegetation Index, NDVI = (NIR - Red) / (NIR + Red), from "
    "Sentinel-2 Level-2A imagery using band 8 for "
    "near-infrared and band 4 for red, both at 10 m. Cloud "
    "and cloud shadow are removed using the Scene "
    "Classification Layer before any comparison."
)

SEASONAL = (
    "Change detection compares equivalent seasonal windows in "
    "different years. Miombo woodland across the Copperbelt "
    "sheds leaf every dry season, so comparing adjacent "
    "months would report vegetation loss across the entire "
    "province. A clearing is reported only where the decline "
    "reaches the configured NDVI threshold and the patch "
    "covers at least 0.5 hectares, the area criterion in the "
    "Forests Act No. 4 of 2015. Only that area criterion is "
    "applied: the system does not measure canopy cover or "
    "tree height."
)

CAUTION = (
    "A detection is POTENTIAL vegetation loss, not proof of "
    "illegal deforestation. Harvest, fire, drought, disease "
    "and cultivation all reduce the vegetation index, and "
    "this system does not distinguish them from felling. "
    "Every location requires field verification before any "
    "conclusion is drawn about its cause or lawfulness."
)


# =========================================================
# PDF
# =========================================================

class PdfRenderer:
    """Lays the collected analytics out as a PDF."""

    def __init__(self) -> None:
        self.base = ReportService()
        self.styles = self.base.styles

    def render(self, data: ReportData) -> bytes:
        """Return the finished PDF as bytes."""

        flow: list = []

        flow += self.base.masthead(
            data.request.title,
            "Deforestation monitoring, Copperbelt Province",
        )

        flow += self._information(data)
        flow += self._summary(data)
        flow += self._trend(data)
        flow += self._districts(data)
        flow += self._ndvi(data)
        flow += self._detections(data)
        flow += self._alerts(data)
        flow += self._recommendations(data)
        flow += self._history(data)
        flow += self._methodology(data)

        return self.base.build(flow, data.request.title)

    # -----------------------------------------------------
    # SECTIONS
    # -----------------------------------------------------

    def _information(self, data: ReportData) -> list:
        return [
            Paragraph("Report information", self.styles["heading"]),
            self.base.field_table(
                [
                    ("Reference", data.reference),
                    ("Generated", self.base.moment(data.generated_at)),
                    ("Scope", data.scope_description),
                    (
                        "Sections",
                        ", ".join(
                            s.replace("_", " ")
                            for s in data.request.sections
                        ),
                    ),
                ]
            ),
        ]

    def _summary(self, data: ReportData) -> list:
        if data.summary is None:
            return []

        s = data.summary

        return [
            Paragraph("Executive summary", self.styles["heading"]),
            self.base.field_table(
                [
                    (
                        "Monitored forest area",
                        f"{number(s['monitored_hectares'])} ha across "
                        f"{s['monitored_forest_areas']} areas",
                    ),
                    (
                        "Potential loss, cumulative",
                        f"{number(s['cumulative_loss_hectares'])} ha "
                        "(ground detected twice counts twice)",
                    ),
                    (
                        "Potential loss, unique ground",
                        UNAVAILABLE
                        if s["unique_loss_hectares"] is None
                        else (
                            f"{number(s['unique_loss_hectares'])} ha "
                            f"from {s['detections_with_outline']} "
                            "mapped outlines"
                        ),
                    ),
                    (
                        "Detections",
                        f"{s['total_detections']} across "
                        f"{s['forest_areas_with_detections']} areas",
                    ),
                    (
                        "Forest areas analysed",
                        str(s["forest_areas_analysed"]),
                    ),
                    (
                        "Latest analysis",
                        self.base.moment(s["latest_analysis_at"]),
                    ),
                ]
            ),
        ]

    def _trend(self, data: ReportData) -> list:
        if not data.has("forest_loss") or not data.trend:
            return []

        return [
            Paragraph(
                "Potential forest loss over time",
                self.styles["heading"],
            ),
            Paragraph(
                "One row per day an analysis completed. A zero "
                "is a measured zero: the analysis ran and found "
                "no clearing large enough to report. Days absent "
                "from this table were not observed.",
                self.styles["note"],
            ),
            Spacer(1, 4),
            self._table(
                ["Date", "Analyses", "Detections", "Hectares"],
                [
                    [
                        str(row["date"]),
                        str(row["analyses"]),
                        str(row["detections"]),
                        number(row["loss_hectares"]),
                    ]
                    for row in data.trend
                ],
            ),
        ]

    def _districts(self, data: ReportData) -> list:
        if not data.has("districts") or not data.districts:
            return []

        return [
            Paragraph(
                "Potential loss by district", self.styles["heading"]
            ),
            self._table(
                [
                    "District",
                    "Detections",
                    "Hectares",
                    "Analyses",
                    "Observed",
                ],
                [
                    [
                        row["district"],
                        str(row["detections"]),
                        number(row["loss_hectares"]),
                        str(row["analyses"]),
                        "yes" if row["observed"] else "NOT EXAMINED",
                    ]
                    for row in data.districts
                ],
            ),
        ]

    def _ndvi(self, data: ReportData) -> list:
        if not data.has("ndvi"):
            return []

        head = [
            Paragraph("NDVI change analysis", self.styles["heading"])
        ]

        if data.ndvi is None:
            return head + [
                Paragraph(
                    "No completed analysis was available for the "
                    "selected filters, so no NDVI comparison "
                    "could be included.",
                    self.styles["body"],
                )
            ]

        n = data.ndvi

        return head + [
            self.base.field_table(
                [
                    ("Analysis", str(data.ndvi_job["id"])),
                    (
                        "Baseline window",
                        f"{plain(n['baseline_start'], '—')} to "
                        f"{plain(n['baseline_end'], '—')}",
                    ),
                    (
                        "Comparison window",
                        f"{plain(n['comparison_start'], '—')} to "
                        f"{plain(n['comparison_end'], '—')}",
                    ),
                    (
                        "Mean NDVI, earlier",
                        number(n["mean_ndvi_before"], 4),
                    ),
                    (
                        "Mean NDVI, later",
                        number(n["mean_ndvi_after"], 4),
                    ),
                    (
                        "Difference (later minus earlier)",
                        number(n["mean_ndvi_difference"], 4),
                    ),
                    (
                        "Valid pixels that declined",
                        UNAVAILABLE
                        if n["declined_pixel_percentage"] is None
                        else f"{n['declined_pixel_percentage']}%",
                    ),
                    (
                        "Area past threshold",
                        UNAVAILABLE
                        if n["declined_hectares"] is None
                        else f"{number(n['declined_hectares'])} ha",
                    ),
                    ("NDVI threshold", plain(n["ndvi_threshold"])),
                ]
            ),
            Spacer(1, 4),
            Paragraph(
                "These are whole-area statistics, over every "
                "pixel measurable on both dates. They are not "
                "the means over detected patches, which describe "
                "only ground already selected for having lost "
                "vegetation, and the two must not be read as one "
                "series.",
                self.styles["note"],
            ),
        ]

    def _detections(self, data: ReportData) -> list:
        if not data.has("detections"):
            return []

        head = [
            Paragraph("Detection details", self.styles["heading"])
        ]

        if not data.detections:
            return head + [
                Paragraph(
                    "No detections fall within the selected "
                    "filters.",
                    self.styles["body"],
                )
            ]

        return head + [
            self._table(
                [
                    "ID",
                    "Forest area",
                    "District",
                    "Hectares",
                    "NDVI before",
                    "NDVI after",
                    "Status",
                ],
                [
                    [
                        str(d["id"]),
                        d["forest_area"],
                        d["district"],
                        number(d["area_hectares"]),
                        number(d["ndvi_before"], 4),
                        number(d["ndvi_after"], 4),
                        plain(d["status"]),
                    ]
                    for d in data.detections
                ],
                widths=[12, 38, 26, 22, 25, 25, 26],
            )
        ]

    def _alerts(self, data: ReportData) -> list:
        if not data.has("alerts") or data.alerts is None:
            return []

        a = data.alerts

        return [
            Paragraph("Alerts", self.styles["heading"]),
            self.base.field_table(
                [
                    ("Total", str(a["total"])),
                    ("Pending", str(a["pending"])),
                    ("Sent", str(a["sent"])),
                    ("Read", str(a["read"])),
                    ("Resolved", str(a["resolved"])),
                    (
                        "Average time to resolve",
                        UNAVAILABLE
                        if a["average_resolution_hours"] is None
                        else f"{a['average_resolution_hours']} hours",
                    ),
                ]
            ),
        ]

    def _recommendations(self, data: ReportData) -> list:
        if not data.has("recommendations"):
            return []

        head = [
            Paragraph(
                "Advisory recommendations", self.styles["heading"]
            ),
            Paragraph(
                "Advice, not findings. No rule here concludes "
                "that deforestation occurred or that clearing "
                "was unlawful.",
                self.styles["note"],
            ),
            Spacer(1, 4),
        ]

        if not data.recommendations:
            return head + [
                Paragraph(
                    "No rule was triggered by the records in "
                    "scope.",
                    self.styles["body"],
                )
            ]

        return head + [
            self._table(
                ["Priority", "Rule", "Location", "Suggested action"],
                [
                    [
                        r["priority"],
                        r["rule"].replace("_", " ").title(),
                        " · ".join(
                            x
                            for x in (r["forest_area"], r["district"])
                            if x
                        )
                        or "—",
                        r["action"],
                    ]
                    for r in data.recommendations
                ],
                widths=[18, 34, 42, 80],
            )
        ]

    def _history(self, data: ReportData) -> list:
        if not data.has("history") or not data.history:
            return []

        return [
            Paragraph("Analysis history", self.styles["heading"]),
            self._table(
                [
                    "Job",
                    "Forest area",
                    "Status",
                    "Baseline end",
                    "Comparison end",
                    "Cloud %",
                ],
                [
                    [
                        str(h["id"]),
                        h["forest_area"],
                        plain(h["status"]),
                        plain(h["baseline_end"], "—"),
                        plain(h["comparison_end"], "—"),
                        number(h["cloud_cover_percentage"], 1),
                    ]
                    for h in data.history
                ],
                widths=[14, 40, 26, 30, 30, 20],
            ),
        ]

    def _methodology(self, data: ReportData) -> list:
        flow = [
            Paragraph(
                "Methodology and limitations",
                self.styles["heading"],
            ),
            Paragraph(METHODOLOGY, self.styles["body"]),
            Spacer(1, 4),
            Paragraph(SEASONAL, self.styles["body"]),
            Spacer(1, 4),
            Paragraph(f"<b>{CAUTION}</b>", self.styles["body"]),
        ]

        if data.limitations:
            flow.append(Spacer(1, 6))
            flow.append(
                Paragraph(
                    "Limitations affecting this report",
                    self.styles["heading"],
                )
            )

            for item in data.limitations:
                flow.append(
                    Paragraph(f"• {item}", self.styles["body"])
                )
                flow.append(Spacer(1, 2))

        flow.append(Spacer(1, 8))
        flow.append(self.base.provenance(None))

        return flow

    # -----------------------------------------------------
    # TABLE
    # -----------------------------------------------------

    def _table(
        self,
        headings: list[str],
        rows: list[list[str]],
        widths: list[float] | None = None,
    ) -> Table:
        """
        Build a readable data table.

        Cells are Paragraphs so long values wrap rather than
        running past the margin, which is what clips a table
        in a printed report.
        """

        body = [
            [
                Paragraph(f"<b>{heading}</b>", self.styles["cell"])
                for heading in headings
            ]
        ] + [
            [
                Paragraph(str(cell), self.styles["cell"])
                for cell in row
            ]
            for row in rows
        ]

        if widths is None:
            widths = [174.0 / len(headings)] * len(headings)

        table = Table(
            body,
            colWidths=[w * mm for w in widths],
            repeatRows=1,
        )

        table.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.HexColor("#E8F3EC"),
                    ),
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.4,
                        colors.HexColor("#CFDCD4"),
                    ),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )

        return table


# =========================================================
# CSV
# =========================================================

def render_csv(data: ReportData) -> bytes:
    """
    Export the collected analytics as CSV.

    One file has to carry several differently shaped tables,
    so each is introduced by its own heading row and
    separated by a blank line. A spreadsheet opens this
    readably and a human can follow it.

    Encoded UTF-8 with a BOM, because Excel on Windows
    otherwise reads a plain UTF-8 CSV as the system codepage
    and mangles any non-ASCII text in a forest area's name.
    """

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")

    writer.writerow(["ForestWatch Zambia - Analytics Report"])
    writer.writerow(["Reference", data.reference])
    writer.writerow(
        ["Generated", data.generated_at.isoformat(timespec="seconds")]
    )
    writer.writerow(["Scope", data.scope_description])
    writer.writerow([])

    if data.summary is not None:
        writer.writerow(["SUMMARY"])
        writer.writerow(["Measure", "Value", "Unit"])

        s = data.summary
        rows = [
            ("Monitored forest areas", s["monitored_forest_areas"], "count"),
            ("Monitored area", s["monitored_hectares"], "hectares"),
            ("Detections", s["total_detections"], "count"),
            (
                "Potential loss, cumulative",
                s["cumulative_loss_hectares"],
                "hectares",
            ),
            (
                "Potential loss, unique ground",
                s["unique_loss_hectares"],
                "hectares",
            ),
            (
                "Detections with mapped outline",
                s["detections_with_outline"],
                "count",
            ),
            ("Forest areas analysed", s["forest_areas_analysed"], "count"),
            (
                "Latest analysis",
                s["latest_analysis_at"],
                "timestamp",
            ),
        ]

        for label, value, unit in rows:
            writer.writerow(
                [label, UNAVAILABLE if value is None else value, unit]
            )

        writer.writerow([])

    if data.has("forest_loss") and data.trend:
        writer.writerow(["FOREST LOSS TREND"])
        writer.writerow(
            [
                "Observation date",
                "Analyses completed",
                "Detections",
                "Potential loss (hectares)",
            ]
        )
        for row in data.trend:
            writer.writerow(
                [
                    row["date"],
                    row["analyses"],
                    row["detections"],
                    row["loss_hectares"],
                ]
            )
        writer.writerow([])

    if data.has("districts") and data.districts:
        writer.writerow(["DISTRICT COMPARISON"])
        writer.writerow(
            [
                "District",
                "Detections",
                "Potential loss (hectares)",
                "Analyses completed",
                "Observed",
            ]
        )
        for row in data.districts:
            writer.writerow(
                [
                    row["district"],
                    row["detections"],
                    row["loss_hectares"],
                    row["analyses"],
                    "yes" if row["observed"] else "not examined",
                ]
            )
        writer.writerow([])

    if data.has("ndvi") and data.ndvi is not None:
        writer.writerow(["NDVI CHANGE (whole area)"])
        writer.writerow(["Measure", "Value", "Unit"])

        n = data.ndvi
        for label, value, unit in [
            ("Analysis job", data.ndvi_job["id"], "id"),
            ("Baseline start", n["baseline_start"], "date"),
            ("Baseline end", n["baseline_end"], "date"),
            ("Comparison start", n["comparison_start"], "date"),
            ("Comparison end", n["comparison_end"], "date"),
            ("Mean NDVI before", n["mean_ndvi_before"], "index"),
            ("Mean NDVI after", n["mean_ndvi_after"], "index"),
            (
                "NDVI difference (later minus earlier)",
                n["mean_ndvi_difference"],
                "index",
            ),
            (
                "Valid pixels that declined",
                n["declined_pixel_percentage"],
                "percent",
            ),
            (
                "Area past threshold",
                n["declined_hectares"],
                "hectares",
            ),
            ("NDVI threshold", n["ndvi_threshold"], "index"),
            ("Measurable pixels", n["measurable_pixels"], "count"),
        ]:
            writer.writerow(
                [label, UNAVAILABLE if value is None else value, unit]
            )

        writer.writerow([])

    if data.has("detections") and data.detections:
        writer.writerow(["DETECTIONS"])
        writer.writerow(
            [
                "Detection id",
                "Forest area",
                "District",
                "Affected area (hectares)",
                "NDVI before",
                "NDVI after",
                "NDVI decline",
                "Status",
                "Detected on",
                "Analysis job",
                "Has mapped outline",
            ]
        )
        for d in data.detections:
            writer.writerow(
                [
                    d["id"],
                    d["forest_area"],
                    d["district"],
                    _csv_value(d["area_hectares"]),
                    _csv_value(d["ndvi_before"]),
                    _csv_value(d["ndvi_after"]),
                    _csv_value(d["ndvi_decline"]),
                    _csv_value(d["status"]),
                    _csv_value(d["detected_on"]),
                    _csv_value(d["analysis_job_id"]),
                    "yes" if d["has_outline"] else "no",
                ]
            )
        writer.writerow([])

    if data.has("alerts") and data.alerts is not None:
        writer.writerow(["ALERTS"])
        writer.writerow(["Measure", "Value", "Unit"])
        a = data.alerts
        for label, value, unit in [
            ("Total", a["total"], "count"),
            ("Pending", a["pending"], "count"),
            ("Sent", a["sent"], "count"),
            ("Read", a["read"], "count"),
            ("Resolved", a["resolved"], "count"),
            (
                "Average time to resolve",
                a["average_resolution_hours"],
                "hours",
            ),
        ]:
            writer.writerow(
                [label, UNAVAILABLE if value is None else value, unit]
            )
        writer.writerow([])

    if data.has("recommendations") and data.recommendations:
        writer.writerow(["RECOMMENDATIONS (advice, not findings)"])
        writer.writerow(
            [
                "Priority",
                "Rule",
                "Forest area",
                "District",
                "Finding",
                "Suggested action",
            ]
        )
        for r in data.recommendations:
            writer.writerow(
                [
                    r["priority"],
                    r["rule"],
                    _csv_value(r["forest_area"]),
                    _csv_value(r["district"]),
                    r["finding"],
                    r["action"],
                ]
            )
        writer.writerow([])

    if data.has("history") and data.history:
        writer.writerow(["ANALYSIS HISTORY"])
        writer.writerow(
            [
                "Job id",
                "Forest area",
                "Status",
                "Baseline start",
                "Baseline end",
                "Comparison start",
                "Comparison end",
                "Completed at",
                "Cloud cover (percent)",
                "Error",
            ]
        )
        for h in data.history:
            writer.writerow(
                [
                    h["id"],
                    h["forest_area"],
                    _csv_value(h["status"]),
                    _csv_value(h["baseline_start"]),
                    _csv_value(h["baseline_end"]),
                    _csv_value(h["comparison_start"]),
                    _csv_value(h["comparison_end"]),
                    _csv_value(h["completed_at"]),
                    _csv_value(h["cloud_cover_percentage"]),
                    _csv_value(h["error_message"], ""),
                ]
            )
        writer.writerow([])

    writer.writerow(["LIMITATIONS AND METHODOLOGY"])
    writer.writerow([METHODOLOGY])
    writer.writerow([SEASONAL])
    writer.writerow([CAUTION])

    for item in data.limitations:
        writer.writerow([item])

    # BOM so Excel on Windows reads the encoding correctly.
    return buffer.getvalue().encode("utf-8-sig")


def _csv_value(value, fallback: str = UNAVAILABLE):
    """
    Return a value for a cell, never silently zero.

    A missing measurement is written as text so that nobody
    opening the spreadsheet later mistakes it for a measured
    zero.
    """

    if value is None:
        return fallback

    return value


# =========================================================
# EXCEL
# =========================================================

HEADER_FILL = PatternFill("solid", fgColor="E8F3EC")
HEADER_FONT = Font(bold=True, color="14311F")
TITLE_FONT = Font(bold=True, size=13, color="14311F")


def render_xlsx(data: ReportData) -> bytes:
    """
    Export the collected analytics as a workbook.

    Each section becomes its own worksheet, so a reader can
    sort and filter one table without the others interfering,
    which is the advantage a workbook has over the CSV.

    Missing measurements are written as the words "Not
    available" rather than as empty cells or zeros. An empty
    cell in a spreadsheet is ambiguous and a zero is a claim.
    """

    workbook = Workbook()

    cover = workbook.active
    cover.title = "Summary"

    _write_cover(cover, data)

    if data.has("forest_loss") and data.trend:
        _write_sheet(
            workbook.create_sheet("Forest Loss"),
            ["Observation date", "Analyses", "Detections", "Hectares"],
            [
                [
                    row["date"],
                    row["analyses"],
                    row["detections"],
                    row["loss_hectares"],
                ]
                for row in data.trend
            ],
        )

    if data.has("districts") and data.districts:
        _write_sheet(
            workbook.create_sheet("Districts"),
            [
                "District",
                "Detections",
                "Hectares",
                "Analyses",
                "Observed",
            ],
            [
                [
                    row["district"],
                    row["detections"],
                    row["loss_hectares"],
                    row["analyses"],
                    "yes" if row["observed"] else "not examined",
                ]
                for row in data.districts
            ],
        )

    if data.has("ndvi") and data.ndvi is not None:
        n = data.ndvi
        _write_sheet(
            workbook.create_sheet("NDVI Analysis"),
            ["Measure", "Value", "Unit"],
            [
                ["Analysis job", data.ndvi_job["id"], "id"],
                ["Baseline start", _xl(n["baseline_start"]), "date"],
                ["Baseline end", _xl(n["baseline_end"]), "date"],
                [
                    "Comparison start",
                    _xl(n["comparison_start"]),
                    "date",
                ],
                ["Comparison end", _xl(n["comparison_end"]), "date"],
                [
                    "Mean NDVI before",
                    _xl(n["mean_ndvi_before"]),
                    "index",
                ],
                [
                    "Mean NDVI after",
                    _xl(n["mean_ndvi_after"]),
                    "index",
                ],
                [
                    "NDVI difference (later minus earlier)",
                    _xl(n["mean_ndvi_difference"]),
                    "index",
                ],
                [
                    "Valid pixels that declined",
                    _xl(n["declined_pixel_percentage"]),
                    "percent",
                ],
                [
                    "Area past threshold",
                    _xl(n["declined_hectares"]),
                    "hectares",
                ],
                ["NDVI threshold", _xl(n["ndvi_threshold"]), "index"],
                [
                    "Measurable pixels",
                    _xl(n["measurable_pixels"]),
                    "count",
                ],
                [
                    "Basis",
                    "Whole area, every pixel measurable on both "
                    "dates. Not the mean over detected patches.",
                    "",
                ],
            ],
        )

    if data.has("detections") and data.detections:
        _write_sheet(
            workbook.create_sheet("Detections"),
            [
                "Detection id",
                "Forest area",
                "District",
                "Hectares",
                "NDVI before",
                "NDVI after",
                "NDVI decline",
                "Status",
                "Detected on",
                "Analysis job",
                "Mapped outline",
            ],
            [
                [
                    d["id"],
                    d["forest_area"],
                    d["district"],
                    _xl(d["area_hectares"]),
                    _xl(d["ndvi_before"]),
                    _xl(d["ndvi_after"]),
                    _xl(d["ndvi_decline"]),
                    _xl(d["status"]),
                    _xl(_naive(d["detected_on"])),
                    _xl(d["analysis_job_id"]),
                    "yes" if d["has_outline"] else "no",
                ]
                for d in data.detections
            ],
        )

    if data.has("alerts") and data.alerts is not None:
        a = data.alerts
        _write_sheet(
            workbook.create_sheet("Alerts"),
            ["Measure", "Value", "Unit"],
            [
                ["Total", a["total"], "count"],
                ["Pending", a["pending"], "count"],
                ["Sent", a["sent"], "count"],
                ["Read", a["read"], "count"],
                ["Resolved", a["resolved"], "count"],
                [
                    "Average time to resolve",
                    _xl(a["average_resolution_hours"]),
                    "hours",
                ],
            ],
        )

    if data.has("recommendations"):
        _write_sheet(
            workbook.create_sheet("Recommendations"),
            [
                "Priority",
                "Rule",
                "Forest area",
                "District",
                "Finding",
                "Suggested action",
            ],
            [
                [
                    r["priority"],
                    r["rule"],
                    _xl(r["forest_area"]),
                    _xl(r["district"]),
                    r["finding"],
                    r["action"],
                ]
                for r in data.recommendations
            ]
            or [["", "", "", "", "No rule was triggered.", ""]],
        )

    if data.has("history") and data.history:
        _write_sheet(
            workbook.create_sheet("Analysis History"),
            [
                "Job id",
                "Forest area",
                "Status",
                "Baseline end",
                "Comparison end",
                "Completed at",
                "Cloud cover (%)",
                "Error",
            ],
            [
                [
                    h["id"],
                    h["forest_area"],
                    _xl(h["status"]),
                    _xl(h["baseline_end"]),
                    _xl(h["comparison_end"]),
                    _xl(_naive(h["completed_at"])),
                    _xl(h["cloud_cover_percentage"]),
                    _xl(h["error_message"], ""),
                ]
                for h in data.history
            ],
        )

    _write_sheet(
        workbook.create_sheet("Methodology"),
        ["Note"],
        [[METHODOLOGY], [SEASONAL], [CAUTION]]
        + [[item] for item in data.limitations],
        widths=[120],
    )

    buffer = io.BytesIO()
    workbook.save(buffer)

    return buffer.getvalue()


def _naive(moment):
    """
    Drop the timezone from a timestamp.

    Excel has no concept of an offset-aware datetime, and
    openpyxl refuses to write one.
    """

    if moment is None:
        return None

    return moment.replace(tzinfo=None)


def _xl(value, fallback: str = UNAVAILABLE):
    """Return a cell value, saying so when it is missing."""

    if value is None:
        return fallback

    return value


def _write_cover(sheet, data: ReportData) -> None:
    """Write the cover sheet with the report's own details."""

    sheet["A1"] = "ForestWatch Zambia - Analytics Report"
    sheet["A1"].font = TITLE_FONT

    rows = [
        ("Reference", data.reference),
        (
            "Generated",
            data.generated_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        ),
        ("Scope", data.scope_description),
        (
            "Sections",
            ", ".join(
                s.replace("_", " ") for s in data.request.sections
            ),
        ),
    ]

    if data.summary is not None:
        s = data.summary
        rows += [
            ("", ""),
            ("Monitored forest areas", s["monitored_forest_areas"]),
            ("Monitored area (hectares)", s["monitored_hectares"]),
            ("Detections", s["total_detections"]),
            (
                "Potential loss, cumulative (hectares)",
                s["cumulative_loss_hectares"],
            ),
            (
                "Potential loss, unique ground (hectares)",
                _xl(s["unique_loss_hectares"]),
            ),
            (
                "Detections with mapped outline",
                s["detections_with_outline"],
            ),
            ("Forest areas analysed", s["forest_areas_analysed"]),
            (
                "Latest analysis",
                _xl(_naive(s["latest_analysis_at"])),
            ),
        ]

    for index, (label, value) in enumerate(rows, start=3):
        sheet.cell(row=index, column=1, value=label).font = Font(
            bold=True
        )
        sheet.cell(row=index, column=2, value=value)

    sheet.column_dimensions["A"].width = 42
    sheet.column_dimensions["B"].width = 64
    sheet.column_dimensions["B"].alignment = Alignment(wrap_text=True)


def _write_sheet(
    sheet,
    headings: list[str],
    rows: list[list],
    widths: list[int] | None = None,
) -> None:
    """Write one table with a frozen, styled heading row."""

    sheet.append(headings)

    for cell in sheet[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="top", wrap_text=True)

    for row in rows:
        sheet.append(row)

    # Frozen headings keep the column names visible while an
    # officer scrolls a long detection table.
    sheet.freeze_panes = "A2"

    if widths is None:
        widths = []
        for index, heading in enumerate(headings):
            longest = max(
                [len(str(heading))]
                + [
                    len(str(row[index]))
                    for row in rows
                    if index < len(row)
                ]
                or [10]
            )
            widths.append(min(max(longest + 2, 12), 60))

    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[
            get_column_letter(index)
        ].width = width

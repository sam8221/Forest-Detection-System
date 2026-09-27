"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Report Service

Purpose:
    Produces the PDF reports an officer downloads: a single
    detection report for a field visit, and a jurisdiction
    summary covering a period.

Responsibilities:
    - Render a detection as a printable evidence sheet.
    - Render a period summary for a district or province.
    - Stamp every report with who generated it and when.

How it works:

    Built with ReportLab's platypus layer, which composes a
    document from flowable elements rather than drawing at
    coordinates. A table that outgrows a page splits across
    pages on its own, which matters here because a summary
    over a busy quarter can run to several pages.

    ReportLab is pure Python. WeasyPrint would give richer
    layout but needs GTK and Pango installed on the host,
    which is a poor trade for a system that has to be
    deployable by the department itself.

    Nothing in this module queries the database. It is given
    ORM objects that a caller has already fetched through
    the jurisdiction-scoped repository methods, which keeps
    the rendering testable without a database and keeps the
    access decision in the one layer that owns it.

Why reports are generated on the server:

    A report is evidence. An officer may take a detection
    report to a site, attach it to an enforcement file, or
    hand it to a supervisor, so the figures on it must come
    from the database of record rather than from whatever a
    browser happened to be showing.

    It also keeps jurisdiction enforcement in one place. The
    caller fetches through the scoped repository methods, so
    a district officer cannot obtain a report containing
    another district's detections even by editing a request.

Note on what a report asserts:

    A detection report describes a measurement, not a
    finding. The wording in these documents is deliberately
    careful about that distinction: the system reports where
    vegetation cover fell, and the officer determines what
    happened on the ground.

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

from datetime import date, datetime, timezone
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import (
    ParagraphStyle,
    getSampleStyleSheet,
)
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# =========================================================
# HOUSE STYLE
#
# The green is the one the interface uses, so a printed
# report and the screen it came from read as the same
# system. The greys are chosen against it rather than being
# neutral, for the same reason.
# =========================================================

FOREST = colors.HexColor("#198754")
FOREST_DARK = colors.HexColor("#0b3d23")
INK = colors.HexColor("#17301f")
MUTED = colors.HexColor("#64748b")
RULE = colors.HexColor("#d8e1d4")
WASH = colors.HexColor("#e8f5ec")

# Status colours match the pills in the interface, so a
# status means the same thing on paper as on screen.
STATUS_COLOURS = {
    "VERIFIED": colors.HexColor("#15803d"),
    "PENDING": colors.HexColor("#b45309"),
    "REJECTED": colors.HexColor("#b91c1c"),
}


class ReportService:
    """
    Renders ForestWatch PDF reports.

    Holds no state between calls and touches neither the
    database nor the network, so it can be constructed per
    request and exercised in a test with plain objects.
    """

    # -----------------------------------------------------
    # SETUP
    # -----------------------------------------------------

    def __init__(self) -> None:
        """
        Build the paragraph styles used by both reports.
        """

        base = getSampleStyleSheet()

        self.styles = {
            "title": ParagraphStyle(
                "fw-title",
                parent=base["Title"],
                fontName="Helvetica-Bold",
                fontSize=17,
                leading=21,
                textColor=FOREST_DARK,
                alignment=TA_CENTER,
                spaceAfter=2,
            ),
            "subtitle": ParagraphStyle(
                "fw-subtitle",
                parent=base["Normal"],
                fontSize=9,
                leading=12,
                textColor=MUTED,
                alignment=TA_CENTER,
            ),
            "heading": ParagraphStyle(
                "fw-heading",
                parent=base["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=11,
                leading=14,
                textColor=FOREST_DARK,
                spaceBefore=12,
                spaceAfter=5,
            ),
            "body": ParagraphStyle(
                "fw-body",
                parent=base["Normal"],
                fontSize=9.5,
                leading=13.5,
                textColor=INK,
            ),
            "note": ParagraphStyle(
                "fw-note",
                parent=base["Normal"],
                fontSize=8.5,
                leading=12,
                textColor=MUTED,
            ),
            "cell": ParagraphStyle(
                "fw-cell",
                parent=base["Normal"],
                fontSize=8.5,
                leading=11,
                textColor=INK,
            ),
        }

    # -----------------------------------------------------
    # FORMATTING HELPERS
    # -----------------------------------------------------

    @staticmethod
    def text(value: object, fallback: str = "Not recorded") -> str:
        """
        Render a value for display, or say it is absent.

        A blank cell in a report is ambiguous: it could mean
        zero, or that nothing was recorded. Saying which
        avoids an officer reading a gap as a measurement.

        Enum members are unwrapped to their value. The model
        fields for status, role and protected status are
        Python enums, and str() on one of those yields
        "DETECTIONSTATUS.PENDING" rather than "PENDING",
        which is how the class is named internally and not
        something to print in front of an officer.

        Args:
            value: Any value, possibly None or an Enum.
            fallback: Wording used when the value is absent.

        Returns:
            str: The value as text, or the fallback.
        """

        if value is None or value == "":
            return fallback

        # Enum members carry the stored string on .value.
        inner = getattr(value, "value", value)

        if inner is None or inner == "":
            return fallback

        return str(inner)

    @staticmethod
    def number(
        value: object,
        places: int = 2,
        suffix: str = "",
        fallback: str = "Not recorded",
    ) -> str:
        """
        Render a numeric value to a fixed number of places.

        Args:
            value: The figure, possibly None.
            places: Decimal places.
            suffix: Unit appended after a space.
            fallback: Wording used when the value is absent.

        Returns:
            str: Formatted figure, or the fallback.

        Raises:
            Nothing. A value that cannot be read as a number
            is reported with the fallback rather than
            interrupting the report.
        """

        if value is None:
            return fallback

        try:
            rendered = f"{float(value):.{places}f}"
        except (TypeError, ValueError):
            return fallback

        return f"{rendered} {suffix}".strip()

    @staticmethod
    def moment(value: object, fallback: str = "Not recorded") -> str:
        """
        Render a date or timestamp in Zambian convention.

        Args:
            value: A date, datetime, or None.
            fallback: Wording used when absent.

        Returns:
            str: "14 September 2026", with the time appended
                 for a timestamp.
        """

        if value is None:
            return fallback

        if isinstance(value, datetime):
            return value.strftime("%d %B %Y at %H:%M")

        if isinstance(value, date):
            return value.strftime("%d %B %Y")

        return str(value)

    # -----------------------------------------------------
    # PAGE FURNITURE
    # -----------------------------------------------------

    def page_footer(self, canvas, document) -> None:
        """
        Draw the footer rule, page number and provenance.

        Called by ReportLab once per page. The page number
        cannot be composed as a flowable because the total
        is not known until the document is laid out.

        Args:
            canvas: The ReportLab canvas for this page.
            document: The document being rendered.
        """

        canvas.saveState()

        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(
            18 * mm,
            15 * mm,
            A4[0] - 18 * mm,
            15 * mm,
        )

        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)

        canvas.drawString(
            18 * mm,
            10 * mm,
            "ForestWatch Zambia — Forestry Department. "
            "Restricted: not for public release.",
        )

        canvas.drawRightString(
            A4[0] - 18 * mm,
            10 * mm,
            f"Page {document.page}",
        )

        canvas.restoreState()

    def masthead(self, heading: str, subheading: str) -> list:
        """
        Build the block that opens every report.

        Args:
            heading: Report title.
            subheading: One line of context beneath it.

        Returns:
            list: Flowables for the document.
        """

        rule = Table(
            [[""]],
            colWidths=[A4[0] - 36 * mm],
            rowHeights=[2],
        )

        rule.setStyle(
            TableStyle(
                [("BACKGROUND", (0, 0), (-1, -1), FOREST)]
            )
        )

        return [
            Paragraph("ForestWatch Zambia", self.styles["subtitle"]),
            Paragraph(heading, self.styles["title"]),
            Paragraph(subheading, self.styles["subtitle"]),
            Spacer(1, 5),
            rule,
            Spacer(1, 10),
        ]

    def field_table(self, rows: list[tuple[str, str]]) -> Table:
        """
        Render label and value pairs as a two-column table.

        Args:
            rows: (label, value) pairs, in display order.

        Returns:
            Table: A styled flowable.
        """

        data = [
            [
                Paragraph(f"<b>{label}</b>", self.styles["cell"]),
                Paragraph(value, self.styles["cell"]),
            ]
            for label, value in rows
        ]

        table = Table(
            data,
            colWidths=[52 * mm, A4[0] - 88 * mm],
        )

        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("BACKGROUND", (0, 0), (0, -1), WASH),
                    ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
                    ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                ]
            )
        )

        return table

    def build(
        self,
        flowables: list,
        title: str,
    ) -> bytes:
        """
        Render flowables into PDF bytes.

        Args:
            flowables: The document body.
            title: Embedded PDF title metadata.

        Returns:
            bytes: The finished PDF.
        """

        buffer = BytesIO()

        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=16 * mm,
            # Room for the footer drawn by page_footer.
            bottomMargin=22 * mm,
            title=title,
            author="ForestWatch Zambia",
            subject=(
                "Deforestation monitoring, Copperbelt "
                "Province, Zambia"
            ),
        )

        document.build(
            flowables,
            onFirstPage=self.page_footer,
            onLaterPages=self.page_footer,
        )

        return buffer.getvalue()

    # -----------------------------------------------------
    # DETECTION REPORT
    # -----------------------------------------------------

    def detection_report(
        self,
        detection,
        generated_by,
    ) -> bytes:
        """
        Render one detection as a field evidence sheet.

        Everything an officer needs to find the site and
        judge what they are looking at: where it is, how
        large it is, how far vegetation fell, and which two
        acquisitions were compared.

        Args:
            detection:
                A Detection, already confirmed visible to
                this officer by the calling repository.
            generated_by:
                The User requesting the report. Named on the
                document, because a report that circulates
                without provenance is worth little as
                evidence.

        Returns:
            bytes: The finished PDF.

        Raises:
            Nothing of its own. A missing optional field is
            reported as "Not recorded" rather than omitted.
        """

        forest = getattr(detection, "forest_area", None)
        district = getattr(forest, "district", None) if forest else None
        province = getattr(district, "province", None) if district else None

        status = self.text(
            getattr(detection, "status", None),
            "UNKNOWN",
        ).upper()

        flow: list = []

        flow += self.masthead(
            f"Detection Report — No. {detection.id}",
            "Suspected loss of vegetation cover identified "
            "from Sentinel-2 imagery",
        )

        # ---------- Status ----------

        status_colour = STATUS_COLOURS.get(status, MUTED)

        # hexval() yields "0xRRGGBB"; ReportLab's inline
        # markup wants "#RRGGBB".
        status_hex = f"#{status_colour.hexval()[2:]}"

        status_table = Table(
            [[Paragraph(
                f'<font color="{status_hex}">'
                f"<b>Status: {status}</b></font>",
                self.styles["body"],
            )]],
            colWidths=[A4[0] - 36 * mm],
        )

        status_table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                    ("BACKGROUND", (0, 0), (-1, -1), WASH),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )

        flow.append(status_table)

        # ---------- Location ----------

        flow.append(Paragraph("Location", self.styles["heading"]))

        flow.append(
            self.field_table(
                [
                    ("Forest area", self.text(
                        getattr(forest, "name", None))),
                    ("Forest code", self.text(
                        getattr(forest, "forest_code", None))),
                    ("District", self.text(
                        getattr(district, "name", None))),
                    ("Province", self.text(
                        getattr(province, "name", None))),
                    ("Protected status", self.text(
                        getattr(forest, "protected_status", None))),
                ]
            )
        )

        # ---------- Measurements ----------

        flow.append(
            Paragraph("Measurements", self.styles["heading"])
        )

        ndvi_before = getattr(detection, "ndvi_before", None)
        ndvi_after = getattr(detection, "ndvi_after", None)

        # Shown alongside the two readings rather than left
        # for the reader to subtract, because the fall is the
        # figure the detection actually turns on.
        if ndvi_before is not None and ndvi_after is not None:
            try:
                change = f"{float(ndvi_after) - float(ndvi_before):.4f}"
            except (TypeError, ValueError):
                change = "Not recorded"
        else:
            change = "Not recorded"

        flow.append(
            self.field_table(
                [
                    ("Affected area", self.number(
                        getattr(detection, "detected_area_hectares", None),
                        2, "hectares")),
                    ("NDVI before", self.number(ndvi_before, 4)),
                    ("NDVI after", self.number(ndvi_after, 4)),
                    ("Change in NDVI", change),
                    ("Vegetation loss", self.number(
                        getattr(detection, "vegetation_loss_percentage", None),
                        2, "%")),
                    ("Confidence", self.number(
                        getattr(detection, "confidence_score", None),
                        2, "%")),
                ]
            )
        )

        flow.append(Spacer(1, 6))

        flow.append(
            Paragraph(
                "NDVI is the Normalised Difference Vegetation "
                "Index, derived from the red and near-infrared "
                "bands of Sentinel-2. Values fall as vegetation "
                "cover is lost. The minimum reportable area is "
                "0.5 hectares, taken from the area criterion in "
                "the Forests Act No. 4 of 2015.",
                self.styles["note"],
            )
        )

        # ---------- Imagery ----------

        flow.append(Paragraph("Imagery", self.styles["heading"]))

        job = getattr(detection, "analysis_job", None)

        flow.append(
            self.field_table(
                [
                    ("Baseline period", (
                        f"{self.moment(getattr(job, 'baseline_start', None))}"
                        f" to "
                        f"{self.moment(getattr(job, 'baseline_end', None))}"
                    ) if job else "Not recorded"),
                    ("Comparison period", (
                        f"{self.moment(getattr(job, 'comparison_start', None))}"
                        f" to "
                        f"{self.moment(getattr(job, 'comparison_end', None))}"
                    ) if job else "Not recorded"),
                    ("Analysis job", self.text(
                        getattr(detection, "analysis_job_id", None))),
                    ("Satellite image", self.text(
                        getattr(detection, "satellite_image_id", None))),
                ]
            )
        )

        flow.append(Spacer(1, 6))

        flow.append(
            Paragraph(
                "The two periods are equivalent calendar "
                "windows in different years. Miombo woodland "
                "loses leaf across the province every dry "
                "season, so comparing adjacent months would "
                "report loss almost everywhere; comparing the "
                "same season a year apart removes that cycle.",
                self.styles["note"],
            )
        )

        # ---------- Review ----------

        flow.append(Paragraph("Review", self.styles["heading"]))

        verifier = getattr(detection, "verified_by_user", None)

        flow.append(
            self.field_table(
                [
                    ("Reviewed by", self.text(
                        getattr(verifier, "full_name", None),
                        "Not yet reviewed")),
                    ("Reviewed on", self.moment(
                        getattr(detection, "verified_at", None),
                        "Not yet reviewed")),
                    ("Notes", self.text(
                        getattr(detection, "verification_notes", None),
                        "None recorded")),
                ]
            )
        )

        # ---------- Caveat ----------

        flow.append(Spacer(1, 12))

        caveat = Table(
            [[Paragraph(
                "<b>This is a measurement, not a finding.</b> "
                "The system reports where vegetation cover "
                "fell between two dates. It does not establish "
                "that clearing was unlawful, nor does it "
                "measure canopy cover or tree height against "
                "the statutory definition of a forest. "
                "Confirmation is a matter for inspection on "
                "the ground.",
                self.styles["note"],
            )]],
            colWidths=[A4[0] - 36 * mm],
        )

        caveat.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                    ("BACKGROUND", (0, 0), (-1, -1),
                     colors.HexColor("#fffbeb")),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )

        flow.append(caveat)

        flow.append(Spacer(1, 10))

        flow.append(self.provenance(generated_by))

        return self.build(
            flow,
            f"ForestWatch detection report {detection.id}",
        )

    # -----------------------------------------------------
    # SUMMARY REPORT
    # -----------------------------------------------------

    def summary_report(
        self,
        detections: list,
        generated_by,
        start: date | None = None,
        end: date | None = None,
    ) -> bytes:
        """
        Render a period summary over a set of detections.

        Args:
            detections:
                Detections already scoped to the officer's
                jurisdiction by the calling repository.
            generated_by:
                The User requesting the report.
            start:
                Start of the reporting period, or None for
                all records held.
            end:
                End of the reporting period.

        Returns:
            bytes: The finished PDF.

        Raises:
            Nothing. A period with no detections produces a
            valid report saying so, which is a meaningful
            result rather than an error.
        """

        flow: list = []

        if start or end:
            period = (
                f"{self.moment(start, 'Earliest record')} to "
                f"{self.moment(end, 'Latest record')}"
            )
        else:
            period = "All records held"

        flow += self.masthead(
            "Deforestation Summary Report",
            period,
        )

        # ---------- Scope ----------

        flow.append(
            self.field_table(
                [
                    ("Prepared for", self.text(
                        getattr(generated_by, "full_name", None))),
                    ("Jurisdiction",
                     self.describe_jurisdiction(generated_by)),
                    ("Reporting period", period),
                    ("Detections in report", str(len(detections))),
                ]
            )
        )

        # ---------- Totals ----------

        flow.append(Paragraph("Totals", self.styles["heading"]))

        counts = {"VERIFIED": 0, "PENDING": 0, "REJECTED": 0}
        total_area = 0.0

        for item in detections:
            key = self.text(
                getattr(item, "status", None), ""
            ).upper()

            if key in counts:
                counts[key] += 1

            try:
                total_area += float(
                    getattr(item, "detected_area_hectares", 0) or 0
                )
            except (TypeError, ValueError):
                # A malformed area must not stop the report;
                # the row still appears in the table below.
                pass

        flow.append(
            self.field_table(
                [
                    ("Total detections", str(len(detections))),
                    ("Confirmed", str(counts["VERIFIED"])),
                    ("Awaiting review", str(counts["PENDING"])),
                    ("Rejected", str(counts["REJECTED"])),
                    ("Total affected area",
                     f"{total_area:.2f} hectares"),
                ]
            )
        )

        flow.append(Spacer(1, 4))

        flow.append(
            Paragraph(
                "Affected area is the sum of every detection "
                "listed, including those awaiting review and "
                "those since rejected. It is a measure of what "
                "the system flagged, not of confirmed forest "
                "loss.",
                self.styles["note"],
            )
        )

        # ---------- Detections ----------

        flow.append(
            Paragraph("Detections", self.styles["heading"])
        )

        if not detections:
            flow.append(
                Paragraph(
                    "No detections were recorded in this "
                    "period. A period with no detections is a "
                    "valid result: it means no loss of "
                    "vegetation above the half-hectare "
                    "threshold was found in the imagery "
                    "analysed, not that no analysis ran.",
                    self.styles["body"],
                )
            )
        else:
            flow.append(self.detection_table(detections))

        flow.append(Spacer(1, 12))

        flow.append(self.provenance(generated_by))

        return self.build(
            flow,
            "ForestWatch deforestation summary report",
        )

    def detection_table(self, detections: list) -> Table:
        """
        Render detections as a table, newest first.

        Args:
            detections: The detections to list.

        Returns:
            Table: A flowable that repeats its header row on
                   each page it spills onto.
        """

        header = [
            Paragraph(f"<b>{label}</b>", self.styles["cell"])
            for label in (
                "No.",
                "Forest area",
                "District",
                "Area (ha)",
                "NDVI fall",
                "Status",
                "Detected",
            )
        ]

        rows = [header]

        for item in detections:
            forest = getattr(item, "forest_area", None)
            district = (
                getattr(forest, "district", None) if forest else None
            )

            before = getattr(item, "ndvi_before", None)
            after = getattr(item, "ndvi_after", None)

            try:
                fall = f"{float(before) - float(after):.3f}"
            except (TypeError, ValueError):
                fall = "—"

            rows.append(
                [
                    Paragraph(str(item.id), self.styles["cell"]),
                    Paragraph(
                        self.text(getattr(forest, "name", None), "—"),
                        self.styles["cell"],
                    ),
                    Paragraph(
                        self.text(getattr(district, "name", None), "—"),
                        self.styles["cell"],
                    ),
                    Paragraph(
                        self.number(
                            getattr(item, "detected_area_hectares", None),
                            2, "", "—"),
                        self.styles["cell"],
                    ),
                    Paragraph(fall, self.styles["cell"]),
                    Paragraph(
                        self.text(
                            getattr(item, "status", None), "—"
                        ).upper(),
                        self.styles["cell"],
                    ),
                    Paragraph(
                        self.moment(
                            getattr(item, "created_at", None), "—"),
                        self.styles["cell"],
                    ),
                ]
            )

        table = Table(
            rows,
            colWidths=[
                12 * mm, 42 * mm, 26 * mm,
                20 * mm, 20 * mm, 22 * mm, 32 * mm,
            ],
            # The header is reprinted at the top of every
            # page the table spills onto, so a reader who
            # turns over still knows what the columns are.
            repeatRows=1,
        )

        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), WASH),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("GRID", (0, 0), (-1, -1), 0.4, RULE),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.8, FOREST),
                ]
            )
        )

        return table

    # -----------------------------------------------------
    # SHARED BLOCKS
    # -----------------------------------------------------

    @staticmethod
    def describe_jurisdiction(user) -> str:
        """
        Describe the area an account covers.

        Mirrors the wording the interface uses, so a report
        and the screen it was generated from describe the
        same account the same way.

        Args:
            user: The User the report was generated for.

        Returns:
            str: A readable jurisdiction.
        """

        role = ReportService.text(getattr(user, "role", None), "")

        if "ADMIN" in role:
            return "All provinces (national)"

        district = getattr(user, "district", None)

        if district is not None:
            return f"{district.name} District"

        province = getattr(user, "province", None)

        if province is not None:
            return f"{province.name} Province"

        return "No jurisdiction assigned"

    def provenance(self, generated_by) -> KeepTogether:
        """
        Build the block recording who produced the report.

        Kept together so the generation details are never
        split across a page break, which would leave a
        signature line orphaned from the name above it.

        Args:
            generated_by: The requesting User.

        Returns:
            KeepTogether: A flowable.
        """

        stamped = datetime.now(timezone.utc).astimezone()

        return KeepTogether(
            [
                Paragraph(
                    "Report details", self.styles["heading"]
                ),
                self.field_table(
                    [
                        ("Generated by", self.text(
                            getattr(generated_by, "full_name", None))),
                        ("Role", self.text(
                            getattr(generated_by, "role", None))),
                        ("Generated on", self.moment(stamped)),
                    ]
                ),
                Spacer(1, 8),
                Paragraph(
                    "This document contains the locations of "
                    "suspected forest loss and is restricted "
                    "to authorised officers of the Forestry "
                    "Department. It is not for public "
                    "release.",
                    self.styles["note"],
                ),
            ]
        )

"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Reports Router

Purpose:
    Serves the PDF reports an officer downloads.

Responsibilities:
    - Authenticate the caller.
    - Fetch records through the jurisdiction-scoped
      repository.
    - Delegate rendering to ReportService.
    - Return the PDF as a download.

How it works:

    Two endpoints. One renders a single detection as a field
    evidence sheet; the other renders a period summary over
    everything in the officer's jurisdiction.

    Both fetch through the repository's *_for_user methods,
    which apply the jurisdiction filter in SQL. A detection
    outside the officer's district is not retrieved at all,
    so it cannot reach the renderer and cannot appear in a
    report, whatever identifier was requested.

    The response carries Content-Disposition: attachment,
    which is what makes the browser save the file rather
    than try to display it. The filename includes the record
    identifier and the date, so an officer downloading
    several reports does not end up with a folder of files
    called download.pdf.

Note on layering:
    No business logic here. The rendering lives in
    app/services/report_service.py, where it can be
    exercised without a web server, and the access decision
    lives in the repository, which is the only layer that
    owns it.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

import logging
from datetime import date
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.database.session import get_db
from app.models.user import User
from app.repositories.detection_repository import (
    DetectionRepository,
)
from app.repositories.forest_area_repository import (
    ForestAreaRepository,
)
from app.services.analytics_report_renderers import (
    PdfRenderer,
    render_csv,
    render_xlsx,
)
from app.services.analytics_report_service import (
    SECTIONS,
    AnalyticsReportService,
    ReportRequest,
)
from app.services.analytics_service import AnalyticsService
from app.services.report_service import ReportService


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
)


def pdf_response(content: bytes, filename: str) -> Response:
    """
    Return PDF bytes as a browser download.

    Args:
        content: The rendered PDF.
        filename: Name the browser should save it under.

    Returns:
        Response: An attachment response.
    """

    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            ),
            # The report names suspected clearing locations,
            # so it must not be held in a shared cache.
            "Cache-Control": "no-store",
        },
    )


# =========================================================
# DETECTION REPORT
# =========================================================

@router.get("/detections/{detection_id}")
def download_detection_report(
    detection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    """
    Download one detection as a PDF evidence sheet.

    Args:
        detection_id: The detection to report on.

    Returns:
        Response: A PDF attachment.

    Raises:
        HTTPException:
            404 when the detection does not exist, or lies
            outside the officer's jurisdiction. The two are
            deliberately indistinguishable, so that probing
            identifiers reveals nothing about detections in
            other districts.
    """

    repository = DetectionRepository(db)

    detection = repository.get_by_id_for_user(
        detection_id,
        current_user,
    )

    if detection is None:
        raise HTTPException(
            status_code=404,
            detail="Detection not found.",
        )

    content = ReportService().detection_report(
        detection=detection,
        generated_by=current_user,
    )

    return pdf_response(
        content,
        f"forestwatch-detection-{detection_id}.pdf",
    )


# =========================================================
# SUMMARY REPORT
# =========================================================

@router.get("/summary")
def download_summary_report(
    start: date | None = Query(
        default=None,
        description=(
            "Start of the reporting period. Omit for all "
            "records held."
        ),
    ),
    end: date | None = Query(
        default=None,
        description="End of the reporting period.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    """
    Download a period summary for the officer's jurisdiction.

    Args:
        start: Start of the period, or None for everything.
        end: End of the period.

    Returns:
        Response: A PDF attachment.

    Raises:
        HTTPException:
            422 when the period is inverted. Caught here
            rather than silently returning nothing, because
            an empty report is a meaningful result and must
            not be confused with a mistyped date.

    Note:
        A period with no detections produces a valid report
        saying so. That is a real finding — no vegetation
        loss above the half-hectare threshold was found —
        and is deliberately not treated as an error.
    """

    if start and end and start > end:
        raise HTTPException(
            status_code=422,
            detail=(
                "The start of the reporting period is after "
                "its end."
            ),
        )

    repository = DetectionRepository(db)

    detections = repository.get_all_for_user(current_user)

    # Filtered here rather than in SQL because the
    # jurisdiction-scoped query is the one that must not be
    # bypassed, and narrowing its result is safe. A date
    # range pushed into the repository would mean a second
    # query path to keep jurisdiction-correct.
    if start or end:
        filtered = []

        for item in detections:
            created = getattr(item, "created_at", None)

            if created is None:
                continue

            moment = created.date() if hasattr(
                created, "date"
            ) else created

            if start and moment < start:
                continue

            if end and moment > end:
                continue

            filtered.append(item)

        detections = filtered

    content = ReportService().summary_report(
        detections=detections,
        generated_by=current_user,
        start=start,
        end=end,
    )

    stamp = date.today().isoformat()

    return pdf_response(
        content,
        f"forestwatch-summary-{stamp}.pdf",
    )


# =========================================================
# ANALYTICS REPORT
# =========================================================

class AnalyticsReportRequest(BaseModel):
    """What the officer wants in their analytics report."""

    format: Literal["pdf", "csv", "xlsx"] = Field(
        default="pdf",
        description="Output format.",
    )

    sections: list[str] = Field(
        default_factory=lambda: list(SECTIONS),
        description=(
            "Sections to include. Anything not named is not "
            "collected, so an unwanted section costs no "
            "queries."
        ),
    )

    start_date: date | None = None
    end_date: date | None = None
    district_id: int | None = None
    forest_area_id: int | None = None

    title: str = Field(
        default="Forest Analytics Report",
        max_length=120,
    )

    @field_validator("sections")
    @classmethod
    def known_sections(cls, value: list[str]) -> list[str]:
        """Reject sections the report cannot produce."""

        unknown = [one for one in value if one not in SECTIONS]

        if unknown:
            raise ValueError(
                "Unknown section(s): "
                + ", ".join(unknown)
                + ". Available: "
                + ", ".join(SECTIONS)
            )

        if not value:
            raise ValueError(
                "Select at least one section to include."
            )

        # Preserve the documented order rather than the order
        # the caller happened to list them in, so two reports
        # over the same data read the same way.
        return [one for one in SECTIONS if one in value]

    @model_validator(mode="after")
    def ordered_dates(self) -> "AnalyticsReportRequest":
        """
        Reject an inverted period.

        Left alone it would silently produce an empty report,
        which reads as an absence of clearing rather than as
        a mistake in the request.
        """

        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError(
                "start_date must not be later than end_date."
            )

        return self


MEDIA_TYPES = {
    "pdf": "application/pdf",
    "csv": "text/csv; charset=utf-8",
    "xlsx": (
        "application/vnd.openxmlformats-officedocument"
        ".spreadsheetml.sheet"
    ),
}


@router.post("/analytics")
def download_analytics_report(
    request: AnalyticsReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Generate and return an analytics report.

    The report is built and returned in one request. It is
    assembled from database queries and held in memory, which
    takes well under a second for the volumes this system
    carries, so there is no job to poll and no file on disk.

    That also removes a class of risk: with no stored report
    there is no identifier to guess, no path to traverse and
    no temporary file to leak or clean up.

    Every figure is collected through the analytics services,
    which scope their queries to the officer's jurisdiction.
    A report therefore cannot contain a district the
    requester may not see, whatever filters are asked for.

    Raises:
        HTTPException:
            404 when a named forest area or district is not
            visible to this officer; 500 is never returned
            with a partial document, because a failure during
            rendering raises before any bytes are sent.
    """

    service = AnalyticsReportService(db)

    # Named filters are checked against what this officer may
    # see, so an unauthorised identifier is refused rather
    # than silently producing an empty report that looks like
    # an absence of clearing.
    if request.forest_area_id is not None:
        if ForestAreaRepository(db).get_by_id_for_user(
            forest_area_id=request.forest_area_id,
            user=current_user,
        ) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Forest area not found.",
            )

    if request.district_id is not None:
        permitted = {
            row["district_id"]
            for row in AnalyticsService(db).district_comparison(
                current_user
            )
        }

        if request.district_id not in permitted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="District not found.",
            )

    data = service.collect(
        user=current_user,
        request=ReportRequest(
            sections=request.sections,
            start_date=request.start_date,
            end_date=request.end_date,
            district_id=request.district_id,
            forest_area_id=request.forest_area_id,
            title=request.title,
        ),
    )

    try:
        if request.format == "pdf":
            content = PdfRenderer().render(data)
        elif request.format == "csv":
            content = render_csv(data)
        else:
            content = render_xlsx(data)

    except Exception as error:
        # Logged with the reference so a failure can be traced
        # to the request that caused it, while the officer is
        # told only that it failed. A stack trace would expose
        # internal paths.
        logger.exception(
            "Analytics report %s failed to render for user %s",
            data.reference,
            current_user.id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "The report could not be generated. "
                f"Reference {data.reference}."
            ),
        ) from error

    stamp = data.generated_at.strftime("%Y-%m-%d")

    filename = (
        f"Forest_Analytics_{_filename_scope(data)}_{stamp}"
        f".{request.format}"
    )

    return Response(
        content=content,
        media_type=MEDIA_TYPES[request.format],
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            ),
            "X-Report-Reference": data.reference,
            # Names suspected clearing locations, so it must
            # not be held in a shared cache.
            "Cache-Control": "no-store",
        },
    )


def _filename_scope(data) -> str:
    """
    Build a filename fragment describing the scope.

    Restricted to characters that are safe in a filename on
    every platform, because the value reaches a
    Content-Disposition header.
    """

    raw = "Copperbelt"

    for part in data.scope_description.split(" · "):
        if part.startswith(("Forest area:", "District:")):
            raw = part.split(":", 1)[1].strip()
            break

    cleaned = "".join(
        character if character.isalnum() else "_"
        for character in raw
    ).strip("_")

    return cleaned[:40] or "Copperbelt"

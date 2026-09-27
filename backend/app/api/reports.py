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

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.database.session import get_db
from app.models.user import User
from app.repositories.detection_repository import (
    DetectionRepository,
)
from app.services.report_service import ReportService


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

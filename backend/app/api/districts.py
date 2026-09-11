"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: District API

Purpose:
    Provides API endpoints for retrieving districts used
    by the ForestWatch Zambia application.

Responsibilities:
    - Retrieve active districts.
    - Return district names and codes.
    - Provide data for Forest Area registration forms.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.district import District


router = APIRouter(
    prefix="/districts",
    tags=["Districts"],
)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
)
def get_districts(
    db: Session = Depends(get_db),
):
    """
    Retrieve all active districts ordered alphabetically.

    The endpoint is used by the frontend when selecting
    a district while registering or managing a Forest Area.
    """

    districts = (
        db.query(District)
        .filter(District.is_active.is_(True))
        .order_by(District.name.asc())
        .all()
    )

    return [
        {
            "id": district.id,
            "name": district.name,
            "code": district.code,
            "province_id": district.province_id,
        }
        for district in districts
    ]
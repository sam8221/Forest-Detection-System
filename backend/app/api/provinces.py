"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Province API

Purpose:
    Provides API endpoints for retrieving provinces used
    by the ForestWatch Zambia application.

Responsibilities:
    - Retrieve active provinces.
    - Return province names and codes.
    - Provide the options shown when assigning a
      Provincial Forestry Officer a jurisdiction.

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

from app.api.deps import get_current_active_user
from app.database.session import get_db
from app.models.province import Province
from app.models.user import User


router = APIRouter(
    prefix="/provinces",
    tags=["Provinces"],
)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
)
def get_provinces(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Retrieve all active provinces ordered alphabetically.

    Used when an administrator assigns a jurisdiction to a
    Provincial Forestry Officer.

    Requires an authenticated user. The system is restricted
    to authorised Forestry Department officers, so even
    reference data is not served anonymously.
    """

    provinces = (
        db.query(Province)
        .filter(Province.is_active.is_(True))
        .order_by(Province.name.asc())
        .all()
    )

    return [
        {
            "id": province.id,
            "name": province.name,
            "code": province.code,
        }
        for province in provinces
    ]

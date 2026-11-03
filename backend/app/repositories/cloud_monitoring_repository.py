"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Cloud Monitoring Repository

Purpose:
    Supplies the two database readings the cloud monitoring
    card needs: where a district is, and how cloudy the
    imagery over it has been.

Responsibilities:
    - List the Copperbelt districts available to monitor.
    - Find the point to ask the weather provider about.
    - List recent Sentinel-2 observations with their
      recorded cloud cover.

Note:
    Every query for this feature lives here. The service
    layer above holds the rules and the API layer above
    that holds no logic at all, which is the layering the
    rest of this project keeps to.

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

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.district import District
from app.models.forest_area import ForestArea
from app.models.satellite_image import SatelliteImage


#: Where a district's observation point came from.
#:
#: Reported to the screen, because the two are not equally
#: good and an officer should be able to tell which they are
#: looking at.
POINT_FROM_MONITORED_AREAS = "monitored_areas"

POINT_FROM_DISTRICT_REFERENCE = "district_reference"


#: Reference coordinates for the Copperbelt districts.
#:
#: Used only for a district that has no monitored forest
#: area yet, and therefore no geometry to derive a point
#: from. Four of the ten districts were in that position
#: when this was written.
#:
#: These are the district towns, to about a tenth of a
#: degree. They locate a weather reading, nothing more: no
#: detection, no area and no boundary is derived from them,
#: and a district that gains a monitored area stops using
#: its entry here on the next request.
DISTRICT_REFERENCE_POINTS: dict[str, tuple[float, float]] = {
    "Kitwe": (-12.8024, 28.2132),
    "Ndola": (-12.9587, 28.6366),
    "Chingola": (-12.5287, 27.8838),
    "Mufulira": (-12.5500, 28.2408),
    "Luanshya": (-13.1367, 28.4166),
    "Kalulushi": (-12.8400, 28.0942),
    "Chililabombwe": (-12.3667, 27.8333),
    "Lufwanyama": (-13.0167, 27.5000),
    "Masaiti": (-13.3333, 28.4500),
    "Mpongwe": (-13.5167, 28.1500),
}


@dataclass(frozen=True)
class ObservationPoint:
    """
    The point a weather reading is asked about.

    Attributes:
        latitude, longitude:
            WGS84 coordinates.
        source:
            POINT_FROM_MONITORED_AREAS when derived from the
            geometry of the forest areas actually monitored
            in the district, which is the better of the two
            because it follows the real data.

            POINT_FROM_DISTRICT_REFERENCE when the district
            has no monitored area and the district town is
            used instead.
        monitored_area_count:
            How many forest areas the point was derived
            from. Zero for a reference point.
    """

    latitude: float

    longitude: float

    source: str

    monitored_area_count: int


@dataclass(frozen=True)
class SatelliteObservation:
    """
    One Sentinel-2 observation and the cloud cover recorded
    with it.

    Attributes:
        image_id:
            The satellite_images row.
        product_id:
            The Copernicus product name.
        acquisition_date:
            When the satellite passed. The figure's date,
            and never presented as the time now.
        cloud_cover_percentage:
            As recorded by the catalogue for that product.
        forest_area_name:
            The monitored area the scene covers.
        is_processed:
            Whether the system has analysed it.
    """

    image_id: int

    product_id: str

    acquisition_date: object

    cloud_cover_percentage: float

    forest_area_name: str

    is_processed: bool


class CloudMonitoringRepository:
    """Database reads for the cloud monitoring card."""

    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # Districts
    # ---------------------------------------------------------

    def active_districts(self) -> list[District]:
        """
        The districts that may be monitored.

        Returns:
            Active districts, in name order.

        Not scoped to a jurisdiction here. The service layer
        applies that, because the rule belongs with the
        rules and this method is also used to resolve a
        district's name for a provincial officer.
        """

        return list(
            self.db.scalars(
                select(District)
                .where(District.is_active.is_(True))
                .order_by(District.name)
            ).all()
        )

    def get_district(
        self,
        district_id: int,
    ) -> District | None:
        """
        One district by id, or None.

        Args:
            district_id:
                District to load.
        """

        return self.db.get(District, district_id)

    # ---------------------------------------------------------
    # Where to ask about
    # ---------------------------------------------------------

    def observation_point(
        self,
        district: District,
    ) -> ObservationPoint | None:
        """
        The point to ask the weather provider about.

        Args:
            district:
                District being monitored.

        Returns:
            A point, or None when neither the monitored
            areas nor the reference table can supply one.

        Derived from the forest areas actually monitored in
        the district: their geometries are collected and the
        centroid taken, so the reading follows the forest
        being watched rather than the district town, which
        in the Copperbelt is usually a mining settlement
        some distance from the reserve.

        The geometry is stored in UTM 35S and transformed to
        WGS84 here, because that is what a weather provider
        expects.
        """

        centroid = self.db.execute(
            select(
                func.ST_Y(
                    func.ST_Centroid(
                        func.ST_Collect(
                            func.ST_Transform(
                                ForestArea.geometry,
                                4326,
                            )
                        )
                    )
                ),
                func.ST_X(
                    func.ST_Centroid(
                        func.ST_Collect(
                            func.ST_Transform(
                                ForestArea.geometry,
                                4326,
                            )
                        )
                    )
                ),
                func.count(ForestArea.id),
            ).where(
                ForestArea.district_id == district.id,
                ForestArea.is_active.is_(True),
                ForestArea.geometry.isnot(None),
            )
        ).first()

        if centroid is not None:
            latitude, longitude, count = centroid

            if latitude is not None and longitude is not None:
                return ObservationPoint(
                    latitude=float(latitude),
                    longitude=float(longitude),
                    source=POINT_FROM_MONITORED_AREAS,
                    monitored_area_count=int(count or 0),
                )

        reference = DISTRICT_REFERENCE_POINTS.get(
            district.name
        )

        if reference is None:
            return None

        return ObservationPoint(
            latitude=reference[0],
            longitude=reference[1],
            source=POINT_FROM_DISTRICT_REFERENCE,
            monitored_area_count=0,
        )

    # ---------------------------------------------------------
    # Satellite cloud cover
    # ---------------------------------------------------------

    def recent_observations(
        self,
        district_id: int,
        limit: int,
    ) -> list[SatelliteObservation]:
        """
        Recent Sentinel-2 observations over a district.

        Args:
            district_id:
                District whose monitored areas to look at.
            limit:
                Most observations to return.

        Returns:
            Observations newest first, each carrying the
            cloud cover the catalogue recorded for it.

        Reads imagery the system already holds rather than
        asking Copernicus again. The cloud figure was taken
        from the catalogue when the product was registered,
        so this needs no network and keeps working when the
        provider is down, which is also what lets the card
        show satellite cloud cover while the weather half is
        unavailable.
        """

        rows = self.db.execute(
            select(
                SatelliteImage.id,
                SatelliteImage.product_id,
                SatelliteImage.acquisition_date,
                SatelliteImage.cloud_cover_percentage,
                ForestArea.name,
                SatelliteImage.is_processed,
            )
            .join(
                ForestArea,
                SatelliteImage.forest_area_id == ForestArea.id,
            )
            .where(
                ForestArea.district_id == district_id,
                SatelliteImage.is_active.is_(True),
            )
            .order_by(
                SatelliteImage.acquisition_date.desc(),
                SatelliteImage.id.desc(),
            )
            .limit(limit)
        ).all()

        return [
            SatelliteObservation(
                image_id=row[0],
                product_id=row[1],
                acquisition_date=row[2],
                cloud_cover_percentage=float(row[3]),
                forest_area_name=row[4],
                is_processed=bool(row[5]),
            )
            for row in rows
        ]

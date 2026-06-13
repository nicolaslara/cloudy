"""Lightning read contract: one spatial filter + one presentation format.

Spatial modes (mutually exclusive):
  - Sweden default — no lat/lon/radius/bbox query params
  - radius — lat + lon + radius_km (bbox is derived for the SQL prefilter)
  - bbox — minLon,minLat,maxLon,maxLat string (no radius)

Presentation:
  - series — aggregated buckets for the bar chart
  - strokes — individual events for the map explorer
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from math import cos, radians
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from cloudy.core.lightning_limits import DEFAULT_MAP_STROKE_POINTS, MAX_MAP_STROKE_POINTS
from cloudy.core.lightning_types import (
    SpatialMeta,
    SpatialMetaBbox,
    SpatialMetaRadius,
    SpatialMetaSweden,
)
from cloudy.core.series_plan import MAX_TARGET_POINTS, Aggregation, choose_target_points

SWEDEN_BBOX = (9.0, 55.0, 26.0, 70.0)  # min_lon, min_lat, max_lon, max_lat
DEFAULT_FROM = date(2015, 1, 1)
_KM_PER_DEG_LAT = 111.0

LightningFormat = Literal["series", "strokes"]
DEFAULT_AGGREGATION: Aggregation = "auto"


@dataclass(frozen=True)
class SpatialBounds:
    """Resolved lon/lat bounds plus optional haversine radius refinement."""

    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float
    center_lat: float | None = None
    center_lon: float | None = None
    radius_km: float | None = None

    @property
    def use_radius(self) -> bool:
        return (
            self.radius_km is not None
            and self.center_lat is not None
            and self.center_lon is not None
        )

    @property
    def mode(self) -> Literal["sweden", "bbox", "radius"]:
        if self.use_radius:
            return "radius"
        if (self.min_lon, self.min_lat, self.max_lon, self.max_lat) != SWEDEN_BBOX:
            return "bbox"
        return "sweden"

    def as_meta(self) -> SpatialMeta:
        if self.use_radius:
            assert self.center_lat is not None
            assert self.center_lon is not None
            assert self.radius_km is not None
            return SpatialMetaRadius(
                mode="radius",
                lat=self.center_lat,
                lon=self.center_lon,
                radius_km=self.radius_km,
            )
        if self.mode == "bbox":
            return SpatialMetaBbox(
                mode="bbox",
                bbox=[self.min_lon, self.min_lat, self.max_lon, self.max_lat],
            )
        return SpatialMetaSweden(mode="sweden", bbox=list(SWEDEN_BBOX))

    @classmethod
    def sweden(cls) -> Self:
        return cls(*SWEDEN_BBOX)

    @classmethod
    def from_bbox(cls, min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> Self:
        return cls(min_lon, min_lat, max_lon, max_lat)

    @classmethod
    def from_radius(cls, lat: float, lon: float, radius_km: float) -> Self:
        dlat = radius_km / _KM_PER_DEG_LAT
        dlon = radius_km / (_KM_PER_DEG_LAT * cos(radians(lat)))
        return cls(
            lon - dlon,
            lat - dlat,
            lon + dlon,
            lat + dlat,
            center_lat=lat,
            center_lon=lon,
            radius_km=radius_km,
        )


def parse_bbox(raw: str) -> tuple[float, float, float, float]:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be minLon,minLat,maxLon,maxLat")
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    except ValueError as exc:
        raise ValueError("bbox values must be numbers") from exc
    if not (SWEDEN_BBOX[0] <= min_lon < max_lon <= SWEDEN_BBOX[2]):
        raise ValueError("bbox longitude outside Sweden bounds")
    if not (SWEDEN_BBOX[1] <= min_lat < max_lat <= SWEDEN_BBOX[3]):
        raise ValueError("bbox latitude outside Sweden bounds")
    return min_lon, min_lat, max_lon, max_lat


class LightningQuery(BaseModel):
    """GET /api/v1/lightning — shared filter + presentation."""

    model_config = {"populate_by_name": True}

    date_from: Annotated[date, Field(alias="from")] = DEFAULT_FROM
    date_to: Annotated[date | None, Field(alias="to")] = None

    lat: Annotated[float | None, Field(ge=54.0, le=70.0)] = None
    lon: Annotated[float | None, Field(ge=9.0, le=26.0)] = None
    radius_km: int | None = None
    bbox: str | None = None

    format: LightningFormat = "series"
    aggregation: Aggregation = DEFAULT_AGGREGATION
    width_px: Annotated[int | None, Field(ge=100, le=10_000)] = None
    max_points: Annotated[int | None, Field(ge=1, le=MAX_TARGET_POINTS)] = None
    limit: Annotated[int, Field(ge=1, le=MAX_MAP_STROKE_POINTS)] = DEFAULT_MAP_STROKE_POINTS

    @field_validator("bbox")
    @classmethod
    def _bbox_syntax(cls, value: str | None) -> str | None:
        if value is not None:
            parse_bbox(value)  # raises ValueError → 422 in the route
        return value

    @field_validator("radius_km")
    @classmethod
    def _radius_km(cls, value: int | None) -> int | None:
        if value is not None and value not in (10, 25):
            raise ValueError("radius_km must be 10 or 25")
        return value

    @model_validator(mode="after")
    def _spatial_and_presentation(self) -> Self:
        has_lat = self.lat is not None
        has_lon = self.lon is not None
        if has_lat ^ has_lon:
            raise ValueError("lat and lon must be provided together")
        if self.radius_km is not None and not (has_lat and has_lon):
            raise ValueError("radius_km requires lat and lon")
        if self.radius_km is not None and self.bbox is not None:
            raise ValueError("radius_km and bbox are mutually exclusive")
        if self.date_from > self.resolved_date_to():
            raise ValueError("from must be on or before to")
        return self

    def resolved_date_to(self) -> date:
        return self.date_to or datetime.now(UTC).date()

    def spatial(self) -> SpatialBounds:
        if self.radius_km is not None:
            return SpatialBounds.from_radius(self.lat, self.lon, self.radius_km)  # type: ignore[arg-type]
        if self.bbox is not None:
            return SpatialBounds.from_bbox(*parse_bbox(self.bbox))
        return SpatialBounds.sweden()

    def cache_key(self) -> str:
        spatial = self.spatial()
        target_points = choose_target_points(self.width_px, self.max_points)
        return (
            f"lightning:{self.format}:{self.aggregation}:{target_points}:{self.limit}"
            f":{self.date_from}:{self.resolved_date_to()}"
            f":{spatial.min_lon}:{spatial.min_lat}:{spatial.max_lon}:{spatial.max_lat}"
            f":{spatial.center_lat}:{spatial.center_lon}:{spatial.radius_km}"
        )

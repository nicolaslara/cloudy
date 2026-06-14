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

from datetime import UTC, date, datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

# SpatialBounds and bbox parsing are foundation primitives shared with
# climatology; only the mapping to exploration's wire `SpatialMeta` lives here.
from cloudy.core.spatial import SWEDEN_BBOX, SpatialBounds, parse_bbox
from cloudy.exploration.lightning_limits import DEFAULT_MAP_STROKE_POINTS, MAX_MAP_STROKE_POINTS
from cloudy.exploration.lightning_types import (
    SpatialMeta,
    SpatialMetaBbox,
    SpatialMetaRadius,
    SpatialMetaSweden,
)
from cloudy.exploration.series_plan import MAX_TARGET_POINTS, Aggregation, choose_target_points

DEFAULT_FROM = date(2015, 1, 1)

LightningFormat = Literal["series", "strokes"]
DEFAULT_AGGREGATION: Aggregation = "auto"


def spatial_meta(bounds: SpatialBounds) -> SpatialMeta:
    """Project resolved bounds onto the wire shape the explorer expects.

    Kept out of SpatialBounds itself so the geometry can stay in the foundation:
    the meta types are an exploration presentation concern, not a property of the
    box. The "sweden" branch reports the canonical extent, not the (identical)
    stored bounds, so the contract is stable regardless of how bounds were built.
    """
    if bounds.use_radius:
        assert bounds.center_lat is not None
        assert bounds.center_lon is not None
        assert bounds.radius_km is not None
        return SpatialMetaRadius(
            mode="radius",
            lat=bounds.center_lat,
            lon=bounds.center_lon,
            radius_km=bounds.radius_km,
        )
    if bounds.mode == "bbox":
        return SpatialMetaBbox(
            mode="bbox",
            bbox=[bounds.min_lon, bounds.min_lat, bounds.max_lon, bounds.max_lat],
        )
    return SpatialMetaSweden(mode="sweden", bbox=list(SWEDEN_BBOX))


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
        # Everything that changes the response bytes goes in the key: the resolved
        # bounds (not the raw lat/lon/bbox inputs, so equivalent requests share a
        # hit) and the target-point budget (so a wide and a narrow chart of the
        # same window don't collide on differently-downsampled payloads).
        spatial = self.spatial()
        target_points = choose_target_points(self.width_px, self.max_points)
        return (
            f"lightning:{self.format}:{self.aggregation}:{target_points}:{self.limit}"
            f":{self.date_from}:{self.resolved_date_to()}"
            f":{spatial.min_lon}:{spatial.min_lat}:{spatial.max_lon}:{spatial.max_lat}"
            f":{spatial.center_lat}:{spatial.center_lon}:{spatial.radius_km}"
        )

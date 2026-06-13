"""Cloud read contract: optional lat/lon → station or Sweden aggregate series."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Self

from pydantic import BaseModel, Field, model_validator

from cloudy.core.series_plan import MAX_TARGET_POINTS, Aggregation, choose_target_points

DEFAULT_FROM = date(2015, 1, 1)
DEFAULT_AGGREGATION: Aggregation = "auto"


class CloudQuery(BaseModel):
    """GET /api/v1/cloud — station or Sweden-wide time rollup."""

    model_config = {"populate_by_name": True}

    lat: Annotated[float | None, Field(ge=54.0, le=70.0)] = None
    lon: Annotated[float | None, Field(ge=9.0, le=26.0)] = None
    date_from: Annotated[date, Field(alias="from")] = DEFAULT_FROM
    date_to: Annotated[date | None, Field(alias="to")] = None
    aggregation: Aggregation = DEFAULT_AGGREGATION
    width_px: Annotated[int | None, Field(ge=100, le=10_000)] = None
    max_points: Annotated[int | None, Field(ge=1, le=MAX_TARGET_POINTS)] = None

    @model_validator(mode="after")
    def _date_range(self) -> Self:
        has_lat = self.lat is not None
        has_lon = self.lon is not None
        if has_lat ^ has_lon:
            raise ValueError("lat and lon must be provided together")
        if self.date_from > self.resolved_date_to():
            raise ValueError("from must be on or before to")
        return self

    @property
    def has_location(self) -> bool:
        return self.lat is not None and self.lon is not None

    def resolved_date_to(self) -> date:
        return self.date_to or datetime.now(UTC).date()

    def cache_key(self, station_id: int | None) -> str:
        target_points = choose_target_points(self.width_px, self.max_points)
        scope = f"station:{station_id}" if station_id is not None else "sweden"
        return (
            f"cloud:{scope}:{self.aggregation}"
            f":{self.date_from}:{self.resolved_date_to()}"
            f":{target_points}:{self.lat}:{self.lon}"
        )

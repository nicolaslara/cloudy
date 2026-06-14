"""Cloud read contract: optional lat/lon → station or Sweden aggregate series."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Self

from pydantic import BaseModel, Field, model_validator

from cloudy.exploration.series_plan import MAX_TARGET_POINTS, Aggregation, choose_target_points

DEFAULT_FROM = date(2015, 1, 1)
DEFAULT_AGGREGATION: Aggregation = "auto"


class CloudQuery(BaseModel):
    """GET /api/v1/cloud — station or Sweden-wide time rollup."""

    model_config = {"populate_by_name": True}

    # lat/lon bound to Sweden's envelope so a typo'd coordinate is a 422, not a
    # silent empty result. Both are optional and all-or-nothing (see validator):
    # absent means the Sweden-wide aggregate, present means nearest-station.
    lat: Annotated[float | None, Field(ge=54.0, le=70.0)] = None
    lon: Annotated[float | None, Field(ge=9.0, le=26.0)] = None
    # 2015 default matches the lightning history floor so cloud and lightning
    # charts share an x-axis out of the box; `to` defaults to today at read time.
    date_from: Annotated[date, Field(alias="from")] = DEFAULT_FROM
    date_to: Annotated[date | None, Field(alias="to")] = None
    aggregation: Aggregation = DEFAULT_AGGREGATION
    # The client sends its chart width so the backend can pick a resolution that
    # fits the pixels; max_points lets a caller cap that independently. Both feed
    # the shared planner — see series_plan.choose_target_points.
    width_px: Annotated[int | None, Field(ge=100, le=10_000)] = None
    max_points: Annotated[int | None, Field(ge=1, le=MAX_TARGET_POINTS)] = None

    @model_validator(mode="after")
    def _date_range(self) -> Self:
        # Half a coordinate is meaningless — reject lat-without-lon (or vice
        # versa) here rather than guessing a center downstream.
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
        # The key must capture everything that changes the bytes we'd serve.
        # width/max_points are collapsed to the single resolved target_points so
        # two slightly different widths that plan identically share a cache entry.
        # The resolved station id (not raw lat/lon) is the scope, so every
        # coordinate that maps to the same station reuses one entry; lat/lon are
        # still appended because they appear in the station distance metadata.
        target_points = choose_target_points(self.width_px, self.max_points)
        scope = f"station:{station_id}" if station_id is not None else "sweden"
        return (
            f"cloud:{scope}:{self.aggregation}"
            f":{self.date_from}:{self.resolved_date_to()}"
            f":{target_points}:{self.lat}:{self.lon}"
        )

"""Request models for the climatology API.

Both endpoints are point queries — a normal is always *for a place*. Coordinates
are bound to Sweden's envelope so a typo lands as a 422 instead of silently
returning an empty normal. Validation is expressed as pydantic field bounds plus
a `Literal` for `period`; the route layer converts any ValidationError into a
ValueError-shaped 422, matching the exploration controllers.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

# Recurring bucket the normal is grouped by. Defaults to "month": the product's
# primary view is the twelve-month normal, and the current-month expectation is
# only meaningful in monthly terms.
Period = Literal["day", "month", "year"]
DEFAULT_PERIOD: Period = "month"


class ClimatologyCloudQuery(BaseModel):
    """GET /climatology/cloud — cloud normals for a place, or all of Sweden.

    lat/lon are optional and travel as a pair: give both for the normal at the
    nearest station, give neither for the Sweden-wide normal aggregated across
    every active station. Bounds match the exploration queries so a coordinate
    that works for the chart works for the normal.
    """

    model_config = {"populate_by_name": True}

    lat: Annotated[float | None, Field(ge=54.0, le=70.0)] = None
    lon: Annotated[float | None, Field(ge=9.0, le=26.0)] = None
    period: Period = DEFAULT_PERIOD
    # Cloud stations are sparse (often only 0-1 within 50 km, a handful within
    # 100 km), so the cloud distance is much coarser than lightning's 10/25 km:
    # 50 km is "nearest area", 100 km a regional pool. Cloud climatology varies
    # slowly in space, so pooling a region is a fair proxy for "cloud here" and
    # buys a bigger sample. Only meaningful with a location; ignored Sweden-wide.
    radius_km: Literal[50, 100] = 50

    @property
    def has_location(self) -> bool:
        return self.lat is not None and self.lon is not None

    @model_validator(mode="after")
    def _location_is_a_pair(self) -> Self:
        # One coordinate without the other is meaningless to a station lookup, so
        # reject it rather than guess — neither means the Sweden-wide aggregate.
        if (self.lat is None) ^ (self.lon is None):
            raise ValueError("lat and lon must be provided together")
        return self


class ClimatologyLightningQuery(BaseModel):
    """GET /climatology/lightning — lightning normals near a place, or Sweden-wide.

    With lat/lon, the normal counts discharges within `radius_km` (10 or 25 km —
    the radii SMHI's thunder-day products use; lightning is never modelled at the
    bare point). Without lat/lon it's all of Sweden, and the radius is ignored.
    """

    model_config = {"populate_by_name": True}

    lat: Annotated[float | None, Field(ge=54.0, le=70.0)] = None
    lon: Annotated[float | None, Field(ge=9.0, le=26.0)] = None
    period: Period = DEFAULT_PERIOD
    radius_km: Literal[10, 25] = 10

    @property
    def has_location(self) -> bool:
        return self.lat is not None and self.lon is not None

    @model_validator(mode="after")
    def _location_is_a_pair(self) -> Self:
        if (self.lat is None) ^ (self.lon is None):
            raise ValueError("lat and lon must be provided together")
        return self

"""Request models for the predictions API.

Mirrors climatology/query.py exactly: lat/lon are validated and must arrive as a
pair (both or neither), Sweden-envelope bounds reject typos as 422s, and the
radius Literals are the same choices the climatology and exploration layers use so a
frontend call that works for Normals works for Predictions without any adaptation.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator


class PredictionsCloudQuery(BaseModel):
    """GET /predictions/cloud — damped-persistence forecast and backtest.

    lat/lon come as a pair (both for a place, neither for Sweden-wide). The cloud
    radius choices are coarser than lightning's because cloud varies slowly in
    space and station density is low — the same reasoning as climatology.
    """

    model_config = {"populate_by_name": True}

    lat: Annotated[float | None, Field(ge=54.0, le=70.0)] = None
    lon: Annotated[float | None, Field(ge=9.0, le=26.0)] = None
    # 50 km is "nearest area"; 100 km a regional pool. Cloud climatology is
    # spatially smooth so the larger pool buys sample without sacrificing signal.
    radius_km: Literal[50, 100] = 50

    @property
    def has_location(self) -> bool:
        return self.lat is not None and self.lon is not None

    @model_validator(mode="after")
    def _location_is_a_pair(self) -> Self:
        # One coordinate without the other is meaningless to a station lookup.
        # Reject it rather than guess — neither means Sweden-wide.
        if (self.lat is None) ^ (self.lon is None):
            raise ValueError("lat and lon must be provided together")
        return self


class SpatialQuery(BaseModel):
    """GET /predictions/spatial — the spatial cloud normal at a point.

    Unlike the outlooks, lat/lon are both REQUIRED: a point estimate of "cloud here"
    is meaningless Sweden-wide, so there is no None/pair dance — a missing coordinate
    is just a 422. Same Sweden-envelope bounds reject typos.

    `model` selects how the week-of-year normal is estimated at the point, in
    increasing pooling: ``nearest`` (the single closest station) or ``knn`` (the
    equal-weight average of the k nearest stations). They share one neighbour set so
    the two read as a progression; an unknown id is a 422.
    """

    model_config = {"populate_by_name": True}

    lat: Annotated[float, Field(ge=54.0, le=70.0)]
    lon: Annotated[float, Field(ge=9.0, le=26.0)]
    model: Literal["nearest", "knn"] = "knn"


class BacktestSeriesQuery(BaseModel):
    """GET /predictions/backtest-series — a model's forecast-vs-actual over the backtest.

    Same lat/lon pair rule and cloud radii as the outlook (the backtest must reflect
    how a located query actually pools stations). `model` picks the forward model and
    `lead` the horizon (1 or 2 weeks), both validated so a typo is a 422.
    """

    model_config = {"populate_by_name": True}

    lat: Annotated[float | None, Field(ge=54.0, le=70.0)] = None
    lon: Annotated[float | None, Field(ge=9.0, le=26.0)] = None
    radius_km: Literal[50, 100] = 50
    model: Literal["damped"] = "damped"
    lead: Literal[1, 2] = 1

    @model_validator(mode="after")
    def _location_is_a_pair(self) -> Self:
        if (self.lat is None) ^ (self.lon is None):
            raise ValueError("lat and lon must be provided together")
        return self


class PredictionsLightningQuery(BaseModel):
    """GET /predictions/lightning-outlook — damped-persistence lightning outlook.

    Same radius choices as the lightning climatology (10/25 km — lightning is never
    modelled at the bare point), but the outlook *defaults* to the wider 25 km: a
    weekly lightning-day count is sparse, so the larger area buys enough strike-days
    for the persistence signal to be worth stating at all.
    """

    model_config = {"populate_by_name": True}

    lat: Annotated[float | None, Field(ge=54.0, le=70.0)] = None
    lon: Annotated[float | None, Field(ge=9.0, le=26.0)] = None
    radius_km: Literal[10, 25] = 25

    @property
    def has_location(self) -> bool:
        return self.lat is not None and self.lon is not None

    @model_validator(mode="after")
    def _location_is_a_pair(self) -> Self:
        if (self.lat is None) ^ (self.lon is None):
            raise ValueError("lat and lon must be provided together")
        return self

"""Typed response shapes for lightning read paths (series + strokes)."""

from __future__ import annotations

from typing import Literal, TypedDict

Aggregation = Literal["auto", "raw", "hour", "6h", "day", "week", "month", "year"]
Resolution = Literal["raw", "hour", "6h", "day", "week", "month", "year"]
StrokeColumn = Literal["lon", "lat", "peak_ka", "cg", "ts"]
StrokeRow = list[float | int]


class SpatialMetaSweden(TypedDict):
    mode: Literal["sweden"]
    bbox: list[float]


class SpatialMetaBbox(TypedDict):
    mode: Literal["bbox"]
    bbox: list[float]


class SpatialMetaRadius(TypedDict):
    mode: Literal["radius"]
    lat: float
    lon: float
    radius_km: float


# Discriminated on `mode`: the radius variant carries the circle (the bbox is
# only an internal prefilter and isn't echoed back), while the sweden/bbox
# variants carry just the box. The frontend switches on `mode` to label the scope.
SpatialMeta = SpatialMetaSweden | SpatialMetaBbox | SpatialMetaRadius


class LightningPeriod(TypedDict):
    period: str
    bucket_start: str
    bucket_end: str
    cg_count: int
    all_count: int
    lightning_days: int
    max_abs_peak_ka: float
    strongest_event_time: str | None


# Series and strokes carry deliberately different meta: a bar series reports its
# resolution/mode/target-points planning, whereas strokes report sampling honesty
# (how many were dropped and how). Keeping them as separate TypedDicts means a
# field can't accidentally leak from one presentation into the other.
StrokesDownsampleMeta = TypedDict(
    "StrokesDownsampleMeta",
    {
        "from": str,
        "to": str,
        "total_matched": int,
        "returned": int,
        "downsampled": bool,
        "stride": int | None,
        "sample_method": str | None,
        "dropped_count": int,
        "representation": str,
        "is_complete": bool,
    },
)


class StrokesQueryResult(TypedDict):
    columns: list[StrokeColumn]
    rows: list[StrokeRow]
    meta: StrokesDownsampleMeta


SeriesResponseMeta = TypedDict(
    "SeriesResponseMeta",
    {
        "from": str,
        "to": str,
        "sources": list[str],
        "attribution": str,
        "generated_at": str,
        "total_matched": int,
        "returned": int,
        "requested_aggregation": str,
        "resolved_resolution": str,
        "mode": str,
        "representation": str,
        "target_points": int,
        "point_count": int,
        "is_complete": bool,
    },
)


StrokesResponseMeta = TypedDict(
    "StrokesResponseMeta",
    {
        "from": str,
        "to": str,
        "sources": list[str],
        "attribution": str,
        "generated_at": str,
        "total_matched": int,
        "returned": int,
        "downsampled": bool,
        "stride": int | None,
        "sample_method": str | None,
        "dropped_count": int,
        "representation": str,
        "is_complete": bool,
    },
)


class LightningSeriesResponse(TypedDict):
    format: Literal["series"]
    aggregation: Aggregation
    resolved_resolution: Resolution
    spatial: SpatialMeta
    series: list[LightningPeriod]
    meta: SeriesResponseMeta


class LightningStrokesResponse(TypedDict):
    format: Literal["strokes"]
    columns: list[StrokeColumn]
    rows: list[StrokeRow]
    spatial: SpatialMeta
    meta: StrokesResponseMeta


LightningResponse = LightningSeriesResponse | LightningStrokesResponse

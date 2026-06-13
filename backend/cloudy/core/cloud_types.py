"""Typed response shapes for GET /api/v1/cloud."""

from __future__ import annotations

from typing import Literal, TypedDict

Aggregation = Literal["auto", "raw", "hour", "6h", "day", "week", "month", "year"]
Resolution = Literal["raw", "hour", "6h", "day", "week", "month", "year"]


class CloudStationMeta(TypedDict):
    station_id: int
    name: str
    distance_km: float


class CloudPeriod(TypedDict):
    period: str
    bucket_start: str
    bucket_end: str
    mean_cloud_pct: float | None
    min_cloud_pct: float | None
    max_cloud_pct: float | None
    p05_cloud_pct: float | None
    p50_cloud_pct: float | None
    p95_cloud_pct: float | None
    observed_count: int
    expected_count: int
    missing_count: int


class CloudSeriesMeta(TypedDict):
    total_matched: int
    returned: int
    requested_aggregation: str
    resolved_resolution: str
    mode: str
    representation: str
    target_points: int
    point_count: int
    is_complete: bool


class CloudSeriesQueryResult(TypedDict):
    series: list[CloudPeriod]
    coverage_fraction: float
    meta: CloudSeriesMeta


CloudResponseMeta = TypedDict(
    "CloudResponseMeta",
    {
        "from": str,
        "to": str,
        "coverage_fraction": float,
        "scope": str,
        "station_count": int | None,
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


class CloudSeriesResponse(TypedDict):
    aggregation: Aggregation
    resolved_resolution: Resolution
    station: CloudStationMeta | None
    series: list[CloudPeriod]
    meta: CloudResponseMeta

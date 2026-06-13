"""Backend-owned level-of-detail planning for chart series.

The planner is intentionally pure: no SQL, no FastAPI, no source-specific
format knowledge. Adapters estimate source costs, then ask this module whether
a request is safe and which semantic resolution to serve.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from cloudy.core.lightning_limits import MAX_RAW_LIGHTNING_CHART_EVENTS

Dataset = Literal["cloud", "lightning"]
Aggregation = Literal["auto", "raw", "hour", "6h", "day", "week", "month", "year"]
Resolution = Literal["raw", "hour", "6h", "day", "week", "month", "year"]
Mode = Literal["raw", "aggregate"]

DEFAULT_WIDTH_PX = 1200
MIN_TARGET_POINTS = 300
MAX_TARGET_POINTS = 3_000
MAX_RAW_CLOUD_POINTS = 3_000
MAX_RAW_LIGHTNING_EVENTS = MAX_RAW_LIGHTNING_CHART_EVENTS
MAX_LIGHTNING_SCAN_EVENTS = 5_000_000

_RESOLUTIONS: tuple[Resolution, ...] = ("raw", "hour", "6h", "day", "week", "month", "year")
_AGGREGATE_RESOLUTIONS: tuple[Resolution, ...] = (
    "hour",
    "6h",
    "day",
    "week",
    "month",
    "year",
)


@dataclass(frozen=True)
class SeriesPlan:
    dataset: Dataset
    requested_aggregation: Aggregation
    resolved_resolution: Resolution
    mode: Mode
    target_points: int
    estimated_points: int
    representation: str


@dataclass(frozen=True)
class QueryRejected(Exception):
    code: str
    message: str
    estimated_points: int
    limit: int
    suggested_aggregation: Resolution

    def as_detail(self) -> dict[str, object]:
        return {
            "error": self.code,
            "message": self.message,
            "estimated_points": self.estimated_points,
            "limit": self.limit,
            "suggested_aggregation": self.suggested_aggregation,
        }


def choose_target_points(width_px: int | None, max_points: int | None = None) -> int:
    width = width_px or DEFAULT_WIDTH_PX
    target = max(MIN_TARGET_POINTS, min(int(width * 1.5), MAX_TARGET_POINTS))
    if max_points is None:
        return target
    return max(1, min(max_points, target, MAX_TARGET_POINTS))


def date_range_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    start = datetime.combine(date_from, time.min, tzinfo=UTC)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
    return start, end


def raw_cloud_points(date_from: date, date_to: date) -> int:
    start, end = date_range_bounds(date_from, date_to)
    return int((end - start).total_seconds() // 3600)


def bucket_count(resolution: Resolution, date_from: date, date_to: date) -> int:
    if resolution == "raw":
        return raw_cloud_points(date_from, date_to)
    if resolution == "hour":
        return raw_cloud_points(date_from, date_to)
    if resolution == "6h":
        return (raw_cloud_points(date_from, date_to) + 5) // 6
    if resolution == "day":
        return (date_to - date_from).days + 1
    if resolution == "week":
        start = _week_start(date_from)
        end = _week_start(date_to)
        return ((end - start).days // 7) + 1
    if resolution == "month":
        return (date_to.year - date_from.year) * 12 + date_to.month - date_from.month + 1
    return date_to.year - date_from.year + 1


def _week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())


def choose_resolution(
    dataset: Dataset,
    date_from: date,
    date_to: date,
    target_points: int,
    lightning_event_count: int | None = None,
) -> Resolution:
    days = _calendar_days(date_from, date_to)
    if dataset == "cloud" and days <= 14 and raw_cloud_points(date_from, date_to) <= target_points:
        return "raw"
    if (
        dataset == "lightning"
        and lightning_event_count is not None
        and lightning_event_count <= min(target_points, MAX_RAW_LIGHTNING_EVENTS)
        and days == 1
    ):
        return "raw"
    for resolution in _candidate_resolutions(dataset, date_from, date_to):
        if bucket_count(resolution, date_from, date_to) <= target_points:
            return resolution
    return "year"


def _calendar_days(date_from: date, date_to: date) -> int:
    return (date_to - date_from).days + 1


def _candidate_resolutions(
    dataset: Dataset,
    date_from: date,
    date_to: date,
) -> tuple[Resolution, ...]:
    if dataset == "cloud":
        days = _calendar_days(date_from, date_to)
        if days <= 14:
            return ("hour", "6h", "day", "week", "month", "year")
        if days <= 93:
            return ("day", "week", "month", "year")
        if days <= 366:
            return ("week", "month", "year")
        return ("month", "year")

    days = _calendar_days(date_from, date_to)
    if days <= 14:
        return ("hour", "6h", "day", "week", "month", "year")
    if days <= 93:
        return ("day", "week", "month", "year")
    if days <= 366:
        return ("week", "month", "year")
    return ("month", "year")


def plan_series(
    dataset: Dataset,
    date_from: date,
    date_to: date,
    requested: Aggregation,
    width_px: int | None = None,
    max_points: int | None = None,
    lightning_event_count: int | None = None,
) -> SeriesPlan:
    target_points = choose_target_points(width_px, max_points)
    resolution = (
        choose_resolution(dataset, date_from, date_to, target_points, lightning_event_count)
        if requested == "auto"
        else requested
    )
    if dataset == "lightning" and resolution == "raw":
        estimated = lightning_event_count
        if estimated is None:
            raise ValueError("lightning_event_count is required for raw lightning planning")
    elif dataset == "cloud" and resolution == "raw":
        estimated = raw_cloud_points(date_from, date_to)
    else:
        estimated = bucket_count(resolution, date_from, date_to)
    _reject_if_unsafe(
        dataset,
        requested,
        resolution,
        estimated,
        target_points,
        date_from,
        date_to,
        lightning_event_count,
    )
    mode: Mode = "raw" if resolution == "raw" else "aggregate"
    return SeriesPlan(
        dataset=dataset,
        requested_aggregation=requested,
        resolved_resolution=resolution,
        mode=mode,
        target_points=target_points,
        estimated_points=estimated,
        representation=f"{dataset}_{mode}_{resolution}",
    )


def _reject_if_unsafe(
    dataset: Dataset,
    requested: Aggregation,
    resolution: Resolution,
    estimated: int,
    target_points: int,
    date_from: date,
    date_to: date,
    lightning_event_count: int | None,
) -> None:
    suggested = choose_resolution(dataset, date_from, date_to, target_points, lightning_event_count)
    if resolution == "raw":
        limit = MAX_RAW_CLOUD_POINTS if dataset == "cloud" else MAX_RAW_LIGHTNING_EVENTS
        if estimated > limit:
            raise QueryRejected(
                "too_many_points_for_raw_response",
                "Raw response would return too many points.",
                estimated,
                limit,
                suggested,
            )
    elif estimated > target_points:
        raise QueryRejected(
            "too_many_buckets_for_response",
            "Requested aggregation would return too many buckets.",
            estimated,
            target_points,
            suggested,
        )
    if (
        dataset == "lightning"
        and lightning_event_count is not None
        and requested != "raw"
        and lightning_event_count > MAX_LIGHTNING_SCAN_EVENTS
    ):
        raise QueryRejected(
            "too_many_events_to_scan",
            "Lightning query would scan too many matched events.",
            lightning_event_count,
            MAX_LIGHTNING_SCAN_EVENTS,
            suggested,
        )

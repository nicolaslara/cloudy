"""Dispatch a validated CloudQuery to the station series reader."""

from dataclasses import replace
from datetime import UTC, date, datetime

from sqlalchemy import Engine
from sqlmodel import Session

from cloudy.exploration.cloud_query import CloudQuery
from cloudy.exploration.cloud_series import query_series, query_sweden_series
from cloudy.exploration.cloud_types import CloudSeriesResponse, CloudStationMeta
from cloudy.exploration.series_plan import SeriesPlan, bucket_count, plan_series
from cloudy.ingest import stations


def execute(engine: Engine, query: CloudQuery) -> CloudSeriesResponse:
    date_to = query.resolved_date_to()
    generated_at = datetime.now(UTC).isoformat()

    plan = plan_series(
        "cloud",
        query.date_from,
        date_to,
        query.aggregation,
        query.width_px,
        query.max_points,
    )
    if query.has_location:
        # A coordinate resolves to the nearest *active* station, not a grid cell:
        # cloud cover here comes from point observations, so we attach the series
        # to a real station and report its distance for honesty. No station in
        # range is a LookupError the route turns into a 404.
        assert query.lat is not None
        assert query.lon is not None
        with Session(engine) as session:
            try:
                nearest, distance_km = stations.nearest_active(session, query.lat, query.lon)
            except LookupError as exc:
                raise LookupError(str(exc)) from exc

        series, coverage = query_series(engine, nearest.id, plan, query.date_from, date_to)
        station: CloudStationMeta | None = {
            "station_id": nearest.id,
            "name": nearest.name,
            "distance_km": round(distance_km, 1),
        }
        scope = "station"
        station_count = None
    else:
        # No location → aggregate across all active stations. The Sweden path has
        # no per-station raw rows to serve, so any "raw" plan is rewritten to an
        # hourly aggregate before querying (see _sweden_aggregate_plan).
        plan = _sweden_aggregate_plan(plan, query.date_from, date_to)
        series, coverage, station_count = query_sweden_series(
            engine,
            plan,
            query.date_from,
            date_to,
        )
        station = None
        scope = "sweden"

    return {
        "aggregation": query.aggregation,
        "resolved_resolution": plan.resolved_resolution,
        "station": station,
        "series": series,
        "meta": {
            "from": query.date_from.isoformat(),
            "to": date_to.isoformat(),
            "coverage_fraction": coverage,
            "scope": scope,
            "station_count": station_count,
            "sources": ["smhi-metobs"],
            "attribution": "Source: SMHI",
            "generated_at": generated_at,
            "total_matched": plan.estimated_points,
            "returned": len(series),
            "requested_aggregation": plan.requested_aggregation,
            "resolved_resolution": plan.resolved_resolution,
            "mode": plan.mode,
            "representation": plan.representation,
            "target_points": plan.target_points,
            "point_count": len(series),
            "is_complete": True,
        },
    }


def _sweden_aggregate_plan(plan: SeriesPlan, date_from: date, date_to: date) -> SeriesPlan:
    if plan.resolved_resolution != "raw":
        return plan
    return replace(
        plan,
        resolved_resolution="hour",
        mode="aggregate",
        estimated_points=bucket_count("hour", date_from, date_to),
        representation="cloud_aggregate_hour",
    )

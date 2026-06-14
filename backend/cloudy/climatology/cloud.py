"""Compute cloud normals for the station nearest a coordinate.

Source of truth is the hourly `cloud_hourly` table, read directly rather than the
serving rollups: a normal is computed rarely and cached for an hour, so clarity
(group the raw hours, average across years) beats shaving milliseconds off a
query that already runs sub-second on a single station's history.

Two products come out of here:
  - the per-period normal series (by calendar month, day-of-year, or year), each
    point a mean plus a p10/p50/p90 spread band across all years;
  - the current-month expectation, which blends the hours observed so far this
    UTC month with the month's climatological tail for the days still to come.

`now` is always passed in, never read from the clock inside these helpers, so
every blend is deterministic and testable. The route passes UTC `now()`.
"""

from __future__ import annotations

import calendar
from datetime import datetime
from typing import Literal

from sqlalchemy import Engine, text
from sqlmodel import Session

from cloudy.climatology.query import ClimatologyCloudQuery, Period
from cloudy.climatology.types import (
    ClimatologyStationMeta,
    CloudClimatologyResponse,
    CloudCurrentMonthExpectation,
    CloudNormalPoint,
)
from cloudy.ingest import stations

# Postgres EXTRACT field per period. "year" yields one point per calendar year
# (year-to-year variation), the other two collapse all years onto a recurring
# slot. doy gives 1-366 so leap-day Feb 29 keeps its own bucket.
_PERIOD_FIELD: dict[Period, str] = {
    "day": "doy",
    "month": "month",
    "year": "year",
}

# One grouped pass over a station's hours. observed_count (NULL cloud_pct rows are
# not-observable codes and carry no count) is the honesty denominator behind each
# slot. We also split the hours into clear / partly cloudy / overcast shares,
# because hourly Swedish cloud is U-shaped — usually near 0% or near 100%, rarely
# in between — so a mean or a percentile band hides the real story. The thresholds
# mirror the okta convention: clear ≲2/8 (<25%), overcast ≳6/8 (>75%), partial the
# middle. The three shares are the percentage of usable hours in each band and sum
# to ~100, which is exactly what a stacked column wants to draw. The mean is still
# computed because the current-month expectation blends on it.
_NORMAL_SQL = """
    SELECT
        {bucket} AS bucket,
        avg(cloud_pct) AS mean_cloud_pct,
        percentile_cont(0.10) WITHIN GROUP (ORDER BY cloud_pct) AS p10,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY cloud_pct) AS p50,
        percentile_cont(0.90) WITHIN GROUP (ORDER BY cloud_pct) AS p90,
        100.0 * count(*) FILTER (WHERE cloud_pct < 25)
            / NULLIF(count(cloud_pct), 0) AS clear_pct,
        100.0 * count(*) FILTER (WHERE cloud_pct >= 25 AND cloud_pct <= 75)
            / NULLIF(count(cloud_pct), 0) AS partial_pct,
        100.0 * count(*) FILTER (WHERE cloud_pct > 75)
            / NULLIF(count(cloud_pct), 0) AS overcast_pct,
        count(cloud_pct)::int AS observed_count,
        count(DISTINCT EXTRACT(YEAR FROM ts_utc))::int AS year_count
    FROM cloud_hourly
    WHERE {station_filter}
    GROUP BY bucket
    ORDER BY bucket
"""

# The month-in-progress pieces. `observed` is the mean of this UTC month's hours
# so far (NULL until the first reading); `tail` is the same calendar month's mean
# across *all* years — the climatological fill for the days not yet elapsed, and
# also the plain baseline. Distinct years let us report how thin the baseline is.
_CURRENT_MONTH_SQL = """
    SELECT
        avg(cloud_pct) FILTER (
            WHERE ts_utc >= :month_start AND ts_utc < :now
        ) AS observed_pct,
        avg(cloud_pct) FILTER (
            WHERE EXTRACT(MONTH FROM ts_utc) = :month
        ) AS baseline_pct,
        count(DISTINCT EXTRACT(YEAR FROM ts_utc)) FILTER (
            WHERE EXTRACT(MONTH FROM ts_utc) = :month
        )::int AS year_count
    FROM cloud_hourly
    WHERE {station_filter}
"""

# A station-set filter: an explicit id list for a located normal (the stations in
# range), or every active station for the Sweden-wide one. A subquery (not a join)
# keeps the row count one-per-hour so the percentile and share maths stay identical
# whether one station or many feed the pool.
_SWEDEN_FILTER = "station_id IN (SELECT id FROM stations WHERE active)"


def compute(
    engine: Engine,
    query: ClimatologyCloudQuery,
    now: datetime,
) -> CloudClimatologyResponse:
    if query.has_location:
        assert query.lat is not None and query.lon is not None
        with Session(engine) as session:
            # Pool the active stations within the radius into one area normal. If
            # none are in range (sparse network), fall back to the single nearest
            # so the chart is never empty — the distance line will say so.
            # (Either raises LookupError when no stations exist → 503.)
            members = stations.active_within_radius(
                session, query.lat, query.lon, float(query.radius_km)
            )
            if not members:
                members = [stations.nearest_active(session, query.lat, query.lon)]
        ids = [s.id for s, _ in members]
        nearest, distance_km = members[0]
        # ids come from our own station table (ints), so inlining them is safe and
        # avoids an expanding-bindparam dance for the IN clause.
        station_filter = f"station_id IN ({', '.join(str(i) for i in ids)})"
        params: dict[str, object] = {}
        station: ClimatologyStationMeta | None = {
            "station_id": nearest.id,
            "name": nearest.name,
            "distance_km": round(distance_km, 1),
        }
        scope: Literal["station", "sweden"] = "station"
        station_count: int | None = len(ids)
    else:
        # No location: pool every active station into one Sweden-wide normal.
        station_filter = _SWEDEN_FILTER
        params = {}
        station = None
        scope = "sweden"
        station_count = _active_station_count(engine)

    series = _normal_series(engine, station_filter, params, query.period)
    current = _current_month(engine, station_filter, params, now)
    overall_years = max((p["year_count"] for p in series), default=0)

    return {
        "scope": scope,
        "station": station,
        "station_count": station_count,
        "period": query.period,
        "series": series,
        "current_month": current,
        "meta": {
            "sources": ["smhi-metobs"],
            "attribution": "Source: SMHI",
            "generated_at": now.isoformat(),
            "year_count": overall_years,
        },
    }


def _active_station_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM stations WHERE active")).scalar_one())


def _normal_series(
    engine: Engine,
    station_filter: str,
    params: dict[str, object],
    period: Period,
) -> list[CloudNormalPoint]:
    bucket = f"EXTRACT({_PERIOD_FIELD[period]} FROM ts_utc)::int"
    sql = text(_NORMAL_SQL.format(bucket=bucket, station_filter=station_filter))
    with engine.connect() as conn:
        rows = conn.execute(sql, params).all()
    return [
        {
            "period": str(row.bucket),
            "mean_cloud_pct": _round(row.mean_cloud_pct),
            "p10_cloud_pct": _round(row.p10),
            "p50_cloud_pct": _round(row.p50),
            "p90_cloud_pct": _round(row.p90),
            "clear_pct": _round(row.clear_pct),
            "partial_pct": _round(row.partial_pct),
            "overcast_pct": _round(row.overcast_pct),
            "observed_count": row.observed_count,
            "year_count": row.year_count,
        }
        for row in rows
    ]


def _current_month(
    engine: Engine,
    station_filter: str,
    params: dict[str, object],
    now: datetime,
) -> CloudCurrentMonthExpectation:
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    # Whole days elapsed before today; today is "still to come" for the tail so a
    # partial day doesn't get double-counted across the observed/tail split.
    observed_days = now.day - 1
    remaining_days = days_in_month - observed_days

    with engine.connect() as conn:
        row = conn.execute(
            text(_CURRENT_MONTH_SQL.format(station_filter=station_filter)),
            {
                **params,
                "month": now.month,
                "month_start": month_start,
                "now": now,
            },
        ).one()

    observed = _round(row.observed_pct)
    baseline = _round(row.baseline_pct)
    expected = _blend(observed, baseline, observed_days, remaining_days, days_in_month)

    return {
        "month": now.month,
        "observed_so_far_pct": observed,
        "observed_days": observed_days,
        "climatology_tail_pct": baseline,
        "expected_pct": expected,
        "baseline_pct": baseline,
    }


def _blend(
    observed: float | None,
    tail: float | None,
    observed_days: int,
    remaining_days: int,
    days_in_month: int,
) -> float | None:
    # Day-weighted average of "what happened" and "what usually happens". If
    # either side is missing (no readings yet, or no climatology for this month)
    # the expectation is just the side we have — never a half-weighted guess.
    if observed is None:
        return tail
    if tail is None:
        return observed
    if days_in_month == 0:
        return tail
    weight = (observed * observed_days + tail * remaining_days) / days_in_month
    return round(weight, 1)


def _round(value: float | None) -> float | None:
    return round(float(value), 1) if value is not None else None

"""Cloud level-of-detail queries over materialized rollups."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, NamedTuple

from sqlalchemy import Engine, text
from sqlalchemy.engine import Row

from cloudy.core.cloud_types import CloudPeriod, Resolution
from cloudy.core.series_plan import SeriesPlan, date_range_bounds, raw_cloud_points
from cloudy.core.series_sql import as_utc, iso, period_key


class CloudRawRow(NamedTuple):
    ts_utc: datetime
    cloud_pct: float | None


class CloudRollupRow(NamedTuple):
    bucket_start: datetime
    bucket_end: datetime
    observed_count: int
    expected_count: int
    missing_count: int
    mean_cloud_pct: float | None
    min_cloud_pct: float | None
    max_cloud_pct: float | None
    p05_cloud_pct: float | None
    p50_cloud_pct: float | None
    p95_cloud_pct: float | None


_RAW_SQL = text(
    """
    SELECT ts_utc, cloud_pct
    FROM cloud_hourly
    WHERE station_id = :station_id
      AND ts_utc >= :ts_from
      AND ts_utc < :ts_to
    ORDER BY ts_utc
    """
)

_ROLLUP_SQL = text(
    """
    SELECT
        bucket_start,
        bucket_end,
        observed_count,
        expected_count,
        missing_count,
        mean_cloud_pct,
        min_cloud_pct,
        max_cloud_pct,
        p05_cloud_pct,
        p50_cloud_pct,
        p95_cloud_pct
    FROM cloud_rollups
    WHERE station_id = :station_id
      AND resolution = :resolution
      AND bucket_end > :ts_from
      AND bucket_start < :ts_to
    ORDER BY bucket_start
    """
)

# The honesty hinge of this query is the expected/missing count. A naive
# `sum(expected_count)` only counts stations that actually produced a rollup row
# for the bucket, so a station that goes dark mid-window (e.g. SMHI stops
# publishing its latest-months rows, as happened to Dravagen) silently drops out
# of the denominator and coverage reads ~100% when stations are in fact missing.
# Instead we fix the denominator to the stations that *participated* anywhere in
# the window — `participating.n` — and expect each of them to cover every hour of
# every bucket. A station present early but absent later then surfaces as missing
# rather than vanishing. We deliberately don't expand to all `active` stations:
# one that never reported in the window (brand-new, or no history yet) would only
# add false pessimism, not visible-and-honest gaps.
_SWEDEN_ROLLUP_SQL = text(
    """
    WITH active_rollups AS (
        SELECT cr.*
        FROM cloud_rollups cr
        JOIN stations s ON s.id = cr.station_id
        WHERE s.active = true
          AND cr.resolution = :resolution
          AND cr.bucket_end > :ts_from
          AND cr.bucket_start < :ts_to
    ),
    participating AS (
        SELECT count(DISTINCT station_id) AS n FROM active_rollups
    )
    SELECT
        ar.bucket_start,
        ar.bucket_end,
        sum(ar.observed_count)::int AS observed_count,
        (p.n * (EXTRACT(EPOCH FROM (ar.bucket_end - ar.bucket_start)) / 3600.0))::int
            AS expected_count,
        GREATEST(
            (p.n * (EXTRACT(EPOCH FROM (ar.bucket_end - ar.bucket_start)) / 3600.0))::int
            - sum(ar.observed_count)::int,
            0
        ) AS missing_count,
        (
            sum(ar.mean_cloud_pct * ar.observed_count)
                FILTER (WHERE ar.mean_cloud_pct IS NOT NULL AND ar.observed_count > 0)
            / NULLIF(
                sum(ar.observed_count)
                    FILTER (WHERE ar.mean_cloud_pct IS NOT NULL AND ar.observed_count > 0),
                0
            )
        ) AS mean_cloud_pct,
        min(ar.min_cloud_pct) FILTER (WHERE ar.min_cloud_pct IS NOT NULL) AS min_cloud_pct,
        max(ar.max_cloud_pct) FILTER (WHERE ar.max_cloud_pct IS NOT NULL) AS max_cloud_pct,
        percentile_cont(0.05) WITHIN GROUP (ORDER BY ar.mean_cloud_pct)
            FILTER (WHERE ar.mean_cloud_pct IS NOT NULL) AS p05_cloud_pct,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY ar.mean_cloud_pct)
            FILTER (WHERE ar.mean_cloud_pct IS NOT NULL) AS p50_cloud_pct,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY ar.mean_cloud_pct)
            FILTER (WHERE ar.mean_cloud_pct IS NOT NULL) AS p95_cloud_pct,
        p.n::int AS station_count
    FROM active_rollups ar
    CROSS JOIN participating p
    GROUP BY ar.bucket_start, ar.bucket_end, p.n
    ORDER BY ar.bucket_start
    """
)


def query_series(
    engine: Engine,
    station_id: int,
    plan: SeriesPlan,
    date_from: date,
    date_to: date,
) -> tuple[list[CloudPeriod], float]:
    ts_from, ts_to = date_range_bounds(date_from, date_to)
    params = {
        "station_id": station_id,
        "ts_from": ts_from,
        "ts_to": ts_to,
        "resolution": plan.resolved_resolution,
    }
    sql = _RAW_SQL if plan.mode == "raw" else _ROLLUP_SQL
    with engine.connect() as conn:
        rows = conn.execute(sql, params).all()

    if plan.mode == "raw":
        points = [_raw_point(_raw_row(row)) for row in rows]
    else:
        points = [_rollup_point(_rollup_row(row), plan.resolved_resolution) for row in rows]
    observed = sum(point["observed_count"] for point in points)
    expected = raw_cloud_points(date_from, date_to)
    coverage = round(observed / expected, 3) if expected else 0.0
    return points, coverage


def query_sweden_series(
    engine: Engine,
    plan: SeriesPlan,
    date_from: date,
    date_to: date,
) -> tuple[list[CloudPeriod], float, int]:
    """Return one cloud series aggregated across active stations."""
    ts_from, ts_to = date_range_bounds(date_from, date_to)
    resolution = "hour" if plan.resolved_resolution == "raw" else plan.resolved_resolution
    with engine.connect() as conn:
        rows = conn.execute(
            _SWEDEN_ROLLUP_SQL,
            {
                "ts_from": ts_from,
                "ts_to": ts_to,
                "resolution": resolution,
            },
        ).all()

    rollup_rows = [_rollup_row(row) for row in rows]
    points = [_rollup_point(row, resolution) for row in rollup_rows]
    observed = sum(point["observed_count"] for point in points)
    expected = sum(point["expected_count"] for point in points)
    coverage = round(observed / expected, 3) if expected else 0.0
    station_count = max((row.station_count for row in rows), default=0)
    return points, coverage, station_count


def _raw_row(row: Row[Any]) -> CloudRawRow:
    return CloudRawRow(ts_utc=row.ts_utc, cloud_pct=row.cloud_pct)


def _rollup_row(row: Row[Any]) -> CloudRollupRow:
    return CloudRollupRow(
        bucket_start=row.bucket_start,
        bucket_end=row.bucket_end,
        observed_count=row.observed_count,
        expected_count=row.expected_count,
        missing_count=row.missing_count,
        mean_cloud_pct=row.mean_cloud_pct,
        min_cloud_pct=row.min_cloud_pct,
        max_cloud_pct=row.max_cloud_pct,
        p05_cloud_pct=row.p05_cloud_pct,
        p50_cloud_pct=row.p50_cloud_pct,
        p95_cloud_pct=row.p95_cloud_pct,
    )


def _raw_point(row: CloudRawRow) -> CloudPeriod:
    ts_utc = as_utc(row.ts_utc)
    cloud_pct = row.cloud_pct
    bucket_end = ts_utc + timedelta(hours=1)
    observed = 1 if cloud_pct is not None else 0
    return {
        "period": period_key(ts_utc, "raw"),
        "bucket_start": iso(ts_utc),
        "bucket_end": iso(bucket_end),
        "mean_cloud_pct": _round(cloud_pct),
        "min_cloud_pct": _round(cloud_pct),
        "max_cloud_pct": _round(cloud_pct),
        "p05_cloud_pct": _round(cloud_pct),
        "p50_cloud_pct": _round(cloud_pct),
        "p95_cloud_pct": _round(cloud_pct),
        "observed_count": observed,
        "expected_count": 1,
        "missing_count": 1 - observed,
    }


def _rollup_point(row: CloudRollupRow, resolution: Resolution) -> CloudPeriod:
    bucket_start = as_utc(row.bucket_start)
    bucket_end = as_utc(row.bucket_end)
    return {
        "period": period_key(bucket_start, resolution),
        "bucket_start": iso(bucket_start),
        "bucket_end": iso(bucket_end),
        "mean_cloud_pct": _round(row.mean_cloud_pct),
        "min_cloud_pct": _round(row.min_cloud_pct),
        "max_cloud_pct": _round(row.max_cloud_pct),
        "p05_cloud_pct": _round(row.p05_cloud_pct),
        "p50_cloud_pct": _round(row.p50_cloud_pct),
        "p95_cloud_pct": _round(row.p95_cloud_pct),
        "observed_count": row.observed_count,
        "expected_count": row.expected_count,
        "missing_count": row.missing_count,
    }


def _round(value: float | None) -> float | None:
    return round(float(value), 1) if value is not None else None

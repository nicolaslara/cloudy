"""Lightning level-of-detail queries over exact raw events."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, NamedTuple

from sqlalchemy import Connection, Engine, text
from sqlalchemy.engine import Row

from cloudy.core.lightning_query import SpatialBounds
from cloudy.core.lightning_types import LightningPeriod, Resolution
from cloudy.core.series_plan import SeriesPlan
from cloudy.core.series_sql import (
    as_utc,
    bucket_end_expr,
    bucket_start_expr,
    haversine_filter_sql,
    iso,
    period_key,
)

# The center-distance filter is identical across the count, raw, and aggregate
# queries, so build it once. Column/param names match this module's _params().
_HAVERSINE = haversine_filter_sql()


class LightningBucketRow(NamedTuple):
    bucket_start: datetime
    bucket_end: datetime
    cg_count: int
    all_count: int
    lightning_days: int
    max_abs_peak_ka: float
    strongest_event_time: datetime | None


_COUNT_SQL = text(
    f"""
    SELECT count(*) AS total
    FROM lightning_events
    WHERE day BETWEEN :date_from AND :date_to
      AND lat BETWEEN :lat_min AND :lat_max
      AND lon BETWEEN :lon_min AND :lon_max
      AND {_HAVERSINE}
    """
)

_RAW_SQL = text(
    f"""
    SELECT
        ts_utc AS bucket_start,
        ts_utc AS bucket_end,
        CASE WHEN cloud_indicator = 0 THEN 1 ELSE 0 END AS cg_count,
        1 AS all_count,
        1 AS lightning_days,
        abs(peak_current_ka) AS max_abs_peak_ka,
        ts_utc AS strongest_event_time
    FROM lightning_events
    WHERE day BETWEEN :date_from AND :date_to
      AND lat BETWEEN :lat_min AND :lat_max
      AND lon BETWEEN :lon_min AND :lon_max
      AND {_HAVERSINE}
    ORDER BY ts_utc, id
    """
)

_SWEDEN_ROLLUP_COUNT_SQL = text(
    """
    SELECT
        count(*)::int AS rollup_days,
        COALESCE(sum(all_count), 0)::int AS total
    FROM lightning_daily_rollups
    WHERE day BETWEEN :date_from AND :date_to
    """
)

_DELETE_SWEDEN_DAILY_ROLLUPS_SQL = text(
    """
    DELETE FROM lightning_daily_rollups
    WHERE day BETWEEN :date_from AND :date_to
    """
)

_INSERT_SWEDEN_DAILY_ROLLUPS_SQL = text(
    """
    INSERT INTO lightning_daily_rollups (
        day,
        bucket_start,
        bucket_end,
        cg_count,
        all_count,
        lightning_days,
        max_abs_peak_ka,
        strongest_event_time,
        source,
        source_version
    )
    SELECT
        day,
        day::timestamp AT TIME ZONE 'UTC' AS bucket_start,
        (day + 1)::timestamp AT TIME ZONE 'UTC' AS bucket_end,
        count(*) FILTER (WHERE cloud_indicator = 0)::int AS cg_count,
        count(*)::int AS all_count,
        1 AS lightning_days,
        max(abs(peak_current_ka)) AS max_abs_peak_ka,
        (array_agg(ts_utc ORDER BY abs(peak_current_ka) DESC, ts_utc))[1]
            AS strongest_event_time,
        source,
        source_version
    FROM lightning_events
    WHERE day BETWEEN :date_from AND :date_to
    GROUP BY day, source, source_version
    ORDER BY day
    """
)


def count_events(
    engine: Engine,
    spatial: SpatialBounds,
    date_from: date,
    date_to: date,
) -> int:
    if spatial.mode == "sweden":
        rollup_count = _count_sweden_rollup_events(engine, date_from, date_to)
        if rollup_count is not None:
            return rollup_count
    with engine.connect() as conn:
        row = conn.execute(_COUNT_SQL, _params(spatial, date_from, date_to)).one()
    return int(row.total)


def query_series(
    engine: Engine,
    spatial: SpatialBounds,
    plan: SeriesPlan,
    date_from: date,
    date_to: date,
) -> list[LightningPeriod]:
    if spatial.mode == "sweden" and plan.resolved_resolution in ("day", "week", "month", "year"):
        rollup_rows = _query_sweden_rollup_series(
            engine,
            plan.resolved_resolution,
            date_from,
            date_to,
        )
        if rollup_rows is not None:
            return [_point(row, plan.resolved_resolution) for row in rollup_rows]
    params = _params(spatial, date_from, date_to)
    sql = _RAW_SQL if plan.mode == "raw" else text(_aggregate_sql(plan.resolved_resolution))
    with engine.connect() as conn:
        rows = conn.execute(sql, params).all()
    return [_point(_bucket_row(row), plan.resolved_resolution) for row in rows]


def refresh_sweden_daily_rollups(conn: Connection, date_from: date, date_to: date) -> None:
    """Refresh Sweden-wide daily serving rollups after lightning ingest."""
    conn.execute(_DELETE_SWEDEN_DAILY_ROLLUPS_SQL, {"date_from": date_from, "date_to": date_to})
    conn.execute(_INSERT_SWEDEN_DAILY_ROLLUPS_SQL, {"date_from": date_from, "date_to": date_to})


def _count_sweden_rollup_events(engine: Engine, date_from: date, date_to: date) -> int | None:
    with engine.connect() as conn:
        row = conn.execute(
            _SWEDEN_ROLLUP_COUNT_SQL,
            {"date_from": date_from, "date_to": date_to},
        ).one()
    return int(row.total) if int(row.rollup_days) > 0 else None


def _query_sweden_rollup_series(
    engine: Engine,
    resolution: Resolution,
    date_from: date,
    date_to: date,
) -> list[LightningBucketRow] | None:
    sql = text(_sweden_rollup_aggregate_sql(resolution))
    with engine.connect() as conn:
        rows = conn.execute(sql, {"date_from": date_from, "date_to": date_to}).all()
    return [_bucket_row(row) for row in rows] if rows else None


def _params(spatial: SpatialBounds, date_from: date, date_to: date) -> dict[str, object]:
    return {
        "date_from": date_from,
        "date_to": date_to,
        "lat_min": spatial.min_lat,
        "lat_max": spatial.max_lat,
        "lon_min": spatial.min_lon,
        "lon_max": spatial.max_lon,
        "use_radius": spatial.use_radius,
        "lat": spatial.center_lat if spatial.use_radius else 0.0,
        "lon": spatial.center_lon if spatial.use_radius else 0.0,
        "radius_km": spatial.radius_km if spatial.use_radius else 0.0,
    }


def _aggregate_sql(resolution: Resolution) -> str:
    bucket_start = bucket_start_expr(resolution)
    bucket_end = bucket_end_expr(resolution, "bucket_start")
    return f"""
        WITH filtered AS (
            SELECT
                ts_utc,
                day,
                peak_current_ka,
                cloud_indicator,
                {bucket_start} AS bucket_start
            FROM lightning_events
            WHERE day BETWEEN :date_from AND :date_to
              AND lat BETWEEN :lat_min AND :lat_max
              AND lon BETWEEN :lon_min AND :lon_max
              AND {_HAVERSINE}
        ),
        bucketed AS (
            SELECT *, {bucket_end} AS bucket_end
            FROM filtered
        )
        SELECT
            bucket_start,
            bucket_end,
            count(*) FILTER (WHERE cloud_indicator = 0)::int AS cg_count,
            count(*)::int AS all_count,
            count(DISTINCT day)::int AS lightning_days,
            max(abs(peak_current_ka)) AS max_abs_peak_ka,
            (array_agg(ts_utc ORDER BY abs(peak_current_ka) DESC, ts_utc))[1]
                AS strongest_event_time
        FROM bucketed
        GROUP BY bucket_start, bucket_end
        ORDER BY bucket_start
    """


def _sweden_rollup_aggregate_sql(resolution: Resolution) -> str:
    bucket_start = _sweden_rollup_bucket_start_expr(resolution)
    bucket_end = bucket_end_expr(resolution, "bucket_start")
    return f"""
        WITH bucketed AS (
            SELECT
                day,
                cg_count,
                all_count,
                lightning_days,
                max_abs_peak_ka,
                strongest_event_time,
                {bucket_start} AS bucket_start
            FROM lightning_daily_rollups
            WHERE day BETWEEN :date_from AND :date_to
        ),
        with_end AS (
            SELECT *, {bucket_end} AS bucket_end
            FROM bucketed
        )
        SELECT
            bucket_start,
            bucket_end,
            sum(cg_count)::int AS cg_count,
            sum(all_count)::int AS all_count,
            sum(lightning_days)::int AS lightning_days,
            max(max_abs_peak_ka) AS max_abs_peak_ka,
            (array_agg(
                strongest_event_time
                ORDER BY max_abs_peak_ka DESC NULLS LAST, strongest_event_time
            ))[1] AS strongest_event_time
        FROM with_end
        GROUP BY bucket_start, bucket_end
        ORDER BY bucket_start
    """


def _sweden_rollup_bucket_start_expr(resolution: Resolution) -> str:
    # Distinct from series_sql.bucket_start_expr: we re-aggregate the daily rollup
    # table, so the source column is already-day-aligned `bucket_start`, not
    # `ts_utc`. "day" is therefore a no-op; coarser buckets truncate in UTC.
    if resolution == "day":
        return "bucket_start"
    if resolution in ("week", "month", "year"):
        return f"date_trunc('{resolution}', bucket_start AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"
    raise ValueError(f"Sweden lightning rollup SQL is not defined for {resolution!r}")


def _bucket_row(row: Row[Any]) -> LightningBucketRow:
    return LightningBucketRow(
        bucket_start=row.bucket_start,
        bucket_end=row.bucket_end,
        cg_count=row.cg_count,
        all_count=row.all_count,
        lightning_days=row.lightning_days,
        max_abs_peak_ka=float(row.max_abs_peak_ka or 0.0),
        strongest_event_time=row.strongest_event_time,
    )


def _point(row: LightningBucketRow, resolution: Resolution) -> LightningPeriod:
    start = as_utc(row.bucket_start)
    end = as_utc(row.bucket_end)
    strongest = row.strongest_event_time
    return {
        "period": period_key(start, resolution),
        "bucket_start": iso(start),
        "bucket_end": iso(end),
        "cg_count": row.cg_count,
        "all_count": row.all_count,
        "lightning_days": row.lightning_days,
        "max_abs_peak_ka": float(row.max_abs_peak_ka),
        "strongest_event_time": iso(strongest) if strongest is not None else None,
    }

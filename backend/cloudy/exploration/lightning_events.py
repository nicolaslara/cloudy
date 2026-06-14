"""Strokes presentation: individual events in a spatial window."""

from datetime import date

from sqlalchemy import Engine, text

from cloudy.core.series_sql import haversine_filter_sql
from cloudy.core.spatial import SpatialBounds
from cloudy.exploration.lightning_limits import DEFAULT_MAP_STROKE_POINTS, MAX_MAP_STROKE_POINTS
from cloudy.exploration.lightning_types import StrokeColumn, StrokesQueryResult
from cloudy.exploration.series_plan import MAX_LIGHTNING_SCAN_EVENTS, QueryRejected

COLUMNS: tuple[StrokeColumn, ...] = ("lon", "lat", "peak_ka", "cg", "ts")

# Shared bbox + center-distance filter for the strokes window. The center-distance
# half comes from the one haversine helper; the bbox prefilter is cheap and lets
# Postgres use the lat/lon index before the trig runs.
_FILTER_CLAUSE = f"""
    FROM lightning_events
    WHERE day BETWEEN :date_from AND :date_to
      AND lon BETWEEN :min_lon AND :max_lon
      AND lat BETWEEN :min_lat AND :max_lat
      AND {haversine_filter_sql()}
"""

_RAW_SQL = text(
    f"""
    SELECT lon, lat, peak_current_ka, cloud_indicator, ts_utc
    {_FILTER_CLAUSE}
    ORDER BY ts_utc, id
    LIMIT :limit
    """
)

_PRIORITY_SAMPLE_SQL = text(
    f"""
    WITH filtered AS (
        SELECT id, lon, lat, peak_current_ka, cloud_indicator, ts_utc
        {_FILTER_CLAUSE}
    ),
    ranked AS (
        SELECT
            *,
            row_number() OVER (
                ORDER BY
                    CASE WHEN cloud_indicator = 0 THEN 0 ELSE 1 END,
                    abs(peak_current_ka) DESC NULLS LAST,
                    ts_utc,
                    id
            ) AS priority_rank
        FROM filtered
    )
    SELECT lon, lat, peak_current_ka, cloud_indicator, ts_utc
    FROM ranked
    WHERE priority_rank <= :limit
    ORDER BY ts_utc, id
    LIMIT :limit
    """
)

_COUNT_SQL = text(
    f"""
    SELECT count(*) AS total
    {_FILTER_CLAUSE}
    """
)


def query_events(
    engine: Engine,
    date_from: date,
    date_to: date,
    spatial: SpatialBounds,
    limit: int = DEFAULT_MAP_STROKE_POINTS,
) -> StrokesQueryResult:
    """Return compact event rows for format=strokes."""
    if limit < 1 or limit > MAX_MAP_STROKE_POINTS:
        raise ValueError(f"limit must be 1..{MAX_MAP_STROKE_POINTS}")
    if spatial.min_lon >= spatial.max_lon or spatial.min_lat >= spatial.max_lat:
        raise ValueError("spatial bounds must have min < max on both axes")
    params = {
        "date_from": date_from,
        "date_to": date_to,
        "min_lon": spatial.min_lon,
        "min_lat": spatial.min_lat,
        "max_lon": spatial.max_lon,
        "max_lat": spatial.max_lat,
        "limit": limit,
        "use_radius": spatial.use_radius,
        "lat": spatial.center_lat if spatial.use_radius else 0.0,
        "lon": spatial.center_lon if spatial.use_radius else 0.0,
        "radius_km": spatial.radius_km if spatial.use_radius else 0.0,
    }
    with engine.connect() as conn:
        total = int(conn.execute(_COUNT_SQL, params).one().total)
        if total > MAX_LIGHTNING_SCAN_EVENTS:
            raise QueryRejected(
                "too_many_events_to_scan",
                "Lightning strokes query would scan too many matched events.",
                total,
                MAX_LIGHTNING_SCAN_EVENTS,
                "month",
            )
        sql = _RAW_SQL if total <= limit else _PRIORITY_SAMPLE_SQL
        rows = conn.execute(sql, params).all()
    returned = len(rows)
    compact = [
        [
            float(row.lon),
            float(row.lat),
            float(row.peak_current_ka),
            1 if row.cloud_indicator == 0 else 0,
            int(row.ts_utc.timestamp()),
        ]
        for row in rows
    ]
    sampled = total > returned
    return {
        "columns": list(COLUMNS),
        "rows": compact,
        "meta": {
            "from": date_from.isoformat(),
            "to": date_to.isoformat(),
            "total_matched": total,
            "returned": returned,
            "downsampled": sampled,
            "stride": None,
            "sample_method": "priority_abs_peak" if sampled else None,
            "dropped_count": total - returned,
            "representation": "priority_sampled_strokes" if sampled else "raw_strokes",
            "is_complete": not sampled,
        },
    }

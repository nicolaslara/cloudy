"""Shared SQL fragments for the cloud and lightning level-of-detail series.

The cloud and lightning read paths grew up independently but converged on the
same handful of SQL idioms: a great-circle radius filter, the resolution ->
period-label mapping, and the 6h/calendar bucket boundary expressions. Keeping
three copies in sync by hand was a standing bug magnet, so the single source of
truth lives here. The Python great-circle distance stays in core/geo.py; this
module is only its SQL twin plus the bucketing helpers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

# Resolution is spelled differently in cloud_types vs lightning_types but the
# string values are identical, so this module works against the bare label.
ResolutionLabel = Literal["raw", "hour", "6h", "day", "week", "month", "year"]

# The radius of the Earth used by both the SQL and the Python haversine. Keeping
# the constant beside its SQL use makes it obvious the two implementations agree.
EARTH_RADIUS_KM = 6371.0


def haversine_filter_sql(
    *,
    lat_col: str = "lat",
    lon_col: str = "lon",
    use_radius_param: str = "use_radius",
    lat_param: str = "lat",
    lon_param: str = "lon",
    radius_param: str = "radius_km",
) -> str:
    """Return a boolean SQL fragment: row is within `radius_param` km of center.

    This is the haversine great-circle distance, written so the bind parameters
    stay parameters — callers must never interpolate coordinates into SQL, both
    to dodge injection and to let Postgres reuse the plan across calls. The
    `:use_radius` short-circuit lets a bbox-only query skip the trig entirely;
    when it is false the center/radius params are passed as harmless zeros.

    Param names are configurable because the strokes path binds `:min_lon` etc.
    for its bbox but still uses `:lat`/`:lon`/`:radius_km` for the center, while
    everyone shares the same center-distance shape. The defaults match the two
    series callers; only the column names ever differ in practice.
    """
    return f"""(
          :{use_radius_param} = false
          OR 2 * {EARTH_RADIUS_KM} * asin(sqrt(
                  power(sin(radians({lat_col} - :{lat_param}) / 2), 2)
                  + cos(radians(:{lat_param})) * cos(radians({lat_col}))
                    * power(sin(radians({lon_col} - :{lon_param}) / 2), 2)
              )) <= :{radius_param}
          )"""


def bucket_start_expr(resolution: ResolutionLabel, ts_col: str = "ts_utc") -> str:
    """SQL that snaps a timestamp down to the start of its bucket.

    6h buckets are anchored on the Unix epoch via date_bin so they tile cleanly
    regardless of the query window; calendar buckets use date_trunc in UTC so a
    "month" means a real calendar month, not a rolling 30-day span.
    """
    if resolution == "6h":
        return f"date_bin(INTERVAL '6 hours', {ts_col}, TIMESTAMPTZ '1970-01-01 00:00:00+00')"
    if resolution in ("hour", "day", "week", "month", "year"):
        return f"date_trunc('{resolution}', {ts_col} AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"
    raise ValueError(f"bucket SQL is not defined for {resolution!r}")


def bucket_end_expr(resolution: ResolutionLabel, start_name: str) -> str:
    """Bucket end as start + one interval. INTERVAL arithmetic keeps month/year
    boundaries calendar-correct (e.g. Feb is 28/29 days) instead of fixed-width."""
    interval = {
        "hour": "1 hour",
        "6h": "6 hours",
        "day": "1 day",
        "week": "1 week",
        "month": "1 month",
        "year": "1 year",
    }[resolution]
    return f"{start_name} + INTERVAL '{interval}'"


def period_key(value: datetime, resolution: ResolutionLabel) -> str:
    """Human/stable label for a bucket, granular enough to be unique per period.

    Sub-day resolutions need the full instant; day/week collapse to a date;
    month and year drop to their coarse strftime forms. The frontend keys series
    points on this string, so the shape per resolution is part of the contract.
    """
    if resolution in ("raw", "hour", "6h"):
        return iso(value)
    if resolution in ("day", "week"):
        return value.date().isoformat()
    if resolution == "month":
        return value.strftime("%Y-%m")
    return value.strftime("%Y")


def as_utc(value: datetime) -> datetime:
    """Naive timestamps from the DB are UTC by construction; tag or convert them
    so downstream ISO formatting is unambiguous."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def iso(value: datetime) -> str:
    """UTC ISO-8601 with a trailing Z, the wire format the API and tests expect."""
    return as_utc(value).isoformat().replace("+00:00", "Z")

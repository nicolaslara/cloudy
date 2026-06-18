"""Compute lightning normals for a coordinate within a radius, or all of Sweden.

Lightning is never modelled at a point — a strike lands in an *area* — so a
located query carries a radius (10 or 25 km), and the Sweden-wide view is just the
whole-country bounding box with the radius refinement switched off. Either way we
count discharges straight from `lightning_events` using the same
bbox-prefilter-then-exact-haversine pattern as the exploration raw path; the
shared filter SQL lives in core.series_sql so the radius geometry can never drift
between the two readers.

The unit of the climatology is the **lightning day**: a calendar day with at
least one discharge in scope. That mirrors SMHI's thunder-day maps and keeps the
headline metric robust to the wild per-storm variance in raw counts.

  strike_day_probability[slot] = lightning-days in slot / observed days in slot
  expected_lightning_days[slot] = lightning-days / occurrences of the slot

The denominator — "observed days" — is the number of real calendar days that
fall in the slot across the span we actually hold data for. We derive that span
from the filtered events themselves (min/max day), so a probability is always
days-with-strikes over days-we-could-have-seen-strikes, never inflated by
pretending we have coverage we don't.

Performance note: the Sweden-wide query scans the whole event archive, the one
slow read here (a few seconds cold). We deliberately keep it a live scan behind
the route's one-hour response cache rather than precomputing it. An earlier
revision added a materialized `lightning_normals` table (refreshed on ingest, the
twin of `cloud_normals`); it worked, but it cost a table, a migration, a refresh
step and a second read path to shave ~10ms off an already-cached request — too
much machinery for too little. If cold-cache latency ever bites, the cheaper next
step is to warm (or invalidate) the cache right after each ingest; only if that
isn't enough should the precomputed table come back. Cloud makes the opposite call
(it does materialize its Sweden normal) for reasons that don't apply here: its
percentile scan runs ~6s/period over ~10M hourly rows, it's paid once *per period*,
and it backs the default landing view where a cold first paint is unacceptable.
Lightning's Sweden scan is ~2s over ~4M events on a secondary view — well inside
what the response cache absorbs. The `lightning_daily_rollups` table stays purely
an exploration serving concern; the normals path no longer reads it.

`now` is passed in (UTC at the route) so the current-month blend is testable.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Literal

from sqlalchemy import Engine, text

from cloudy.climatology.query import ClimatologyLightningQuery, Period
from cloudy.climatology.types import (
    LightningClimatologyResponse,
    LightningCurrentMonthExpectation,
    LightningNormalPoint,
)
from cloudy.core.series_sql import haversine_filter_sql
from cloudy.core.spatial import SpatialBounds

_HAVERSINE = haversine_filter_sql()

# Per-(year, slot) lightning-days and discharge counts inside the radius. We
# aggregate to (year, slot) first so a "lightning day" is one distinct calendar
# day, then average across years in Python where the calendar arithmetic for the
# denominator lives. The bbox columns let the lat/lon index prune before the trig.
_SLOT_SQL = """
    WITH filtered AS (
        SELECT day
        FROM lightning_events
        WHERE lat BETWEEN :lat_min AND :lat_max
          AND lon BETWEEN :lon_min AND :lon_max
          AND {haversine}
    )
    SELECT
        EXTRACT(YEAR FROM day)::int AS year,
        {bucket} AS bucket,
        count(DISTINCT day)::int AS lightning_days,
        count(*)::int AS strike_count
    FROM filtered
    GROUP BY year, bucket
    ORDER BY bucket, year
"""

# Bounds of the observed window for the radius, used to size the denominators.
_SPAN_SQL = """
    SELECT min(day) AS first_day, max(day) AS last_day
    FROM lightning_events
    WHERE lat BETWEEN :lat_min AND :lat_max
      AND lon BETWEEN :lon_min AND :lon_max
      AND {haversine}
"""

# This month so far: distinct lightning-days observed in the current UTC month.
_CURRENT_MONTH_SQL = """
    SELECT count(DISTINCT day)::int AS lightning_days
    FROM lightning_events
    WHERE day >= :month_start AND day < :today
      AND lat BETWEEN :lat_min AND :lat_max
      AND lon BETWEEN :lon_min AND :lon_max
      AND {haversine}
"""

_PERIOD_BUCKET: dict[Period, str] = {
    "day": "EXTRACT(DOY FROM day)::int",
    "month": "EXTRACT(MONTH FROM day)::int",
    "year": "EXTRACT(YEAR FROM day)::int",
}


def compute(
    engine: Engine,
    query: ClimatologyLightningQuery,
    now: datetime,
) -> LightningClimatologyResponse:
    if query.has_location:
        assert query.lat is not None and query.lon is not None
        # A point+radius normal: the exact circle around the place.
        bounds = SpatialBounds.from_radius(query.lat, query.lon, float(query.radius_km))
        scope: Literal["radius", "sweden"] = "radius"
        lat: float | None = query.lat
        lon: float | None = query.lon
        radius_km: int | None = query.radius_km
    else:
        # No location: all of Sweden. The Sweden bbox with no radius makes the
        # haversine clause short-circuit (use_radius = false), so every event in
        # the country counts — the radius is irrelevant and reported as null. This
        # is the slow read (a full-archive scan) but the route caches it for an
        # hour; see the module docstring for why we don't precompute it.
        bounds = SpatialBounds.sweden()
        scope = "sweden"
        lat = lon = None
        radius_km = None

    params = _bbox_params(bounds)

    first_day, last_day = _observed_span(engine, params)
    series = _normal_series(engine, params, query.period, first_day, last_day)
    current = _current_month(engine, params, now, first_day, last_day)
    overall_years = max((p["year_count"] for p in series), default=0)

    return {
        "scope": scope,
        "lat": lat,
        "lon": lon,
        "radius_km": radius_km,
        "period": query.period,
        "series": series,
        "current_month": current,
        "meta": {
            "sources": ["smhi-lightning"],
            "attribution": "Source: SMHI",
            "generated_at": now.isoformat(),
            "year_count": overall_years,
        },
    }


def _normal_series(
    engine: Engine,
    params: dict[str, object],
    period: Period,
    first_day: date | None,
    last_day: date | None,
) -> list[LightningNormalPoint]:
    sql = text(_SLOT_SQL.format(haversine=_HAVERSINE, bucket=_PERIOD_BUCKET[period]))
    with engine.connect() as conn:
        rows = conn.execute(sql, params).all()
    if not rows or first_day is None or last_day is None:
        return []

    # Fold the per-(year, slot) rows into per-slot aggregates. Keeping the year
    # set per slot lets us average lightning-days per *occurrence* of the slot
    # (e.g. per July that actually happened) rather than per calendar year.
    by_slot: dict[int, dict[str, object]] = {}
    for row in rows:
        slot = by_slot.setdefault(
            row.bucket,
            {"days": 0, "strikes": 0, "years": set()},
        )
        slot["days"] = int(slot["days"]) + row.lightning_days  # type: ignore[call-overload]
        slot["strikes"] = int(slot["strikes"]) + row.strike_count  # type: ignore[call-overload]
        years = slot["years"]
        assert isinstance(years, set)
        years.add(row.year)

    points: list[LightningNormalPoint] = []
    for bucket in sorted(by_slot):
        slot = by_slot[bucket]
        days = int(slot["days"])  # type: ignore[call-overload]
        strikes = int(slot["strikes"])  # type: ignore[call-overload]
        years = slot["years"]
        assert isinstance(years, set)
        occurrences = len(years)
        observed_days = _observed_days_for_slot(period, bucket, first_day, last_day)
        points.append(
            {
                "period": str(bucket),
                "strike_day_probability": _ratio(days, observed_days),
                "expected_lightning_days": _ratio(days, occurrences),
                "mean_count": _ratio(strikes, occurrences),
                "year_count": occurrences,
            }
        )
    return points


def _current_month(
    engine: Engine,
    params: dict[str, object],
    now: datetime,
    first_day: date | None,
    last_day: date | None,
) -> LightningCurrentMonthExpectation:
    month_start = now.date().replace(day=1)
    today = now.date()
    observed_days = today.day - 1
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    remaining_days = days_in_month - observed_days

    with engine.connect() as conn:
        row = conn.execute(
            text(_CURRENT_MONTH_SQL.format(haversine=_HAVERSINE)),
            {**params, "month_start": month_start, "today": today},
        ).one()
    observed = int(row.lightning_days)

    # The month's climatological lightning-day rate (per day), turned into an
    # expectation for the days still to come. baseline_days is the same rate over
    # a whole month — what you'd expect for this month with no observations yet.
    rate = _month_day_rate(engine, params, now.month, first_day, last_day)
    tail = round(rate * remaining_days, 2) if rate is not None else None
    baseline = round(rate * days_in_month, 2) if rate is not None else None
    expected = round(observed + tail, 2) if tail is not None else float(observed)

    return {
        "month": now.month,
        "observed_lightning_days": observed,
        "observed_days": observed_days,
        "climatology_tail_days": tail,
        "expected_lightning_days": expected,
        "baseline_days": baseline,
    }


def _month_day_rate(
    engine: Engine,
    params: dict[str, object],
    month: int,
    first_day: date | None,
    last_day: date | None,
) -> float | None:
    """Lightning-days-per-day for a calendar month across the observed span."""
    if first_day is None or last_day is None:
        return None
    sql = text(_SLOT_SQL.format(haversine=_HAVERSINE, bucket="EXTRACT(MONTH FROM day)::int"))
    with engine.connect() as conn:
        rows = conn.execute(sql, params).all()
    total_days = sum(int(row.lightning_days) for row in rows if row.bucket == month)
    observed_days = _observed_days_for_slot("month", month, first_day, last_day)
    if observed_days == 0:
        return None
    return total_days / observed_days


def _observed_span(
    engine: Engine,
    params: dict[str, object],
) -> tuple[date | None, date | None]:
    with engine.connect() as conn:
        row = conn.execute(text(_SPAN_SQL.format(haversine=_HAVERSINE)), params).one()
    return row.first_day, row.last_day


def _observed_days_for_slot(
    period: Period,
    bucket: int,
    first_day: date,
    last_day: date,
) -> int:
    """Real calendar days falling in `bucket` between first_day and last_day.

    This is the honest denominator: the count of days we could have seen a strike
    on. For "year" the slot *is* a year, so the denominator is that year's days
    clipped to the observed span; for month/day-of-year we sweep the span and tally
    matching days. The span is small (a decade of lightning history at most), so a
    day-by-day sweep is clearer than calendar arithmetic and plenty fast.
    """
    matched = 0
    cursor = first_day
    one_day = timedelta(days=1)
    while cursor <= last_day:
        if _bucket_of(period, cursor) == bucket:
            matched += 1
        cursor += one_day
    return matched


def _bucket_of(period: Period, day: date) -> int:
    if period == "day":
        return day.timetuple().tm_yday
    if period == "month":
        return day.month
    return day.year


def _bbox_params(bounds: SpatialBounds) -> dict[str, object]:
    # Radius mode binds the exact circle; Sweden mode leaves use_radius false so
    # the haversine clause passes everything inside the (country-sized) bbox. The
    # center/radius binds are harmless zeros when unused.
    return {
        "lat_min": bounds.min_lat,
        "lat_max": bounds.max_lat,
        "lon_min": bounds.min_lon,
        "lon_max": bounds.max_lon,
        "use_radius": bounds.use_radius,
        "lat": bounds.center_lat if bounds.use_radius else 0.0,
        "lon": bounds.center_lon if bounds.use_radius else 0.0,
        "radius_km": bounds.radius_km if bounds.use_radius else 0.0,
    }


def _ratio(numerator: float, denominator: float) -> float | None:
    if not denominator:
        return None
    return round(numerator / denominator, 3)

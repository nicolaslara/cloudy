"""Truth test for the radius/period aggregation SQL against the isolated
test database (see conftest.py). Radius SQL is never trusted off Postgres."""

from datetime import UTC, date, datetime
from math import asin, cos, degrees, radians, sin

import pytest
from sqlalchemy import Engine, delete
from sqlmodel import Session

from cloudy.core.lightning_query import SpatialBounds
from cloudy.core.lightning_series import count_events, query_series, refresh_sweden_daily_rollups
from cloudy.core.series_plan import plan_series
from cloudy.db.models import LightningEvent


def _radius(lat: float, lon: float, radius_km: float) -> SpatialBounds:
    return SpatialBounds.from_radius(lat, lon, radius_km)


LAT, LON = 59.0, 17.0
KM_PER_DEG_LAT = 111.32
FROM, TO = date(2030, 1, 1), date(2031, 12, 31)


def _event(day: date, lat: float, lon: float, peak_ka: float, cloud: int) -> LightningEvent:
    return LightningEvent(
        ts_utc=datetime(day.year, day.month, day.day, 12, tzinfo=UTC),
        day=day,
        lat=lat,
        lon=lon,
        peak_current_ka=peak_ka,
        multiplicity=1,
        number_of_sensors=4,
        cloud_indicator=cloud,
    )


@pytest.fixture
def engine(db: Engine) -> Engine:
    # ~9.5 km NE diagonally: inside the bbox prefilter but ~13.4 km away —
    # proves the haversine cut, not just the bbox.
    diag_lat = LAT + 9.5 / KM_PER_DEG_LAT
    diag_lon = LON + 9.5 / (KM_PER_DEG_LAT * cos(radians(LAT)))
    events = [
        _event(date(2030, 7, 1), LAT, LON, -110.2, cloud=0),  # CG, big negative peak
        _event(date(2030, 7, 1), LAT + 0.01, LON, 30.0, cloud=1),  # IC, ~1.1 km away
        _event(date(2030, 7, 2), LAT, LON, 50.0, cloud=0),  # CG, second day
        _event(date(2030, 8, 15), LAT, LON - 0.01, -5.0, cloud=1),  # IC, next month
        _event(date(2030, 7, 1), diag_lat, diag_lon, 200.0, cloud=0),  # outside 10 km
    ]
    with Session(db) as session:
        session.add_all(events)
        session.commit()
    with db.begin() as conn:
        refresh_sweden_daily_rollups(conn, FROM, TO)
    return db


def test_month_granularity_radius_10(engine: Engine) -> None:
    spatial = _radius(LAT, LON, 10)
    event_count = count_events(engine, spatial, FROM, TO)
    plan = plan_series(
        "lightning",
        FROM,
        TO,
        "month",
        lightning_event_count=event_count,
    )
    series = query_series(engine, spatial, plan, FROM, TO)
    assert series == [
        {
            "period": "2030-07",
            "bucket_start": "2030-07-01T00:00:00Z",
            "bucket_end": "2030-08-01T00:00:00Z",
            "cg_count": 2,
            "all_count": 3,
            "lightning_days": 2,
            "max_abs_peak_ka": 110.2,
            "strongest_event_time": "2030-07-01T12:00:00Z",
        },
        {
            "period": "2030-08",
            "bucket_start": "2030-08-01T00:00:00Z",
            "bucket_end": "2030-09-01T00:00:00Z",
            "cg_count": 0,
            "all_count": 1,
            "lightning_days": 1,
            "max_abs_peak_ka": 5.0,
            "strongest_event_time": "2030-08-15T12:00:00Z",
        },
    ]


def test_sweden_aggregate_uses_daily_rollup(engine: Engine) -> None:
    spatial = SpatialBounds.sweden()
    with engine.begin() as conn:
        conn.execute(delete(LightningEvent))

    event_count = count_events(engine, spatial, FROM, TO)
    plan = plan_series(
        "lightning",
        FROM,
        TO,
        "year",
        lightning_event_count=event_count,
    )
    series = query_series(engine, spatial, plan, FROM, TO)

    assert event_count == 5
    assert series == [
        {
            "period": "2030",
            "bucket_start": "2030-01-01T00:00:00Z",
            "bucket_end": "2031-01-01T00:00:00Z",
            "cg_count": 3,
            "all_count": 5,
            "lightning_days": 3,
            "max_abs_peak_ka": 200.0,
            "strongest_event_time": "2030-07-01T12:00:00Z",
        },
    ]


def test_day_granularity_radius_10(engine: Engine) -> None:
    spatial = _radius(LAT, LON, 10)
    plan = plan_series(
        "lightning", FROM, TO, "day", lightning_event_count=count_events(engine, spatial, FROM, TO)
    )
    series = query_series(engine, spatial, plan, FROM, TO)
    assert [row["period"] for row in series] == ["2030-07-01", "2030-07-02", "2030-08-15"]
    assert series[0]["cg_count"] == 1
    assert series[0]["all_count"] == 2
    assert series[0]["lightning_days"] == 1
    assert series[0]["max_abs_peak_ka"] == 110.2
    assert series[1]["max_abs_peak_ka"] == 50.0
    assert all(row["lightning_days"] == 1 for row in series)


def test_year_granularity_radius_10(engine: Engine) -> None:
    spatial = _radius(LAT, LON, 10)
    plan = plan_series(
        "lightning", FROM, TO, "year", lightning_event_count=count_events(engine, spatial, FROM, TO)
    )
    series = query_series(engine, spatial, plan, FROM, TO)
    assert len(series) == 1
    assert series[0]["period"] == "2030"
    assert series[0]["cg_count"] == 2
    assert series[0]["all_count"] == 4
    assert series[0]["lightning_days"] == 3
    assert series[0]["max_abs_peak_ka"] == 110.2


def test_radius_25_includes_the_diagonal_outlier(engine: Engine) -> None:
    spatial = _radius(LAT, LON, 25)
    plan = plan_series(
        "lightning", FROM, TO, "year", lightning_event_count=count_events(engine, spatial, FROM, TO)
    )
    series = query_series(engine, spatial, plan, FROM, TO)
    assert series[0]["cg_count"] == 3
    assert series[0]["all_count"] == 5
    assert series[0]["lightning_days"] == 3
    assert series[0]["max_abs_peak_ka"] == 200.0


def test_date_window_filters(engine: Engine) -> None:
    spatial = _radius(LAT, LON, 10)
    plan = plan_series(
        "lightning",
        date(2030, 7, 1),
        date(2030, 7, 31),
        "month",
        lightning_event_count=count_events(engine, spatial, date(2030, 7, 1), date(2030, 7, 31)),
    )
    series = query_series(engine, spatial, plan, date(2030, 7, 1), date(2030, 7, 31))
    assert [row["period"] for row in series] == ["2030-07"]


def test_empty_window_returns_empty_series(engine: Engine) -> None:
    spatial = _radius(LAT, LON, 10)
    plan = plan_series(
        "lightning",
        date(2031, 1, 1),
        TO,
        "month",
        lightning_event_count=count_events(engine, spatial, date(2031, 1, 1), TO),
    )
    assert query_series(engine, spatial, plan, date(2031, 1, 1), TO) == []


def test_bbox_prefilter_keeps_point_at_radius_due_east(engine: Engine) -> None:
    # 5 m inside the 10 km circle, due east: lands in the ~11 m sliver a
    # too-narrow bbox prefilter (111.32 km/deg vs the haversine's R=6371)
    # used to clip. Locks in: bbox must be a superset of the circle.
    dist_km = 9.995
    dlon = degrees(2 * asin(sin(dist_km / (2 * 6371.0)) / cos(radians(LAT))))
    with Session(engine) as session:
        session.add(_event(date(2031, 6, 1), LAT, LON + dlon, 75.0, cloud=0))
        session.commit()
    spatial = _radius(LAT, LON, 10)
    plan = plan_series(
        "lightning",
        date(2031, 1, 1),
        date(2031, 12, 31),
        "day",
        lightning_event_count=count_events(engine, spatial, date(2031, 1, 1), date(2031, 12, 31)),
    )
    series = query_series(engine, spatial, plan, date(2031, 1, 1), date(2031, 12, 31))
    assert len(series) == 1
    assert series[0]["period"] == "2031-06-01"
    assert series[0]["cg_count"] == 1

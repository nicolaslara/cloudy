"""Truth test for cloud period aggregation SQL against the isolated test database."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select

from cloudy.core.cloud_series import query_series, query_sweden_series
from cloudy.core.series_plan import plan_series
from cloudy.db.models import CloudHourly, Station
from cloudy.ingest.cloud import refresh_rollups

FROM, TO = date(2030, 1, 1), date(2030, 12, 31)
STATION_ID = 98040


@pytest.fixture
def engine(stations_sample: Engine) -> Engine:
    with Session(stations_sample) as session:
        session.add_all(
            [
                CloudHourly(
                    station_id=STATION_ID,
                    ts_utc=datetime(2030, 7, 1, h, tzinfo=UTC),
                    cloud_pct=50.0 if h < 12 else None,
                )
                for h in range(24)
            ]
            + [
                CloudHourly(
                    station_id=STATION_ID,
                    ts_utc=datetime(2030, 8, 15, 6, tzinfo=UTC),
                    cloud_pct=88.0,
                )
            ]
        )
        session.commit()
    refresh_rollups(stations_sample, STATION_ID)
    return stations_sample


def test_month_aggregation(engine: Engine) -> None:
    plan = plan_series("cloud", FROM, TO, "month")
    series, coverage = query_series(engine, STATION_ID, plan, FROM, TO)
    assert series == [
        {
            "period": "2030-07",
            "bucket_start": "2030-07-01T00:00:00Z",
            "bucket_end": "2030-08-01T00:00:00Z",
            "mean_cloud_pct": 50.0,
            "min_cloud_pct": 50.0,
            "max_cloud_pct": 50.0,
            "p05_cloud_pct": 50.0,
            "p50_cloud_pct": 50.0,
            "p95_cloud_pct": 50.0,
            "observed_count": 12,
            "expected_count": 744,  # 31 days in July
            "missing_count": 732,
        },
        {
            "period": "2030-08",
            "bucket_start": "2030-08-01T00:00:00Z",
            "bucket_end": "2030-09-01T00:00:00Z",
            "mean_cloud_pct": 88.0,
            "min_cloud_pct": 88.0,
            "max_cloud_pct": 88.0,
            "p05_cloud_pct": 88.0,
            "p50_cloud_pct": 88.0,
            "p95_cloud_pct": 88.0,
            "observed_count": 1,
            "expected_count": 744,  # full calendar month
            "missing_count": 743,
        },
    ]
    assert coverage == round(13 / (365 * 24), 3)


def test_day_aggregation(engine: Engine) -> None:
    plan = plan_series("cloud", FROM, TO, "day", width_px=10_000)
    series, _ = query_series(engine, STATION_ID, plan, FROM, TO)
    assert [row["period"] for row in series] == ["2030-07-01", "2030-08-15"]
    assert series[0]["mean_cloud_pct"] == 50.0
    assert series[0]["observed_count"] == 12
    assert series[0]["expected_count"] == 24


def test_raw_resolution(engine: Engine) -> None:
    plan = plan_series("cloud", date(2030, 7, 1), date(2030, 7, 1), "raw")
    series, coverage = query_series(engine, STATION_ID, plan, date(2030, 7, 1), date(2030, 7, 1))
    assert len(series) == 24
    assert series[0]["period"] == "2030-07-01T00:00:00Z"
    assert series[-1]["missing_count"] == 1
    assert coverage == 0.5


def test_sweden_aggregation_averages_active_station_rollups(stations_sample: Engine) -> None:
    with Session(stations_sample) as session:
        active_ids = [
            station.id for station in session.exec(select(Station).where(Station.active)).all()
        ]
        first, second = active_ids[:2]
        session.add_all(
            [
                CloudHourly(
                    station_id=first,
                    ts_utc=datetime(2030, 7, 1, 0, tzinfo=UTC),
                    cloud_pct=20.0,
                ),
                CloudHourly(
                    station_id=second,
                    ts_utc=datetime(2030, 7, 1, 0, tzinfo=UTC),
                    cloud_pct=80.0,
                ),
            ]
        )
        session.commit()

    refresh_rollups(stations_sample, first)
    refresh_rollups(stations_sample, second)

    plan = plan_series("cloud", date(2030, 7, 1), date(2030, 7, 1), "hour")
    series, coverage, station_count = query_sweden_series(
        stations_sample,
        plan,
        date(2030, 7, 1),
        date(2030, 7, 1),
    )

    assert station_count == 2
    assert series == [
        {
            "period": "2030-07-01T00:00:00Z",
            "bucket_start": "2030-07-01T00:00:00Z",
            "bucket_end": "2030-07-01T01:00:00Z",
            "mean_cloud_pct": 50.0,
            "min_cloud_pct": 20.0,
            "max_cloud_pct": 80.0,
            "p05_cloud_pct": 23.0,
            "p50_cloud_pct": 50.0,
            "p95_cloud_pct": 77.0,
            "observed_count": 2,
            "expected_count": 2,
            "missing_count": 0,
        }
    ]
    assert coverage == 1.0


def test_sweden_aggregation_counts_absent_participating_stations_as_missing(
    stations_sample: Engine,
) -> None:
    """A station that reports early but goes dark later still counts toward the
    expected total, so its later absence reads as missing instead of inflating
    coverage to a falsely complete 100%."""
    with Session(stations_sample) as session:
        active_ids = [
            station.id for station in session.exec(select(Station).where(Station.active)).all()
        ]
        always, drops = active_ids[:2]
        session.add_all(
            [
                # `always` reports both hours; `drops` reports only the first and
                # then goes dark — the Dravagen-style mid-window source gap.
                CloudHourly(
                    station_id=always, ts_utc=datetime(2030, 7, 1, 0, tzinfo=UTC), cloud_pct=40.0
                ),
                CloudHourly(
                    station_id=always, ts_utc=datetime(2030, 7, 1, 1, tzinfo=UTC), cloud_pct=60.0
                ),
                CloudHourly(
                    station_id=drops, ts_utc=datetime(2030, 7, 1, 0, tzinfo=UTC), cloud_pct=80.0
                ),
            ]
        )
        session.commit()

    refresh_rollups(stations_sample, always)
    refresh_rollups(stations_sample, drops)

    plan = plan_series("cloud", date(2030, 7, 1), date(2030, 7, 1), "hour")
    series, coverage, station_count = query_sweden_series(
        stations_sample,
        plan,
        date(2030, 7, 1),
        date(2030, 7, 1),
    )

    assert station_count == 2
    assert [(p["observed_count"], p["expected_count"], p["missing_count"]) for p in series] == [
        (2, 2, 0),  # 00:00 — both stations present
        (1, 2, 1),  # 01:00 — `drops` absent but still expected → visible as missing
    ]
    # 3 observed of 4 expected, not the falsely complete 3/3 the old per-present
    # denominator reported.
    assert coverage == 0.75

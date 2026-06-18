"""Truth tests for cloud normals against the isolated test database.

The point of a climatology is averaging *across years*, so every fixture seeds
the same calendar slot in two different years with different values and asserts
the normal lands on the mean — not on either year alone.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select

from cloudy.climatology import cloud
from cloudy.climatology.query import ClimatologyCloudQuery
from cloudy.climatology.types import CloudNormalPoint
from cloudy.db.models import CloudHourly, Station
from cloudy.ingest import stations

# Berga, from the captured station registry. Its coordinates are what the query
# resolves to via nearest_active.
STATION_ID = 98040
BERGA_LAT, BERGA_LON = 59.068, 18.115


@pytest.fixture
def engine(stations_sample: Engine) -> Engine:
    rows: list[CloudHourly] = []
    # July across two years: 40 and 60 -> month normal 50, with a real spread.
    for year, pct in ((2020, 40.0), (2021, 60.0)):
        for hour in range(24):
            rows.append(
                CloudHourly(
                    station_id=STATION_ID,
                    ts_utc=datetime(year, 7, 1, hour, tzinfo=UTC),
                    cloud_pct=pct,
                )
            )
    # A not-observable hour (NULL) must be ignored by mean and percentiles alike.
    rows.append(
        CloudHourly(
            station_id=STATION_ID,
            ts_utc=datetime(2021, 7, 2, 0, tzinfo=UTC),
            cloud_pct=None,
        )
    )
    with Session(stations_sample) as session:
        session.add_all(rows)
        session.commit()
    return stations_sample


def _series_by_period(engine: Engine, period: str) -> dict[str, CloudNormalPoint]:
    query = ClimatologyCloudQuery(lat=BERGA_LAT, lon=BERGA_LON, period=period)  # type: ignore[arg-type]
    now = datetime(2022, 1, 15, tzinfo=UTC)  # outside the seeded months
    body = cloud.compute(engine, query, now)
    return {p["period"]: p for p in body["series"]}


def test_monthly_normal_averages_across_years(engine: Engine) -> None:
    july = _series_by_period(engine, "month")["7"]
    assert july["mean_cloud_pct"] == 50.0  # mean of 40 (2020) and 60 (2021)
    assert july["year_count"] == 2
    assert july["observed_count"] == 48  # 24 + 24 real readings; the NULL excluded


def test_monthly_normal_reports_percentile_band(engine: Engine) -> None:
    july = _series_by_period(engine, "month")["7"]
    # Half the readings are 40 and half 60: p10 sits in the low cluster, p90 in
    # the high one, p50 at the midpoint.
    assert july["p10_cloud_pct"] == 40.0
    assert july["p50_cloud_pct"] == 50.0
    assert july["p90_cloud_pct"] == 60.0


def test_sweden_wide_pools_active_stations(stations_sample: Engine) -> None:
    """With no location the normal pools every active station into one Sweden-wide
    series — scope 'sweden', no single station, a station count instead, and the
    mean is the pool of all stations' hours."""
    with Session(stations_sample) as session:
        active = [s.id for s in session.exec(select(Station).where(Station.active)).all()]
        first, second = active[:2]
        session.add_all(
            [
                CloudHourly(
                    station_id=first, ts_utc=datetime(2020, 7, 1, 0, tzinfo=UTC), cloud_pct=20.0
                ),
                CloudHourly(
                    station_id=second, ts_utc=datetime(2020, 7, 1, 0, tzinfo=UTC), cloud_pct=80.0
                ),
            ]
        )
        session.commit()

    assert cloud.refresh_sweden_normals(stations_sample) == 3
    with Session(stations_sample) as session:
        session.add(
            CloudHourly(
                station_id=first,
                ts_utc=datetime(2020, 7, 2, 0, tzinfo=UTC),
                cloud_pct=100.0,
            )
        )
        session.commit()

    body = cloud.compute(
        stations_sample, ClimatologyCloudQuery(period="month"), datetime(2022, 1, 15, tzinfo=UTC)
    )
    assert body["scope"] == "sweden"
    assert body["station"] is None
    assert body["station_count"] == len(active)
    july = {p["period"]: p for p in body["series"]}["7"]
    assert july["mean_cloud_pct"] == 50.0  # read from the refreshed materialized normal


def test_monthly_normal_reports_sky_state_shares(stations_sample: Engine) -> None:
    """clear/partial/overcast split usable hours by the okta-style bands (clear
    <25%, overcast >75%, partial between) and sum to ~100 — the honest spread for
    U-shaped cloud that the stacked column draws."""

    # One August day: 1 clear, 2 partial, 1 overcast -> 25 / 50 / 25.
    def hour(h: int, pct: float) -> CloudHourly:
        return CloudHourly(
            station_id=STATION_ID, ts_utc=datetime(2020, 8, 1, h, tzinfo=UTC), cloud_pct=pct
        )

    with Session(stations_sample) as session:
        session.add_all([hour(0, 10.0), hour(1, 50.0), hour(2, 50.0), hour(3, 90.0)])
        session.commit()
    query = ClimatologyCloudQuery(lat=BERGA_LAT, lon=BERGA_LON, period="month")
    body = cloud.compute(stations_sample, query, datetime(2022, 1, 15, tzinfo=UTC))
    august = {p["period"]: p for p in body["series"]}["8"]
    assert august["clear_pct"] == 25.0
    assert august["partial_pct"] == 50.0
    assert august["overcast_pct"] == 25.0


def test_cloud_distance_filter_widens_the_station_pool(stations_sample: Engine) -> None:
    """A bigger radius pools more stations into the cloud normal — the distance
    filter actually filters. (Pure helper check: the pool grows and stays sorted.)"""
    with Session(stations_sample) as session:
        near = stations.active_within_radius(session, 59.33, 18.06, 25.0)
        far = stations.active_within_radius(session, 59.33, 18.06, 100.0)
    near_ids = {s.id for s, _ in near}
    far_ids = {s.id for s, _ in far}
    assert near_ids <= far_ids  # widening only adds stations
    assert len(far_ids) > len(near_ids)  # ...and around Stockholm it adds some
    distances = [d for _, d in far]
    assert distances == sorted(distances)  # nearest first
    assert all(d <= 100.0 for d in distances)


def test_resolves_to_nearest_station(engine: Engine) -> None:
    query = ClimatologyCloudQuery(lat=BERGA_LAT, lon=BERGA_LON, period="month")
    body = cloud.compute(engine, query, datetime(2022, 1, 15, tzinfo=UTC))
    station = body["station"]
    assert station is not None
    assert station["station_id"] == STATION_ID
    assert body["scope"] == "station"
    assert body["meta"]["attribution"] == "Source: SMHI"


def test_current_month_blends_observed_and_tail(engine: Engine) -> None:
    """Mid-July, with observed hours running cloudier than the July normal.

    Day 11 of a 31-day July: 10 observed days at 90% so far, 21 remaining days
    filled from the July climatology mean (50%). The blend is day-weighted, and
    the baseline is the plain July normal regardless of what's been observed.
    """
    with Session(engine) as session:
        session.add_all(
            CloudHourly(
                station_id=STATION_ID,
                ts_utc=datetime(2022, 7, day, 12, tzinfo=UTC),
                cloud_pct=90.0,
            )
            for day in range(1, 11)
        )
        session.commit()

    query = ClimatologyCloudQuery(lat=BERGA_LAT, lon=BERGA_LON, period="month")
    body = cloud.compute(engine, query, datetime(2022, 7, 11, 8, tzinfo=UTC))
    current = body["current_month"]

    assert current["month"] == 7
    assert current["observed_so_far_pct"] == 90.0
    assert current["observed_days"] == 10
    # The seeded 2022 July hours raise the all-years July mean above 50, so the
    # baseline is the recomputed monthly normal, not a hard-coded 50.
    assert current["baseline_pct"] == current["climatology_tail_pct"]
    baseline = current["baseline_pct"]
    assert baseline is not None
    expected = round((90.0 * 10 + baseline * 21) / 31, 1)
    assert current["expected_pct"] == expected


def test_current_month_with_no_observations_falls_back_to_baseline(engine: Engine) -> None:
    # January has no seeded data and the current month (Jan 2025) has no hours:
    # expectation must be the bare baseline (here None — no January climatology).
    query = ClimatologyCloudQuery(lat=BERGA_LAT, lon=BERGA_LON, period="month")
    body = cloud.compute(engine, query, datetime(2025, 1, 5, tzinfo=UTC))
    current = body["current_month"]
    assert current["observed_so_far_pct"] is None
    assert current["expected_pct"] == current["baseline_pct"]

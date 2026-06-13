"""Fixture-replay tests for metobs cloud CSV ingest."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlmodel import Session

from cloudy.db.models import CloudHourly
from cloudy.ingest import cloud

FIXTURE = Path(__file__).parent / "fixtures" / "metobs-cloud-98040-sample.csv"
STATION_ID = 98040


def test_parse_rows_normalizes_and_skips_sentinels() -> None:
    rows, skipped = cloud.parse_rows(FIXTURE, STATION_ID)
    assert skipped == 0
    assert len(rows) == 10
    by_ts = {row["ts_utc"]: row["cloud_pct"] for row in rows}
    assert by_ts[datetime(2018, 7, 1, 3, tzinfo=UTC)] is None  # 113
    assert by_ts[datetime(2018, 7, 2, 12, tzinfo=UTC)] is None  # 9999
    assert by_ts[datetime(2018, 7, 1, 4, tzinfo=UTC)] == 50.0


def test_ingest_station_is_idempotent(
    stations_sample: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cloud, "fetch_csv", lambda station_id, period: (FIXTURE, True))
    first = cloud.ingest_station(stations_sample, STATION_ID)
    second = cloud.ingest_station(stations_sample, STATION_ID)
    assert first.rows == second.rows == 10
    with Session(stations_sample) as session:
        count = session.scalar(select(func.count()).select_from(CloudHourly))
    assert count == 10

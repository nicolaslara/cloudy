"""Fixture-replay tests for metobs cloud CSV ingest."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import Engine, func
from sqlmodel import Session, select

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


def test_fetch_csv_replays_corrected_archive_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cloud, "get_settings", lambda: SimpleNamespace(raw_data_dir=str(tmp_path)))
    path = cloud.raw_path(STATION_ID, "corrected-archive")
    path.parent.mkdir(parents=True)
    path.write_text("cached", encoding="utf-8")

    def fail_get(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("corrected archive should use cache")

    # String target so we patch httpx.get without referencing the re-imported
    # `cloud.httpx` attribute (which mypy's no-implicit-reexport rule rejects).
    monkeypatch.setattr("cloudy.ingest.cloud.httpx.get", fail_get)

    fetched_path, fetched = cloud.fetch_csv(STATION_ID, "corrected-archive")

    assert fetched_path == path
    assert fetched is False
    assert path.read_text(encoding="utf-8") == "cached"


def test_fetch_csv_refetches_latest_months_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cloud, "get_settings", lambda: SimpleNamespace(raw_data_dir=str(tmp_path)))
    path = cloud.raw_path(STATION_ID, "latest-months")
    path.parent.mkdir(parents=True)
    path.write_text("stale", encoding="utf-8")

    class Response:
        content = b"fresh"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr("cloudy.ingest.cloud.httpx.get", lambda *_args, **_kwargs: Response())

    fetched_path, fetched = cloud.fetch_csv(STATION_ID, "latest-months")

    assert fetched_path == path
    assert fetched is True
    assert path.read_text(encoding="utf-8") == "fresh"


def test_ingest_station_is_idempotent(
    stations_sample: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cloud, "fetch_csv", lambda station_id, period: (FIXTURE, True))
    first = cloud.ingest_station(stations_sample, STATION_ID)
    second = cloud.ingest_station(stations_sample, STATION_ID)
    assert first.rows == second.rows == 10
    with Session(stations_sample) as session:
        count = session.exec(select(func.count()).select_from(CloudHourly)).one()
    assert count == 10

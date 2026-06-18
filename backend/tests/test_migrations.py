"""Alembic revision chain and data migrations."""

import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import create_engine, text

from cloudy.db.migrate import upgrade, upgrade_head

TEST_PG_SERVER = os.environ.get(
    "TEST_PG_SERVER", "postgresql+psycopg://cloudy:cloudy@localhost:5432/cloudy"
)


@pytest.fixture
def _empty_db_url() -> Iterator[str]:
    admin = create_engine(TEST_PG_SERVER, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("no Postgres reachable (make db) — migration test skipped")
    name = f"cloudy_migrate_test_{uuid.uuid4().hex[:12]}"
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = TEST_PG_SERVER.rsplit("/", 1)[0] + f"/{name}"
    yield url
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    admin.dispose()


def test_upgrade_head_creates_tables(_empty_db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_db(monkeypatch, _empty_db_url)

    upgrade_head()

    engine = create_engine(_empty_db_url)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        }
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()

    assert tables == {
        "alembic_version",
        "cloud_hourly",
        "cloud_normals",
        "cloud_rollups",
        "ingest_runs",
        "lightning_daily_rollups",
        "lightning_events",
        "stations",
    }
    assert version == "2b8d6f7a9c01"


def test_cloud_rollup_migration_backfills_existing_hourly_data(
    _empty_db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_db(monkeypatch, _empty_db_url)

    upgrade("616b3e53d92a")
    engine = create_engine(_empty_db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO stations (
                    id, name, lat, lon, active, source, source_version
                )
                VALUES (
                    98040, 'Berga', 59.33, 18.06, true, 'smhi-metobs', '1.0'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO cloud_hourly (
                    station_id,
                    ts_utc,
                    cloud_pct,
                    quality,
                    source,
                    source_version
                )
                VALUES
                    (98040, '2018-07-01T00:00:00Z', 40.0, 'G', 'smhi-metobs', '1.0'),
                    (98040, '2018-07-01T01:00:00Z', NULL, 'G', 'smhi-metobs', '1.0'),
                    (98040, '2018-07-01T02:00:00Z', 60.0, 'G', 'smhi-metobs', '1.0')
                """
            )
        )

    upgrade_head()

    with engine.connect() as conn:
        rows: dict[str, list[Any]] = {}
        for row in conn.execute(
            text(
                """
                SELECT resolution, observed_count, expected_count, mean_cloud_pct
                FROM cloud_rollups
                WHERE station_id = 98040
                ORDER BY resolution, bucket_start
                """
            )
        ):
            rows.setdefault(row.resolution, []).append(row)
        day = conn.execute(
            text(
                """
                SELECT resolution, observed_count, expected_count, mean_cloud_pct
                FROM cloud_rollups
                WHERE station_id = 98040
                  AND resolution = 'day'
                  AND bucket_start = '2018-07-01T00:00:00Z'
                """
            )
        ).one()
        month = conn.execute(
            text(
                """
                SELECT resolution, observed_count, expected_count, mean_cloud_pct
                FROM cloud_rollups
                WHERE station_id = 98040
                  AND resolution = 'month'
                  AND bucket_start = '2018-07-01T00:00:00Z'
                """
            )
        ).one()
        normal = conn.execute(
            text(
                """
                SELECT period, bucket, observed_count, mean_cloud_pct
                FROM cloud_normals
                WHERE period = 'month'
                  AND bucket = 7
                  AND source = 'smhi-metobs'
                  AND source_version = '1.0'
                """
            )
        ).one()
    engine.dispose()

    assert set(rows) == {"hour", "6h", "day", "week", "month", "year"}
    assert [row.observed_count for row in rows["hour"]] == [1, 0, 1]
    assert day.observed_count == 2
    assert day.expected_count == 24
    assert day.mean_cloud_pct == 50.0
    assert month.observed_count == 2
    assert month.expected_count == 744
    assert month.mean_cloud_pct == 50.0
    assert normal.observed_count == 2
    assert normal.mean_cloud_pct == 50.0


def test_lightning_rollup_migration_backfills_existing_events(
    _empty_db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_db(monkeypatch, _empty_db_url)

    upgrade("7c3a4a4b5c6d")
    engine = create_engine(_empty_db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO lightning_events (
                    ts_utc,
                    day,
                    lat,
                    lon,
                    peak_current_ka,
                    multiplicity,
                    number_of_sensors,
                    cloud_indicator,
                    source,
                    source_version
                )
                VALUES
                    (
                        '2018-07-01T12:00:00Z',
                        '2018-07-01',
                        59.3,
                        18.0,
                        -110.0,
                        1,
                        4,
                        0,
                        'smhi-lightning',
                        '1.0'
                    ),
                    (
                        '2018-07-01T13:00:00Z',
                        '2018-07-01',
                        59.4,
                        18.1,
                        30.0,
                        1,
                        4,
                        1,
                        'smhi-lightning',
                        '1.0'
                    )
                """
            )
        )

    upgrade_head()

    with engine.connect() as conn:
        rollup = conn.execute(
            text(
                """
                SELECT day, cg_count, all_count, lightning_days, max_abs_peak_ka,
                       strongest_event_time
                FROM lightning_daily_rollups
                WHERE day = '2018-07-01'
                """
            )
        ).one()
    engine.dispose()

    assert rollup.cg_count == 1
    assert rollup.all_count == 2
    assert rollup.lightning_days == 1
    assert rollup.max_abs_peak_ka == 110.0
    assert rollup.strongest_event_time.isoformat() == "2018-07-01T12:00:00+00:00"


def _use_db(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", url)
    from cloudy.config import get_settings
    from cloudy.db.session import get_engine

    get_settings.cache_clear()
    get_engine.cache_clear()

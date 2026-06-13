"""Alembic revision chain: upgrade head on an empty database."""

import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text

from cloudy.db.migrate import upgrade_head

TEST_PG_SERVER = os.environ.get(
    "TEST_PG_SERVER", "postgresql+psycopg://cloudy:cloudy@localhost:5432/cloudy"
)


@pytest.fixture(scope="module")
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
    monkeypatch.setenv("DATABASE_URL", _empty_db_url)
    from cloudy.config import get_settings

    get_settings.cache_clear()

    upgrade_head()

    engine = create_engine(_empty_db_url)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                )
            )
        }
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()

    assert tables == {
        "alembic_version",
        "cloud_hourly",
        "ingest_runs",
        "lightning_events",
        "stations",
    }
    assert version == "616b3e53d92a"

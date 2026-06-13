"""Django-style test database (locked 2026-06-11).

One throwaway database per test session (created on the compose Postgres,
schema built once, dropped at the end); every test gets isolation by
truncation; data fixtures are declared per test and built from captured real
payloads. Tests NEVER read DATABASE_URL — pointing tests at a database that
contains anything you care about is a bug, not a configuration (incident
2026-06-11: a drop_all against the dev DB wiped the 4.1M-row archive).
"""

import json
import os
import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, insert, text
from sqlmodel import SQLModel

from cloudy.db import models  # noqa: F401  (register tables on the metadata)
from cloudy.db import session as db_session

FIXTURES = Path(__file__).parent / "fixtures"
TEST_PG_SERVER = os.environ.get(
    "TEST_PG_SERVER", "postgresql+psycopg://cloudy:cloudy@localhost:5432/cloudy"
)


@pytest.fixture(scope="session")
def _test_db_engine() -> Iterator[Engine]:
    admin = create_engine(TEST_PG_SERVER, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("no Postgres reachable (make db) — DB tests skipped, pure tests still run")
    name = f"cloudy_test_{uuid.uuid4().hex[:12]}"
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(TEST_PG_SERVER.rsplit("/", 1)[0] + f"/{name}")
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def db(_test_db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    """The app's engine for one test; tables truncated afterwards (isolation)."""
    monkeypatch.setattr(db_session, "get_engine", lambda: _test_db_engine)
    yield _test_db_engine
    tables = ", ".join(f'"{t.name}"' for t in SQLModel.metadata.sorted_tables)
    with _test_db_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def stations_sample(db: Engine) -> Engine:
    """11 real metobs stations (8 active incl. Abisko Aut) from the captured registry."""
    from cloudy.ingest import stations

    payload = json.loads((FIXTURES / "metobs-param16-sample.json").read_text())
    stations.ingest(db, payload)
    return db


@pytest.fixture
def lightning_sample(db: Engine) -> Engine:
    """40 real strokes from the captured 2018-07-25 CSV (northern Sweden cluster)."""
    from cloudy.db.models import LightningEvent
    from cloudy.ingest.lightning import parse_rows

    rows, _ = parse_rows(FIXTURES / "lightning-2018-07-25-sample.csv", date(2018, 7, 25))
    with db.begin() as conn:
        conn.execute(insert(LightningEvent), rows)
    return db

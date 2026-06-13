import os
from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, create_engine, select

from cloudy.db.models import IngestRun


def test_ingest_run_round_trip() -> None:
    # Locked testing story: pytest runs against the compose Postgres when
    # DATABASE_URL is set (CI exports it); falls back to in-memory SQLite so
    # the test still runs without Docker locally.
    engine = create_engine(os.environ.get("DATABASE_URL", "sqlite://"))
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            IngestRun(
                source="smhi-lightning",
                job="lightning-daily",
                started_at=datetime(2026, 6, 10, 3, 0, tzinfo=UTC),
                status="running",
            )
        )
        session.commit()
        run = session.exec(select(IngestRun)).one()
        assert run.id is not None
        assert run.job == "lightning-daily"
        assert run.status == "running"
        assert run.finished_at is None

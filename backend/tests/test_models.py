from datetime import UTC, datetime

from sqlalchemy import Engine
from sqlmodel import Session, select

from cloudy.db.models import IngestRun


def test_ingest_run_round_trip(db: Engine) -> None:
    with Session(db) as session:
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

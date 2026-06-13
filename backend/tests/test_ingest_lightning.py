from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, func, select

from cloudy.db.models import LightningEvent
from cloudy.ingest import lightning

FIXTURE = Path(__file__).parent / "fixtures" / "lightning-2018-07-25-sample.csv"
DAY = date(2018, 7, 25)


def test_parse_rows_real_fixture() -> None:
    # 40 real rows + 1 deliberately malformed line in the fixture.
    rows, skipped = lightning.parse_rows(FIXTURE, DAY)
    assert len(rows) == 40
    assert skipped == 1
    first = rows[0]
    assert first["ts_utc"] == datetime(2018, 7, 25, 0, 2, 53, 510631, tzinfo=UTC)
    assert first["lat"] == 65.4018
    assert first["lon"] == 18.3213
    assert first["peak_current_ka"] == 11.0
    assert first["multiplicity"] == 0  # stroke row, not missing
    assert first["cloud_indicator"] == 1
    assert first["source_version"] == lightning.SOURCE_VERSION


def test_ingest_day_is_idempotent(db: Engine, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Replay from a fake raw archive — no network in tests.
    raw = tmp_path / lightning.SOURCE / "2018" / "07"
    raw.mkdir(parents=True)
    (raw / "2018-07-25.csv").write_bytes(FIXTURE.read_bytes())
    monkeypatch.setattr(lightning, "raw_path", lambda day: raw / f"{day.isoformat()}.csv")

    first = lightning.ingest_day(db, DAY)
    second = lightning.ingest_day(db, DAY)  # re-run must replace, not duplicate
    assert first.rows == second.rows == 40
    assert not first.fetched and not second.fetched

    with Session(db) as session:
        count = session.exec(select(func.count()).select_from(LightningEvent)).one()
        assert count == 40

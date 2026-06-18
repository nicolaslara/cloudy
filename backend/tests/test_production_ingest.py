from datetime import date
from pathlib import Path

from sqlalchemy import Engine, insert

from cloudy.db.models import LightningEvent
from cloudy.ingest.lightning import parse_rows
from cloudy.production_ingest import FIRST_LIGHTNING_DAY, next_lightning_day

FIXTURES = Path(__file__).parent / "fixtures"


def test_next_lightning_day_starts_at_archive_beginning_for_empty_db(db: Engine) -> None:
    assert next_lightning_day(db) == FIRST_LIGHTNING_DAY


def test_next_lightning_day_advances_past_latest_ingested_day(db: Engine) -> None:
    rows, _ = parse_rows(FIXTURES / "lightning-2018-07-25-sample.csv", date(2018, 7, 25))
    with db.begin() as conn:
        conn.execute(insert(LightningEvent), rows)

    assert next_lightning_day(db) == date(2018, 7, 26)

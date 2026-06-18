"""Production data refresh orchestration.

The one-source `cloudy ingest ...` commands stay small and composable. This
module owns the operator workflow: initial backfill, smoke load, and scheduled
incremental refresh against Neon.
"""

import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from sqlalchemy import Engine, text

from cloudy.config import get_settings
from cloudy.db.session import get_engine
from cloudy.ingest import lightning

Mode = Literal["smoke", "full", "incremental"]

FIRST_LIGHTNING_DAY = date(2015, 1, 1)
SMOKE_FROM = date(2018, 7, 1)
SMOKE_TO = date(2018, 7, 31)
SMOKE_CLOUD_STATION = 98040


@dataclass(frozen=True)
class IngestSummary:
    mode: Mode
    lightning_from: date | None
    lightning_to: date | None
    lightning_events: int
    lightning_days: int
    lightning_skipped: bool


def run(mode: Mode, *, today: date | None = None) -> IngestSummary:
    """Run the production ingest workflow for a mode."""

    from cloudy.ingest import cloud as cloud_ingest
    from cloudy.ingest import stations
    from cloudy.logging import configure_logging

    _prepare_production_env()
    configure_logging(get_settings().log_level)
    engine = get_engine()
    today = today or datetime.now(UTC).date()

    stations_count = stations.ingest(engine)
    print(f"{stations_count} stations upserted")

    if mode == "smoke":
        lightning_from, lightning_to = SMOKE_FROM, SMOKE_TO
        lightning_results = lightning.ingest_range(engine, lightning_from, lightning_to)
        cloud_result = cloud_ingest.ingest_station(engine, SMOKE_CLOUD_STATION)
        print(f"{cloud_result.rows} hours for station {cloud_result.station_id}")
        lightning_skipped = False
    elif mode == "full":
        lightning_from, lightning_to = FIRST_LIGHTNING_DAY, today
        lightning_results = lightning.ingest_range(engine, lightning_from, lightning_to)
        cloud_results = cloud_ingest.ingest_all_active(engine)
        print(f"{sum(r.rows for r in cloud_results)} hours over {len(cloud_results)} stations")
        _run_backtest(engine)
        lightning_skipped = False
    elif mode == "incremental":
        lightning_from, lightning_to = next_lightning_day(engine), today
        if lightning_from > lightning_to:
            print(f"lightning is already current through {today.isoformat()}")
            lightning_results = []
            lightning_skipped = True
        else:
            lightning_results = lightning.ingest_range(engine, lightning_from, lightning_to)
            lightning_skipped = False
        cloud_results = cloud_ingest.ingest_all_active(engine, period="latest-months")
        print(f"{sum(r.rows for r in cloud_results)} hours over {len(cloud_results)} stations")
        _run_backtest(engine)
    else:
        raise ValueError(f"unknown production ingest mode: {mode}")

    lightning_events = sum(result.rows for result in lightning_results)
    lightning_days = len(lightning_results)
    if lightning_results:
        print(f"{lightning_events} events over {lightning_days} days")

    return IngestSummary(
        mode=mode,
        lightning_from=lightning_from,
        lightning_to=lightning_to,
        lightning_events=lightning_events,
        lightning_days=lightning_days,
        lightning_skipped=lightning_skipped,
    )


def next_lightning_day(engine: Engine) -> date:
    """Return the first SMHI lightning day not present in the target database."""

    with engine.connect() as conn:
        latest = cast(
            date | None,
            conn.execute(
                text(
                    """
                    SELECT max(day)
                    FROM lightning_events
                    WHERE source = :source
                      AND source_version = :source_version
                    """
                ),
                {"source": lightning.SOURCE, "source_version": lightning.SOURCE_VERSION},
            ).scalar_one(),
        )

    if latest is None:
        return FIRST_LIGHTNING_DAY
    return latest + timedelta(days=1)


def _prepare_production_env() -> None:
    """Make production defaults explicit before Settings/Engine are constructed."""

    os.environ.setdefault("DATABASE_URL", _database_url())
    os.environ.setdefault("RAW_DATA_DIR", "../data/raw")

    # Settings and the SQLAlchemy engine are process caches. Clear them after
    # setting env so callers can invoke this from tests or long-lived processes.
    get_settings.cache_clear()
    get_engine.cache_clear()


def _database_url() -> str:
    if database_url := os.environ.get("DATABASE_URL"):
        return database_url

    repo_root = Path(__file__).resolve().parents[2]
    terraform_dir = repo_root / "infra" / "terraform"
    result = subprocess.run(
        ["terraform", f"-chdir={terraform_dir}", "output", "-raw", "database_url"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _run_backtest(engine: Engine) -> None:
    import json

    from cloudy.ingest.retry import with_reconnect
    from cloudy.predictions import evaluate

    # The backtest is a read-heavy pass that runs at the tail of a long ingest;
    # a connection drop here would otherwise waste the whole loaded dataset, so
    # reconnect and recompute (it is pure + idempotent).
    artifact = with_reconnect(
        engine, lambda: evaluate.evaluate(engine), what="weekly-outlook backtest"
    )
    path = Path(get_settings().predictions_scorecard_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"wrote weekly-outlook benchmark ({artifact['n_stations']} stations) to {path}")

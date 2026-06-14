"""SMHI lightning archive ingestion: one CSV per day, replayed from data/raw.

Idempotency: the day-file is the unit — each (day, source_version) is replaced
in a single transaction, so re-running any day absorbs SMHI's late-loading
corrections and can never leave a half-ingested day.
"""

import csv
import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from sqlalchemy import Connection, Engine, delete, insert, text

from cloudy.config import get_settings
from cloudy.db.models import IngestRun, LightningEvent

logger = logging.getLogger(__name__)

# Write-side serving rollups. Refreshing the Sweden-wide daily summary is an
# ingest concern — it must commit in the same transaction as the events — so it
# lives in the foundation beside the events it summarizes, not in the read path.
# The exploration reader re-aggregates these daily rows up to week/month/year.
_DELETE_SWEDEN_DAILY_ROLLUPS_SQL = text(
    """
    DELETE FROM lightning_daily_rollups
    WHERE day BETWEEN :date_from AND :date_to
    """
)

_INSERT_SWEDEN_DAILY_ROLLUPS_SQL = text(
    """
    INSERT INTO lightning_daily_rollups (
        day,
        bucket_start,
        bucket_end,
        cg_count,
        all_count,
        lightning_days,
        max_abs_peak_ka,
        strongest_event_time,
        source,
        source_version
    )
    SELECT
        day,
        day::timestamp AT TIME ZONE 'UTC' AS bucket_start,
        (day + 1)::timestamp AT TIME ZONE 'UTC' AS bucket_end,
        count(*) FILTER (WHERE cloud_indicator = 0)::int AS cg_count,
        count(*)::int AS all_count,
        1 AS lightning_days,
        max(abs(peak_current_ka)) AS max_abs_peak_ka,
        (array_agg(ts_utc ORDER BY abs(peak_current_ka) DESC, ts_utc))[1]
            AS strongest_event_time,
        source,
        source_version
    FROM lightning_events
    WHERE day BETWEEN :date_from AND :date_to
    GROUP BY day, source, source_version
    ORDER BY day
    """
)


def refresh_sweden_daily_rollups(conn: Connection, date_from: date, date_to: date) -> None:
    """Refresh Sweden-wide daily serving rollups after lightning ingest."""
    conn.execute(_DELETE_SWEDEN_DAILY_ROLLUPS_SQL, {"date_from": date_from, "date_to": date_to})
    conn.execute(_INSERT_SWEDEN_DAILY_ROLLUPS_SQL, {"date_from": date_from, "date_to": date_to})


SOURCE = "smhi-lightning"
SOURCE_VERSION = "1.0"
URL = (
    "https://opendata-download-lightning.smhi.se"
    "/api/version/latest/year/{y}/month/{m:02d}/day/{d:02d}/data.csv"
)

_FLOAT_FIELDS = {
    "ellipseAngle": "ellipse_angle",
    "semiMajorAxis": "semi_major_axis",
    "semiMinorAxis": "semi_minor_axis",
    "chiSquareValue": "chi_square_value",
    "riseTime": "rise_time",
    "peakToZeroTime": "peak_to_zero_time",
    "maxRateOfRise": "max_rate_of_rise",
}
_INT_FIELDS = {
    "degreesOfFreedom": "degrees_of_freedom",
    "angleIndicator": "angle_indicator",
    "signalIndicator": "signal_indicator",
    "timingIndicator": "timing_indicator",
}


@dataclass
class DayResult:
    day: date
    rows: int
    skipped: int
    fetched: bool  # False = replayed from data/raw


def raw_path(day: date) -> Path:
    root = Path(get_settings().raw_data_dir)
    return root / SOURCE / f"{day.year}" / f"{day.month:02d}" / f"{day.isoformat()}.csv"


def fetch_day(day: date, attempts: int = 4) -> tuple[Path, bool]:
    """Return the raw CSV path for a day, downloading it only if not archived.

    Transient network errors are retried with backoff — a multi-year backfill
    must not die on one timeout.
    """
    path = raw_path(day)
    if path.exists():
        return path, False
    url = URL.format(y=day.year, m=day.month, d=day.day)
    for attempt in range(1, attempts + 1):
        try:
            response = httpx.get(url, timeout=60)
            response.raise_for_status()
            break
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            transient_status = isinstance(
                exc, httpx.HTTPStatusError
            ) and exc.response.status_code in (429, 500, 502, 503, 504)
            if attempt == attempts or not (
                isinstance(exc, httpx.TransportError) or transient_status
            ):
                raise
            wait = 2**attempt
            logger.warning(
                "lightning %s: %s — retry %d/%d in %ds", day, exc, attempt, attempts, wait
            )
            time.sleep(wait)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return path, True


def parse_rows(path: Path, day: date) -> tuple[list[dict[str, object]], int]:
    """Parse a day CSV into insertable dicts; malformed lines are counted, not fatal."""
    rows: list[dict[str, object]] = []
    skipped = 0
    with path.open(newline="") as f:
        for line in csv.DictReader(f, delimiter=";"):
            try:
                ts = datetime(
                    int(line["year"]),
                    int(line["month"]),
                    int(line["day"]),
                    int(line["hours"]),
                    int(line["minutes"]),
                    int(line["seconds"]),
                    int(line["nanoseconds"]) // 1000,  # ns → µs
                    tzinfo=UTC,  # presumed UTC; confirm in SMHI field docs pre-launch
                )
                row: dict[str, object] = {
                    "ts_utc": ts,
                    "day": day,
                    "lat": float(line["lat"]),
                    "lon": float(line["lon"]),
                    "peak_current_ka": float(line["peakCurrent"]),
                    "multiplicity": int(line["multiplicity"]),
                    "number_of_sensors": int(line["numberOfSensors"]),
                    "cloud_indicator": int(line["cloudIndicator"]),
                    "source": SOURCE,
                    "source_version": SOURCE_VERSION,
                }
                for csv_name, column in _FLOAT_FIELDS.items():
                    value = line.get(csv_name, "")
                    row[column] = float(value) if value != "" else None
                for csv_name, column in _INT_FIELDS.items():
                    value = line.get(csv_name, "")
                    row[column] = int(value) if value != "" else None
                rows.append(row)
            except (KeyError, ValueError, TypeError):
                skipped += 1
    return rows, skipped


def ingest_day(engine: Engine, day: date) -> DayResult:
    path, fetched = fetch_day(day)
    rows, skipped = parse_rows(path, day)
    if skipped:
        logger.warning("lightning %s: skipped %d malformed lines", day, skipped)
    with engine.begin() as conn:  # one transaction: replace the whole day
        conn.execute(
            delete(LightningEvent).where(
                LightningEvent.day == day,  # type: ignore[arg-type]
                LightningEvent.source_version == SOURCE_VERSION,  # type: ignore[arg-type]
            )
        )
        if rows:
            conn.execute(insert(LightningEvent), rows)
        # Refresh the day's rollup inside the same transaction so events and their
        # Sweden-wide summary commit atomically — readers never see one without
        # the other, even mid-backfill.
        refresh_sweden_daily_rollups(conn, day, day)
    logger.info("lightning %s: %d events (%s)", day, len(rows), "fetched" if fetched else "replay")
    return DayResult(day=day, rows=len(rows), skipped=skipped, fetched=fetched)


def ingest_range(engine: Engine, start: date, end: date, delay_s: float = 1.0) -> list[DayResult]:
    """Ingest [start, end], politely rate-limited, recording one IngestRun."""

    from sqlmodel import Session

    run = IngestRun(
        source=SOURCE,
        job=f"lightning {start} {end}",
        started_at=datetime.now(UTC),
        status="running",
    )
    with Session(engine) as session:
        session.add(run)
        session.commit()
        session.refresh(run)

    results: list[DayResult] = []
    status, detail = "ok", ""
    try:
        day = start
        while day <= end:
            result = ingest_day(engine, day)
            results.append(result)
            # Only rate-limit when we actually hit SMHI; a replay from data/raw
            # touches no network, so a cached backfill runs at full speed.
            if result.fetched and day < end:
                time.sleep(delay_s)
            day = date.fromordinal(day.toordinal() + 1)
        detail = f"{sum(r.rows for r in results)} events over {len(results)} days"
    except Exception as exc:
        status = "failed"
        detail = f"at {results[-1].day if results else start}: {exc}"
        raise
    # Always close out the IngestRun, even on failure: the row is the audit trail
    # and resume watermark, so a crashed backfill must land as status="failed"
    # with where it stopped, never as a row stuck forever in "running".
    finally:
        with Session(engine) as session:
            finished = session.get(IngestRun, run.id)
            assert finished is not None
            finished.finished_at = datetime.now(UTC)
            finished.status = status
            finished.detail = detail
            session.add(finished)
            session.commit()
    return results

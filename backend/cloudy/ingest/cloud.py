"""SMHI metobs parameter-16 cloud ingest: corrected-archive + latest-months CSVs.

One module per source boundary: raw CSV archived under data/raw/, replayed
without re-download. Sentinel and unit rules live only in core/units.py.
"""

from __future__ import annotations

import csv
import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import httpx
from sqlalchemy import Engine, delete, insert, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session, select

from cloudy.config import get_settings
from cloudy.core.cloud_types import Resolution
from cloudy.core.series_sql import bucket_end_expr, bucket_start_expr
from cloudy.core.units import normalize_cloud_pct
from cloudy.db.models import CloudHourly, IngestRun, Station

logger = logging.getLogger(__name__)

SOURCE = "smhi-metobs"
SOURCE_VERSION = "1.0"

# Rollups are a write-side concern: materialized on ingest, read straight back by
# cloud_series. They live here (not in the read path) so the read module stays
# pure query. "raw" is excluded — it is served live from cloud_hourly, never a
# stored bucket.
ROLLUP_RESOLUTIONS: tuple[Resolution, ...] = ("hour", "6h", "day", "week", "month", "year")


def refresh_rollups(engine: Engine, station_id: int, source_version: str = "1.0") -> None:
    """Recompute all serving rollups for one station from cloud_hourly.

    Delete-then-insert per resolution so a re-ingest of corrected history fully
    replaces stale buckets rather than layering on top. Cheap because it is
    scoped to one station and one source_version.
    """
    with engine.begin() as conn:
        for resolution in ROLLUP_RESOLUTIONS:
            conn.execute(
                text(
                    """
                    DELETE FROM cloud_rollups
                    WHERE station_id = :station_id
                      AND source_version = :source_version
                      AND resolution = :resolution
                    """
                ),
                {
                    "station_id": station_id,
                    "source_version": source_version,
                    "resolution": resolution,
                },
            )
            conn.execute(
                text(_insert_rollup_sql(resolution)),
                {
                    "station_id": station_id,
                    "source_version": source_version,
                    "resolution": resolution,
                },
            )


def _insert_rollup_sql(resolution: Resolution) -> str:
    # Bucket boundaries come from the shared series_sql helpers so the rollups we
    # write line up exactly with the buckets the read path expects.
    bucket_start = bucket_start_expr(resolution)
    bucket_end = bucket_end_expr(resolution, "bucket_start")
    return f"""
        INSERT INTO cloud_rollups (
            station_id,
            resolution,
            bucket_start,
            bucket_end,
            observed_count,
            expected_count,
            missing_count,
            mean_cloud_pct,
            min_cloud_pct,
            max_cloud_pct,
            p05_cloud_pct,
            p50_cloud_pct,
            p95_cloud_pct,
            source,
            source_version
        )
        WITH hourly AS (
            SELECT
                station_id,
                source,
                source_version,
                {bucket_start} AS bucket_start,
                cloud_pct
            FROM cloud_hourly
            WHERE station_id = :station_id
              AND source_version = :source_version
        ),
        bucketed AS (
            SELECT
                station_id,
                source,
                source_version,
                :resolution AS resolution,
                bucket_start,
                {bucket_end} AS bucket_end,
                cloud_pct
            FROM hourly
        )
        SELECT
            station_id,
            resolution,
            bucket_start,
            bucket_end,
            count(cloud_pct)::int AS observed_count,
            (EXTRACT(EPOCH FROM (bucket_end - bucket_start)) / 3600.0)::int AS expected_count,
            GREATEST(
                ((EXTRACT(EPOCH FROM (bucket_end - bucket_start)) / 3600.0)::int)
                - count(cloud_pct)::int,
                0
            ) AS missing_count,
            avg(cloud_pct) FILTER (WHERE cloud_pct IS NOT NULL) AS mean_cloud_pct,
            min(cloud_pct) FILTER (WHERE cloud_pct IS NOT NULL) AS min_cloud_pct,
            max(cloud_pct) FILTER (WHERE cloud_pct IS NOT NULL) AS max_cloud_pct,
            percentile_cont(0.05) WITHIN GROUP (ORDER BY cloud_pct)
                FILTER (WHERE cloud_pct IS NOT NULL) AS p05_cloud_pct,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY cloud_pct)
                FILTER (WHERE cloud_pct IS NOT NULL) AS p50_cloud_pct,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY cloud_pct)
                FILTER (WHERE cloud_pct IS NOT NULL) AS p95_cloud_pct,
            source,
            source_version
        FROM bucketed
        GROUP BY station_id, resolution, bucket_start, bucket_end, source, source_version
        ORDER BY bucket_start
    """


HISTORY_START = date(2015, 1, 1)
Period = Literal["corrected-archive", "latest-months"]
BASE = "https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/16/station"


@dataclass
class StationResult:
    station_id: int
    rows: int
    skipped: int
    fetched: bool


def raw_path(station_id: int, period: Period) -> Path:
    root = Path(get_settings().raw_data_dir)
    return root / SOURCE / str(station_id) / f"{period}.csv"


def csv_url(station_id: int, period: Period) -> str:
    return f"{BASE}/{station_id}/period/{period}/data.csv"


def fetch_csv(station_id: int, period: Period, attempts: int = 4) -> tuple[Path, bool]:
    path = raw_path(station_id, period)
    if path.exists() and period == "corrected-archive":
        return path, False
    url = csv_url(station_id, period)
    for attempt in range(1, attempts + 1):
        try:
            response = httpx.get(url, timeout=120)
            response.raise_for_status()
            break
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            transient = isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (
                429,
                500,
                502,
                503,
                504,
            )
            if attempt == attempts or not (isinstance(exc, httpx.TransportError) or transient):
                raise
            wait = 2**attempt
            logger.warning(
                "cloud %s/%s: %s — retry %d/%d in %ds",
                station_id,
                period,
                exc,
                attempt,
                attempts,
                wait,
            )
            time.sleep(wait)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return path, True


def parse_rows(path: Path, station_id: int) -> tuple[list[dict[str, object]], int]:
    """Parse the data section of a metobs CSV; rows before HISTORY_START are dropped."""
    rows: list[dict[str, object]] = []
    skipped = 0
    in_data = False
    with path.open(newline="", encoding="utf-8") as handle:
        for line in csv.reader(handle, delimiter=";"):
            if not line:
                continue
            if not in_data:
                if line[0].startswith("Datum"):
                    in_data = True
                continue
            if len(line) < 4:
                skipped += 1
                continue
            try:
                day = date.fromisoformat(line[0].strip())
                if day < HISTORY_START:
                    continue
                hour, minute, second = (int(part) for part in line[1].strip().split(":"))
                ts = datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=UTC)
                cloud_pct = normalize_cloud_pct(line[2].strip())
                quality = line[3].strip() or None
                rows.append(
                    {
                        "station_id": station_id,
                        "ts_utc": ts,
                        "cloud_pct": cloud_pct,
                        "quality": quality,
                        "source": SOURCE,
                        "source_version": SOURCE_VERSION,
                    }
                )
            except (ValueError, IndexError):
                skipped += 1
    return rows, skipped


def ingest_station(
    engine: Engine,
    station_id: int,
    period: Period = "corrected-archive",
) -> StationResult:
    """Load one station period CSV. Archive replaces; latest-months upserts."""
    path, fetched = fetch_csv(station_id, period)
    rows, skipped = parse_rows(path, station_id)
    if skipped:
        logger.warning("cloud %s/%s: skipped %d malformed lines", station_id, period, skipped)

    with engine.begin() as conn:
        if period == "corrected-archive":
            conn.execute(
                delete(CloudHourly).where(
                    CloudHourly.station_id == station_id,  # type: ignore[arg-type]
                    CloudHourly.source_version == SOURCE_VERSION,  # type: ignore[arg-type]
                )
            )
            if rows:
                conn.execute(insert(CloudHourly), rows)
        elif rows:
            statement = pg_insert(CloudHourly).values(rows)
            statement = statement.on_conflict_do_update(
                index_elements=["station_id", "source", "source_version", "ts_utc"],
                set_={
                    "cloud_pct": statement.excluded.cloud_pct,
                    "quality": statement.excluded.quality,
                },
            )
            conn.execute(statement)

    logger.info(
        "cloud %s/%s: %d hours (%s)",
        station_id,
        period,
        len(rows),
        "fetched" if fetched else "replay",
    )
    refresh_rollups(engine, station_id, SOURCE_VERSION)
    return StationResult(station_id=station_id, rows=len(rows), skipped=skipped, fetched=fetched)


def ingest_all_active(
    engine: Engine,
    period: Period = "corrected-archive",
    delay_s: float = 1.0,
) -> list[StationResult]:
    """Backfill every active station; records one IngestRun."""
    with Session(engine) as session:
        active = session.exec(select(Station).where(Station.active)).all()
    if not active:
        raise LookupError("no stations ingested — run: cloudy ingest stations")

    run = IngestRun(
        source=SOURCE,
        job=f"cloud {period} {len(active)} stations",
        started_at=datetime.now(UTC),
        status="running",
    )
    with Session(engine) as session:
        session.add(run)
        session.commit()
        session.refresh(run)

    results: list[StationResult] = []
    status, detail = "ok", ""
    try:
        for index, station in enumerate(active):
            results.append(ingest_station(engine, station.id, period))
            if index + 1 < len(active):
                time.sleep(delay_s)
        detail = f"{sum(r.rows for r in results)} hours over {len(results)} stations"
    except Exception as exc:
        status = "failed"
        detail = f"at station {results[-1].station_id if results else '?'}: {exc}"
        raise
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

"""SMHI metobs station registry for parameter 16 (total cloud amount).

Small (~460 rows) and rarely changing: fetched on demand, upserted whole.
"""

import logging
from typing import Any

import httpx
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session, select

from cloudy.db.models import Station

logger = logging.getLogger(__name__)

URL = "https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/16.json"


def fetch() -> dict[str, Any]:
    response = httpx.get(URL, timeout=30)
    response.raise_for_status()
    return response.json()  # type: ignore[no-any-return]


def parse(payload: dict[str, Any]) -> list[Station]:
    stations = []
    for item in payload.get("station", []):
        try:
            stations.append(
                Station(
                    id=int(item["id"]),
                    name=str(item["name"]),
                    lat=float(item["latitude"]),
                    lon=float(item["longitude"]),
                    active=bool(item["active"]),
                )
            )
        except (KeyError, ValueError, TypeError):
            logger.warning("stations: skipping malformed entry %r", item.get("id"))
    return stations


def ingest(engine: Engine, payload: dict[str, Any] | None = None) -> int:
    stations = parse(payload if payload is not None else fetch())
    rows = [s.model_dump() for s in stations]
    statement = pg_insert(Station).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["id"],
        set_={c: statement.excluded[c] for c in ("name", "lat", "lon", "active")},
    )
    with engine.begin() as conn:
        conn.execute(statement)
    logger.info("stations: upserted %d (%d active)", len(rows), sum(s.active for s in stations))
    return len(rows)


def nearest_active(session: Session, lat: float, lon: float) -> tuple[Station, float]:
    """Nearest active station by haversine — ~100 rows, plain Python is fine."""
    from cloudy.core.geo import haversine_km

    stations = session.exec(select(Station).where(Station.active)).all()
    if not stations:
        raise LookupError("no stations ingested — run: cloudy ingest stations")
    best = min(stations, key=lambda s: haversine_km(lat, lon, s.lat, s.lon))
    return best, haversine_km(lat, lon, best.lat, best.lon)


def active_within_radius(
    session: Session, lat: float, lon: float, radius_km: float
) -> list[tuple[Station, float]]:
    """Active stations within `radius_km`, nearest first (each with its distance).

    The cloud distance filter pools these into one area normal. Stations are
    sparse (~30 km apart), so a small radius can return nothing — the caller falls
    back to the single nearest so the chart is never empty. Same plain-Python
    haversine as nearest_active; ~100 rows makes a query needless.
    """
    from cloudy.core.geo import haversine_km

    stations = session.exec(select(Station).where(Station.active)).all()
    if not stations:
        raise LookupError("no stations ingested — run: cloudy ingest stations")
    within = [
        (s, dist) for s in stations if (dist := haversine_km(lat, lon, s.lat, s.lon)) <= radius_km
    ]
    return sorted(within, key=lambda pair: pair[1])

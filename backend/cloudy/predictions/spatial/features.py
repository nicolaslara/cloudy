"""Spatial helpers: pick the stations nearest a point and load their weekly cloud.

The estimators in `statistical.py` answer "what is the cloud at an arbitrary point,
which isn't a station?" from the *other* stations around it. This module gives them
the two ingredients: the nearest stations to a coordinate, and the weekly-mean cloud
history per station. The loaders touch the database; the ranking is a pure function,
so it stays testable without a Postgres round-trip.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Engine, text
from sqlmodel import Session, select

from cloudy.core.geo import haversine_km
from cloudy.db.models import Station

# How many nearest stations describe a point. Five is enough to triangulate (and to
# survive a couple of them having a data gap that week) without reaching across the
# country into weather that has nothing to do with the target.
DEFAULT_NEIGHBOURS = 5

# Weekly mean cloud per station, keyed by the Monday of each ISO week. We bucket into
# per-station dicts in Python. NULLs are excluded from the mean, so a week with any
# readings still produces a value. `{station_filter}` narrows the scan to a given set
# of stations: a point estimate only needs its handful of nearest neighbours, and
# scanning the whole ~10M-row archive to then discard 100+ stations is what made the
# /predictions/spatial call seconds-slow on the serving DB.
_WEEKLY_STATION_SQL = """
    SELECT station_id,
           date_trunc('week', ts_utc)::date AS week_start,
           avg(cloud_pct) AS mean_cloud
    FROM cloud_hourly
    WHERE cloud_pct IS NOT NULL
      {station_filter}
    GROUP BY station_id, week_start
"""

# station_id -> {week_start: weekly-mean cloud %}.
WeeklyByStation = dict[int, dict[date, float]]


@dataclass(frozen=True)
class StationPoint:
    """A station as a bare location — what the nearest-neighbour ranking works over."""

    id: int
    name: str
    lat: float
    lon: float


def load_weekly_station_cloud(
    engine: Engine, station_ids: Sequence[int] | None = None
) -> WeeklyByStation:
    """Weekly-mean SMHI station cloud, keyed by each ISO-week Monday.

    Pass `station_ids` to load only those stations (the point estimators want just the
    nearest neighbours); `None` keeps the all-stations load for any caller that truly
    needs the whole country. An empty list is a no-op — no stations, no rows. Station
    ids are our own ints, so they inline safely and sidestep the expanding-bindparam
    dance an IN clause would otherwise need.
    """
    if station_ids is None:
        station_filter = ""
    elif len(station_ids) == 0:
        return {}
    else:
        ids = ", ".join(str(int(i)) for i in station_ids)
        station_filter = f"AND station_id IN ({ids})"
    sql = _WEEKLY_STATION_SQL.format(station_filter=station_filter)
    by_station: WeeklyByStation = {}
    with engine.connect() as conn:
        for row in conn.execute(text(sql)):
            by_station.setdefault(row.station_id, {})[row.week_start] = float(row.mean_cloud)
    return by_station


def load_active_points(engine: Engine) -> list[StationPoint]:
    """Every active station as a location, ordered by id for a stable layout."""
    with Session(engine) as session:
        stations = session.exec(select(Station).where(Station.active)).all()
    # Sort in Python (a stable, id-ordered layout) rather than SQL ORDER BY — the
    # SQLModel int primary key isn't a column expression mypy will accept there.
    points = [StationPoint(id=s.id, name=s.name, lat=s.lat, lon=s.lon) for s in stations]
    return sorted(points, key=lambda p: p.id)


def nearest_station_neighbours(
    points: list[StationPoint], lat: float, lon: float, k: int = DEFAULT_NEIGHBOURS
) -> list[tuple[int, float]]:
    """The `k` nearest stations to an arbitrary (lat, lon) as (id, distance_km), nearest first.

    The point is a user's free-floating coordinate, not a station, so there is nothing
    to exclude — every station is a candidate. Haversine, nearest-first, capped at k.
    """
    ranked = sorted(
        ((p.id, haversine_km(lat, lon, p.lat, p.lon)) for p in points),
        key=lambda pair: pair[1],
    )
    return ranked[:k]

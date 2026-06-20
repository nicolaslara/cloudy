"""Statistical estimators of the week-of-year cloud normal at an arbitrary point.

Someone's coordinate is rarely a station, so we estimate "typical cloud here" from
the *other* stations around it. Two rungs, increasing in pooling but both parameter-
free and served straight from the live SMHI station history — no trained model, no
teacher source:

  - ``NEAREST_MODEL`` quotes the single closest station's own week-of-year normal —
    the product's honest "nearest station, X km away", made into a curve.
  - ``KNN_MODEL`` blends the k nearest stations' normals, weighting each by inverse
    distance so a closer station counts more — which beat a plain equal-weight average
    on the leave-station-out benchmark (see ``predictions/spatial/benchmark``).

Both reuse the same neighbour selection (`features.nearest_station_neighbours`) so
the two estimates are drawn from the same stations and read as a progression. Each
station's normal is the mean of its weekly cloud grouped by ISO week-of-year over
all the years we hold — the same "typical year" the climatology product draws, just
per station.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Engine

from cloudy.predictions.spatial import features

# The two statistical ways to estimate the week-of-year normal at a point: NEAREST is
# the single closest station's normal (the most basic point estimate), KNN is the
# inverse-distance-weighted average of the k nearest stations' normals (a closer
# station counts more). Both reuse the same neighbour selection so the estimates are
# drawn from the same stations.
NEAREST_MODEL = "nearest"
KNN_MODEL = "knn"
# Every spatial-normal estimator the /predictions/spatial route can serve, increasing
# in pooling: nearest station -> kNN average.
SPATIAL_MODELS = (NEAREST_MODEL, KNN_MODEL)


@dataclass(frozen=True)
class SpatialNormalPoint:
    """One week-of-year slot of the estimated normal curve (week 1..53)."""

    week: int
    estimated_cloud_pct: float


@dataclass(frozen=True)
class SpatialStationMeta:
    """The nearest station used, surfaced so the UI can name the anchor location."""

    station_id: int
    name: str
    distance_km: float


@dataclass(frozen=True)
class SpatialNormalResult:
    """A point's estimated week-of-year cloud normal plus the provenance the UI shows."""

    lat: float
    lon: float
    nearest_station: SpatialStationMeta
    n_neighbours: int
    series: list[SpatialNormalPoint]


def estimate_statistical_normal(
    engine: Engine, lat: float, lon: float, *, pool: str
) -> SpatialNormalResult:
    """Estimate the week-of-year cloud normal at (lat, lon) by plain statistics.

    The two rungs, sharing their neighbour selection so the estimates compare
    like-for-like:

      - ``NEAREST_MODEL`` uses only the single closest station — the most basic "what
        does the nearest place look like" estimate.
      - ``KNN_MODEL`` blends the k nearest stations' week-of-year normals, weighting
        each by inverse distance so a closer station counts more.

    Each station's normal is the mean of its weekly cloud grouped by ISO week-of-year
    over all the years we hold. A week a station never observed simply doesn't
    contribute; a week no selected station covers is absent from the series (the UI
    shows a gap, not a zero).
    """
    points = features.load_active_points(engine)
    if not points:
        raise LookupError("no active stations — ingest the station registry first")
    neighbours = features.nearest_station_neighbours(points, lat, lon)
    by_id = {p.id: p for p in points}
    nearest_id, nearest_distance = neighbours[0]
    nearest = by_id[nearest_id]
    selected = neighbours[:1] if pool == NEAREST_MODEL else neighbours

    # Load weekly history for only the stations we'll actually pool — never the whole
    # country — so a single point estimate doesn't scan the entire cloud archive.
    station_weekly = features.load_weekly_station_cloud(
        engine, [station_id for station_id, _ in selected]
    )
    # Each selected station's own week-of-year normal, then blended across stations by
    # inverse distance per week — a closer station counts more, and a station
    # contributes to a week only where it has one. (For NEAREST the single station's
    # weight cancels, so it reduces to that station's own normal.)
    week_wsum: dict[int, float] = {}
    week_weight: dict[int, float] = {}
    for station_id, distance in selected:
        weight = 1.0 / max(distance, 1.0)
        for week, mean in _station_week_of_year_normal(station_weekly.get(station_id, {})).items():
            week_wsum[week] = week_wsum.get(week, 0.0) + weight * mean
            week_weight[week] = week_weight.get(week, 0.0) + weight
    if not week_wsum:
        raise LookupError("no neighbour cloud history near this location")

    series = [
        SpatialNormalPoint(
            week=week, estimated_cloud_pct=round(week_wsum[week] / week_weight[week], 1)
        )
        for week in sorted(week_wsum)
    ]
    return SpatialNormalResult(
        lat=lat,
        lon=lon,
        nearest_station=SpatialStationMeta(
            station_id=nearest.id,
            name=nearest.name,
            distance_km=round(nearest_distance, 1),
        ),
        n_neighbours=len(selected),
        series=series,
    )


def _station_week_of_year_normal(weekly: dict[date, float]) -> dict[int, float]:
    """Collapse one station's weekly cloud (keyed by week-start) to a 1..53 normal."""
    total: dict[int, float] = {}
    count: dict[int, int] = {}
    for week_start, mean in weekly.items():
        week = week_start.isocalendar().week
        total[week] = total.get(week, 0.0) + mean
        count[week] = count.get(week, 0) + 1
    return {week: total[week] / count[week] for week in total}

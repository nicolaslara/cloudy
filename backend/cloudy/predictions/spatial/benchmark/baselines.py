"""The free, parameter-free spatial baselines the learned model had to beat.

Every estimate for a held-out station is built only from its *neighbours* — other
stations — exactly as we would predict a user's point with no station of its own. A
station is never its own neighbour (`nearest_neighbours` excludes the origin), so
leave-station-out falls out of the data shape: a sample's inputs can never include
its own target.

Three contemporaneous predictors (they read the neighbours' cloud *this same week*):

  - ``nearest_station``  — the nearest neighbour that reported that week. The
    product's old "nearest station, X km away" cop-out, the bar to beat.
  - ``equal_weight``     — plain mean of the neighbours present that week.
  - ``inverse_distance`` — distance-weighted mean of the same neighbours; closer
    stations count more. This is the maths the shipped kNN serves
    (``statistical.KNN_MODEL``), measured here on the weekly target.

The database loaders live in the serving ``features`` module; this file only adds the
leave-station-out neighbour ranking and the (location, week) sample assembly the
predictors are scored over. Nothing here is on the serving path.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from statistics import fmean

from sqlalchemy import Engine

from cloudy.core.geo import haversine_km
from cloudy.predictions.spatial import features
from cloudy.predictions.spatial.features import StationPoint, WeeklyByStation

# k nearest neighbours describe a point — the same default the serving estimate uses.
DEFAULT_NEIGHBOURS = features.DEFAULT_NEIGHBOURS

# A predictor maps a sample to an estimate of the cloud there, or None when it can't
# answer (every neighbour missing that week). None-answers are skipped, not scored as
# zero, so a predictor is judged only where it actually commits.
Predictor = Callable[["SpatialSample"], "float | None"]

# station_id -> {week-of-year: mean cloud %} — a station's own seasonal normal.
WeekOfYearNormals = dict[int, dict[int, float]]


@dataclass(frozen=True)
class SpatialSample:
    """One (location, week) example: the truth to predict, and only what predicts it.

    ``neighbour_*`` are aligned tuples for the k nearest *other* stations, nearest
    first: the static distance to each and that station's weekly cloud for this week
    (None where the neighbour had no reading). ``target_cloud`` is the held-out
    station's own observed cloud here — label and scoring only, never an input.
    """

    station_id: int
    week_start: date
    week_of_year: int
    lat: float
    lon: float
    target_cloud: float
    neighbour_ids: tuple[int, ...]
    neighbour_distance_km: tuple[float, ...]
    neighbour_cloud: tuple[float | None, ...]


def nearest_neighbours(
    points: Sequence[StationPoint], k: int = DEFAULT_NEIGHBOURS
) -> dict[int, list[tuple[int, float]]]:
    """For each point, the ``k`` nearest *other* points as (id, distance_km), nearest first.

    The origin is filtered out, which is the mechanical root of leave-station-out: a
    sample for station S can only ever reference other stations. Distances are static
    (stations don't move), so this is computed once and reused across every week and
    every estimator. Shared by the baselines here and the GBM feature frame, so the two
    are measured on exactly the same neighbour geometry.
    """
    neighbours: dict[int, list[tuple[int, float]]] = {}
    for origin in points:
        ranked = sorted(
            (
                (other.id, haversine_km(origin.lat, origin.lon, other.lat, other.lon))
                for other in points
                if other.id != origin.id
            ),
            key=lambda pair: pair[1],
        )
        neighbours[origin.id] = ranked[:k]
    return neighbours


def build_samples(
    points: Sequence[StationPoint],
    neighbours: dict[int, list[tuple[int, float]]],
    station_weekly: WeeklyByStation,
) -> list[SpatialSample]:
    """One sample per (station, week) the held-out station observed. Pure over dicts.

    The target is the station's OWN observed cloud that week; the inputs are the
    contemporaneous cloud at each fixed neighbour (None where missing). A station is
    never its own neighbour, so the target can never leak into the features.
    """
    samples: list[SpatialSample] = []
    for point in points:
        own_weeks = station_weekly.get(point.id, {})
        ranked = neighbours.get(point.id, [])
        neighbour_ids = tuple(nid for nid, _ in ranked)
        neighbour_distance_km = tuple(dist for _, dist in ranked)
        for week_start, target_cloud in own_weeks.items():
            neighbour_cloud = tuple(
                station_weekly.get(nid, {}).get(week_start) for nid in neighbour_ids
            )
            samples.append(
                SpatialSample(
                    station_id=point.id,
                    week_start=week_start,
                    week_of_year=week_start.isocalendar().week,
                    lat=point.lat,
                    lon=point.lon,
                    target_cloud=target_cloud,
                    neighbour_ids=neighbour_ids,
                    neighbour_distance_km=neighbour_distance_km,
                    neighbour_cloud=neighbour_cloud,
                )
            )
    return samples


def build_from_engine(engine: Engine, k: int = DEFAULT_NEIGHBOURS) -> list[SpatialSample]:
    """Load points + weekly history (serving loaders) and assemble the full sample set."""
    points = features.load_active_points(engine)
    neighbours = nearest_neighbours(points, k)
    station_weekly = features.load_weekly_station_cloud(engine)
    return build_samples(points, neighbours, station_weekly)


def week_of_year_normals(weekly: WeeklyByStation) -> WeekOfYearNormals:
    """Per station, the mean cloud for each week-of-year across all its years."""
    normals: WeekOfYearNormals = {}
    for station_id, weeks in weekly.items():
        by_woy: dict[int, list[float]] = {}
        for week_start, value in weeks.items():
            by_woy.setdefault(week_start.isocalendar().week, []).append(value)
        normals[station_id] = {woy: fmean(values) for woy, values in by_woy.items()}
    return normals


def nearest_station(sample: SpatialSample) -> float | None:
    """Quote the nearest neighbour that has a reading this week — the bar to beat."""
    for cloud in sample.neighbour_cloud:
        if cloud is not None:
            return cloud
    return None


def equal_weight(sample: SpatialSample) -> float | None:
    """Plain mean of the neighbours present this week — kNN with no distance weighting."""
    present = [cloud for cloud in sample.neighbour_cloud if cloud is not None]
    return fmean(present) if present else None


def inverse_distance(sample: SpatialSample) -> float | None:
    """Inverse-distance-weighted mean of the neighbours — the sensible free interpolation.

    Closer stations count more (weight 1/distance, floored so a near-coincident station
    can't dominate to infinity). Parameter-free and contemporaneous.
    """
    weighted_sum = 0.0
    weight_total = 0.0
    pairs = zip(sample.neighbour_cloud, sample.neighbour_distance_km, strict=True)
    for cloud, distance_km in pairs:
        if cloud is None:
            continue
        weight = 1.0 / max(distance_km, 1.0)
        weighted_sum += weight * cloud
        weight_total += weight
    return weighted_sum / weight_total if weight_total else None

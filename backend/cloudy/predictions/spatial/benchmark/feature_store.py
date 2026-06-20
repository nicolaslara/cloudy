"""The spatial feature frame for the learned model — one wide table, built in memory.

One row per (held-out station, week): the truth to predict plus every candidate
feature, so the leave-station-out CV in ``model`` can fit and score the GBM. It is built
from the SAME weekly station cloud the baselines and the serving estimate use
(``features.load_weekly_station_cloud`` — a ``date_trunc('week')`` mean), so the model
and the baselines are graded on one consistent grain: no train/serve resampling skew,
and the same handful of weekly rows everything else reads (not a fresh ~10M-row hourly
scan).

The truth is honest: each held-out station's target is its OWN observed weekly cloud,
and its features are drawn only from *other* stations — exactly what we would have for a
user's point with no station of its own. There is no teacher source (no ERA5): every
feature is live SMHI station data.

Columns are named by group prefix so ``model`` can keep the keys out of the inputs:

  - ``target_cloud``  the label: the station's own observed weekly cloud.
  - ``season_*``      cyclic annual phase (sin/cos of day-of-year).
  - ``geo_*``         the point's static location.
  - ``nbr{i}_*``      the i-th nearest *other* station: cloud, distance, bearing.

This is the benchmark/lab path: it is never imported by the serving estimate
(``spatial.statistical``), and its deps (pandas/numpy/lightgbm) are dev-only.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sqlalchemy import Engine

from cloudy.core.geo import initial_bearing_deg
from cloudy.predictions.spatial import features
from cloudy.predictions.spatial.benchmark.baselines import nearest_neighbours
from cloudy.predictions.spatial.features import StationPoint, WeeklyByStation


@dataclass(frozen=True)
class FeatureConfig:
    """What to extract. The served grain is weekly; k=5 nearest neighbours per point."""

    n_neighbours: int = 5


def build_feature_frame(engine: Engine, config: FeatureConfig) -> pd.DataFrame:
    """Assemble the wide (location, week) feature table for the leave-station-out CV."""
    points = features.load_active_points(engine)
    by_id = {p.id: p for p in points}
    neighbours = nearest_neighbours(points, config.n_neighbours)

    # The same weekly station cloud the baselines and the serving kNN read — one grain
    # for the whole benchmark. It is both the neighbour signal and the held-out
    # station's own observed truth.
    station_cloud = _wide_weekly(features.load_weekly_station_cloud(engine))
    if station_cloud.empty:
        return pd.DataFrame()

    with_truth = {int(sid) for sid in station_cloud.columns}
    frames = [
        _frame_for_point(p, neighbours[p.id], by_id, station_cloud)
        for p in points
        if p.id in with_truth
    ]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _wide_weekly(weekly: WeeklyByStation) -> pd.DataFrame:
    """One column per station, indexed by the ISO-week Monday — the date_trunc weekly mean.

    Empty in -> empty out (a no-history serving DB short-circuits to an empty frame).
    """
    if not weekly:
        return pd.DataFrame()
    wide = pd.DataFrame({sid: pd.Series(weeks) for sid, weeks in weekly.items()})
    wide.index = pd.to_datetime(wide.index)
    return wide.sort_index()


def _frame_for_point(
    point_info: StationPoint,
    neighbours: list[tuple[int, float]],
    by_id: dict[int, StationPoint],
    station_cloud: pd.DataFrame,
) -> pd.DataFrame:
    """One point's rows: target + season + geo + neighbour features.

    The held-out station is predicted purely from *other* stations, so its own cloud
    appears only as the label, never as an input. Weeks with no observed cloud are
    dropped — we only learn where we can score.
    """
    sid = point_info.id
    frame = pd.DataFrame(index=station_cloud.index)
    frame["target_cloud"] = station_cloud[sid]
    _write_neighbour_columns(
        frame, point_info.lat, point_info.lon, neighbours, by_id, station_cloud
    )
    frame["geo_lat"] = point_info.lat
    frame["geo_lon"] = point_info.lon
    _write_season(frame)
    frame["station_id"] = sid
    frame["valid_time"] = station_cloud.index
    return frame[frame["target_cloud"].notna()].reset_index(drop=True)


def _write_neighbour_columns(
    frame: pd.DataFrame,
    point_lat: float,
    point_lon: float,
    neighbours: list[tuple[int, float]],
    by_id: dict[int, StationPoint],
    station_cloud: pd.DataFrame,
) -> None:
    """Write the nbr{i}_* feature columns onto ``frame``, in place.

    For each of the k nearest stations: its weekly cloud (reindexed onto the frame's
    week index, NaN where it has no reading), its static distance, and the bearing from
    the point toward it (the direction its cloud must travel).
    """
    index = frame.index
    for i, (neighbour_id, distance_km) in enumerate(neighbours):
        has_cloud = neighbour_id in station_cloud.columns
        column = station_cloud[neighbour_id].reindex(index) if has_cloud else None
        neighbour = by_id[neighbour_id]
        bearing = initial_bearing_deg(point_lat, point_lon, neighbour.lat, neighbour.lon)
        frame[f"nbr{i}_cloud"] = column if column is not None else np.nan
        frame[f"nbr{i}_dist_km"] = distance_km
        frame[f"nbr{i}_bearing_deg"] = bearing


def _write_season(frame: pd.DataFrame) -> None:
    """Cyclic annual season features from the weekly index's day-of-year."""
    index = pd.DatetimeIndex(frame.index)
    day_of_year = index.dayofyear.to_numpy(dtype=float)
    frame["season_doy_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
    frame["season_doy_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)


def feature_columns(df: pd.DataFrame) -> list[str]:
    """The model input columns: everything except the label and the keys."""
    non_features = {"target_cloud", "station_id", "valid_time"}
    return [column for column in df.columns if column not in non_features]


def with_week_of_year(df: pd.DataFrame, column: str = "valid_time") -> list[int]:
    """The ISO week-of-year for each row, used to collapse predictions to a normal curve."""
    return [int(week) for week in pd.DatetimeIndex(df[column]).isocalendar().week]

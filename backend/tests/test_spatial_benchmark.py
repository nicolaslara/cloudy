"""Tests for the dropped spatial GBM benchmark (the lab harness, not the served kNN).

Pure over hand-built points/samples — no database — so they pin the leave-station-out
guardrail, the baseline arithmetic, and the significance verdict. The LightGBM cross-
validation gets a small smoke test, skipped when lightgbm isn't installed.
"""

from __future__ import annotations

from datetime import date

import pytest

from cloudy.predictions.spatial.benchmark import baselines, significance
from cloudy.predictions.spatial.benchmark.baselines import SpatialSample
from cloudy.predictions.spatial.features import StationPoint

_POINTS = [
    StationPoint(1, "A", 59.0, 18.0),
    StationPoint(2, "B", 59.2, 18.1),
    StationPoint(3, "C", 59.6, 18.0),
    StationPoint(4, "D", 58.5, 17.5),
]


def test_nearest_neighbours_excludes_self_and_orders_by_distance() -> None:
    """The origin is never its own neighbour — the mechanical root of leave-station-out."""
    neighbours = baselines.nearest_neighbours(_POINTS, k=3)
    for origin_id, ranked in neighbours.items():
        ids = [nid for nid, _ in ranked]
        assert origin_id not in ids  # never itself
        distances = [dist for _, dist in ranked]
        assert distances == sorted(distances)  # nearest first
    # Station 1's nearest is 2 (closest), and it keeps at most k.
    assert neighbours[1][0][0] == 2
    assert len(neighbours[1]) == 3


def test_build_samples_is_leave_station_out() -> None:
    """A sample's target is the station's own cloud; its inputs are only other stations."""
    week = date(2021, 1, 4)  # Monday, ISO week 1
    weekly = {1: {week: 40.0}, 2: {week: 50.0}, 3: {week: 60.0}, 4: {week: 70.0}}
    neighbours = baselines.nearest_neighbours(_POINTS, k=3)
    samples = baselines.build_samples(_POINTS, neighbours, weekly)

    one = next(s for s in samples if s.station_id == 1)
    assert one.target_cloud == 40.0  # its OWN observed cloud
    assert 1 not in one.neighbour_ids  # never sees itself as a neighbour
    assert one.week_of_year == 1
    # neighbour_cloud is aligned to neighbour_ids, this same week.
    assert one.neighbour_cloud == tuple(weekly[nid][week] for nid in one.neighbour_ids)


def _sample(
    neighbour_cloud: tuple[float | None, ...], distances: tuple[float, ...]
) -> SpatialSample:
    return SpatialSample(
        station_id=1,
        week_start=date(2021, 1, 4),
        week_of_year=1,
        lat=59.0,
        lon=18.0,
        target_cloud=0.0,
        neighbour_ids=tuple(range(2, 2 + len(distances))),
        neighbour_distance_km=distances,
        neighbour_cloud=neighbour_cloud,
    )


def test_contemporaneous_baselines() -> None:
    """nearest = first present; equal-weight = plain mean; IDW weights 1/distance."""
    sample = _sample((None, 50.0, 70.0), (10.0, 20.0, 30.0))
    assert baselines.nearest_station(sample) == 50.0  # the first neighbour that reported
    assert baselines.equal_weight(sample) == 60.0  # mean(50, 70)
    # IDW: (50/20 + 70/30) / (1/20 + 1/30) = 58.0
    assert baselines.inverse_distance(sample) == pytest.approx(58.0)


def test_all_neighbours_missing_gives_none() -> None:
    sample = _sample((None, None), (10.0, 20.0))
    assert baselines.nearest_station(sample) is None
    assert baselines.equal_weight(sample) is None
    assert baselines.inverse_distance(sample) is None


def test_significance_flags_a_real_gap_and_a_tie() -> None:
    """A consistent edge is significant; a symmetric wash straddles zero (a tie)."""
    better = significance.compare({1: 1.0, 2: 1.0, 3: 1.0}, {1: 2.0, 2: 2.0, 3: 2.0})
    assert better.win_pct == 100.0
    assert better.median_delta == -1.0
    assert better.significant  # CI well below zero

    tie = significance.compare({1: 1.0, 2: 3.0, 3: 2.0}, {1: 3.0, 2: 1.0, 3: 2.0})
    assert tie.median_delta == 0.0
    assert not tie.significant  # CI straddles zero


def test_significance_is_deterministic() -> None:
    """Same seed -> same bootstrap CI, so the committed verdict is reproducible."""
    method = {i: float(i % 5) for i in range(40)}
    reference = {i: float((i + 2) % 5) for i in range(40)}
    first = significance.compare(method, reference)
    second = significance.compare(method, reference)
    assert (first.ci_low, first.ci_high) == (second.ci_low, second.ci_high)


def test_grouped_folds_are_leave_station_out() -> None:
    """Every fold's train and test stations are disjoint (numpy-only, no lightgbm)."""
    import numpy as np

    from cloudy.predictions.spatial.benchmark import model

    station_ids = np.array([1, 1, 2, 2, 3, 3, 4, 4, 5, 5])
    folds = list(model.grouped_folds(station_ids, n_folds=5))
    assert len(folds) == 5
    for train_mask, test_mask in folds:
        assert set(station_ids[train_mask]).isdisjoint(set(station_ids[test_mask]))


def test_cross_val_predict_smoke() -> None:
    """LightGBM out-of-fold predictions are finite and one per row. Skipped without lightgbm."""
    pytest.importorskip("lightgbm")
    import numpy as np
    import pandas as pd

    from cloudy.predictions.spatial.benchmark import feature_store, model

    rows = [
        {
            "station_id": sid,
            "valid_time": pd.Timestamp("2021-01-04") + pd.Timedelta(weeks=w),
            "target_cloud": 40.0 + 2 * sid + w,
            "nbr0_cloud": 39.0 + 2 * sid + w,
            "nbr0_dist_km": 10.0,
            "nbr0_bearing_deg": 90.0,
            "geo_lat": 59.0 + 0.1 * sid,
            "geo_lon": 18.0,
            "season_doy_sin": 0.1,
            "season_doy_cos": 0.2,
        }
        for sid in range(1, 7)
        for w in range(12)
    ]
    df = pd.DataFrame(rows)
    predictions = model.cross_val_predict(df, feature_store.feature_columns(df), n_folds=3)
    assert len(predictions) == len(df)
    assert np.isfinite(predictions).all()

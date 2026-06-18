"""Tests for the statistical spatial estimators (nearest / kNN week-of-year normals).

Pure over stubbed loaders — no database — so they pin the pooling arithmetic and the
neighbour selection that makes the two rungs read as a progression.
"""

from __future__ import annotations

import pytest

from cloudy.predictions.spatial import features, statistical
from cloudy.predictions.spatial.features import StationPoint

_POINTS = [
    StationPoint(1, "A", 59.0, 18.0),
    StationPoint(2, "B", 59.5, 18.2),
    StationPoint(3, "C", 60.0, 18.0),
    StationPoint(4, "D", 58.5, 17.5),
    StationPoint(5, "E", 59.1, 18.9),
    StationPoint(6, "F", 60.5, 19.0),
]


def test_statistical_normal_nearest_uses_only_the_closest_station(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`nearest` is the single closest station's week-of-year normal — no pooling.

    Pure over stubbed loaders: one ISO week, a distinct constant per station, so the
    nearest model must return exactly the closest station's value and n_neighbours==1.
    """
    from datetime import date

    values = {1: 40.0, 2: 50.0, 3: 60.0, 4: 70.0, 5: 80.0, 6: 90.0}
    week_start = date(2021, 1, 4)  # a Monday, ISO week 1
    weekly = {sid: {week_start: values[sid]} for sid in values}
    requested: dict[str, object] = {}
    monkeypatch.setattr(features, "load_active_points", lambda engine: _POINTS)
    monkeypatch.setattr(
        features,
        "load_weekly_station_cloud",
        lambda engine, station_ids=None: (requested.update(ids=station_ids), weekly)[1],
    )

    order = features.nearest_station_neighbours(_POINTS, 59.0, 18.0)
    result = statistical.estimate_statistical_normal(
        None,  # type: ignore[arg-type]
        59.0,
        18.0,
        pool=statistical.NEAREST_MODEL,
    )

    assert result.n_neighbours == 1
    assert [p.week for p in result.series] == [1]
    assert result.series[0].estimated_cloud_pct == round(values[order[0][0]], 1)
    assert result.nearest_station.station_id == order[0][0]
    # nearest loads exactly the one closest station, not the whole country.
    assert requested["ids"] == [order[0][0]]


def test_statistical_normal_knn_averages_the_neighbours_equally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`knn` is the equal-weight mean of the k nearest stations' week-of-year normals."""
    from datetime import date

    values = {1: 40.0, 2: 50.0, 3: 60.0, 4: 70.0, 5: 80.0, 6: 90.0}
    week_start = date(2021, 1, 4)
    weekly = {sid: {week_start: values[sid]} for sid in values}
    requested: dict[str, object] = {}
    monkeypatch.setattr(features, "load_active_points", lambda engine: _POINTS)
    monkeypatch.setattr(
        features,
        "load_weekly_station_cloud",
        lambda engine, station_ids=None: (requested.update(ids=station_ids), weekly)[1],
    )

    order = features.nearest_station_neighbours(_POINTS, 59.0, 18.0)  # k=5 of the 6 points
    result = statistical.estimate_statistical_normal(
        None,  # type: ignore[arg-type]
        59.0,
        18.0,
        pool=statistical.KNN_MODEL,
    )

    assert result.n_neighbours == len(order) == 5
    expected = round(sum(values[sid] for sid, _ in order) / len(order), 1)
    assert result.series[0].estimated_cloud_pct == expected
    # kNN loads exactly the k selected neighbours (not the 6th, farther station).
    assert requested["ids"] == [sid for sid, _ in order]


def test_statistical_normal_raises_without_neighbour_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No cloud for any neighbour is a precondition (LookupError -> 503), not an empty 200."""
    monkeypatch.setattr(features, "load_active_points", lambda engine: _POINTS)
    monkeypatch.setattr(features, "load_weekly_station_cloud", lambda engine, station_ids=None: {})
    with pytest.raises(LookupError, match="no neighbour cloud history"):
        statistical.estimate_statistical_normal(
            None,  # type: ignore[arg-type]
            59.0,
            18.0,
            pool=statistical.KNN_MODEL,
        )

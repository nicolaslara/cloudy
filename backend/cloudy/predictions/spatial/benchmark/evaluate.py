"""Honest leave-station-out evaluation of the spatial GBM vs the free baselines.

Produces the static ``spatial_backtest.json`` evidence the deck cites: on two tasks,
graded against each held-out station's own SMHI observations, how the learned model
compares to the parameter-free averages.

  - NORMAL task: estimate the station's seasonal week-of-year normal — the job the
    shipped spatial estimate actually does. Truth is the station's own woy normal.
  - WEEKLY task: predict the station's actual weekly cloud from neighbours' same-week
    readings — a harder contemporaneous interpolation. Truth is the weekly observation.

The shipped estimate is the equal-weight kNN of neighbours' woy normals
(``statistical.KNN_MODEL``). On the NORMAL task we report each estimator's paired
comparison against it (median delta, win rate, bootstrap CI) — the "is the GBM gain
real?" verdict that the slide's tie table shows. Run once via ``cloudy spatial-backtest``
and written to disk; nothing here is on the serving path.

Every estimator here reads the SAME weekly station cloud (``date_trunc('week')`` mean
from ``features.load_weekly_station_cloud``), so the model and the baselines are graded
on one grain — the train/serve resampling skew the earlier harness carried (PHASE-B
error budget, §5) is gone by construction.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from statistics import fmean, median
from typing import Any

from sqlalchemy import Engine

from cloudy.predictions.spatial import features
from cloudy.predictions.spatial.benchmark import baselines, feature_store, model, significance
from cloudy.predictions.spatial.benchmark.baselines import (
    Predictor,
    SpatialSample,
    WeekOfYearNormals,
)

MODEL_ID = "spatial-smhi"
# The shipped spatial estimate: inverse-distance kNN of the neighbours' woy normals.
# Every "is the model actually better?" comparison is measured against this.
SHIPPED = "knn_idw"

# station_id -> mean absolute error (pp) for one estimator on one task.
PerStation = dict[int, float]


def spatial_scorecard(engine: Engine) -> dict[str, Any]:
    """The spatial benchmark as a servable artifact: both tasks, all estimators, the tie test."""
    points = features.load_active_points(engine)
    weekly = features.load_weekly_station_cloud(engine)
    neighbours = baselines.nearest_neighbours(points)
    normals = baselines.week_of_year_normals(weekly)
    samples = baselines.build_samples(points, neighbours, weekly)

    df = feature_store.build_feature_frame(engine, feature_store.FeatureConfig())
    if df.empty:
        raise LookupError("no spatial feature rows — ingest SMHI cloud first")
    predictions = model.cross_val_predict(df, feature_store.feature_columns(df))
    week_of_year = feature_store.with_week_of_year(df)
    gbm_weekly, gbm_normal = _gbm_per_station(df, predictions, week_of_year, normals)

    normal_task = {
        "nearest": _normal_mae(points, neighbours, normals, _nearest_normal),
        "knn_equalweight": _normal_mae(points, neighbours, normals, _equal_weight_normal),
        "knn_idw": _normal_mae(points, neighbours, normals, _inverse_distance_normal),
        "gbm": gbm_normal,
    }
    weekly_task = {
        "nearest": _weekly_mae(samples, baselines.nearest_station),
        "knn_equalweight": _weekly_mae(samples, baselines.equal_weight),
        "knn_idw": _weekly_mae(samples, baselines.inverse_distance),
        "gbm": gbm_weekly,
    }

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": MODEL_ID,
        "n_stations": len(gbm_weekly),
        "shipped_estimator": SHIPPED,
        # NORMAL is the product's job, so the tie test is measured against the shipped kNN.
        "normal_task": _task_block(
            normal_task, reference=SHIPPED, compared=("nearest", "knn_equalweight", "gbm")
        ),
        # WEEKLY is the harder what-if; the best baseline is inverse-distance, so we ask
        # only whether the model beats *that* (it doesn't).
        "weekly_task": _task_block(weekly_task, reference="knn_idw", compared=("gbm",)),
    }


# --- per-station scoring -------------------------------------------------------


def _weekly_mae(samples: list[SpatialSample], predict: Predictor) -> PerStation:
    """Each station's mean absolute error on the weekly target, leave-station-out."""
    errors: dict[int, list[float]] = {}
    for sample in samples:
        estimate = predict(sample)
        if estimate is None:
            continue
        errors.setdefault(sample.station_id, []).append(abs(estimate - sample.target_cloud))
    return {sid: fmean(errs) for sid, errs in errors.items() if errs}


# A normal-task predictor estimates one week-of-year's normal from the neighbours'
# (distance, that-neighbour's-normal-for-this-week) list, nearest first. A neighbour
# that has never observed this week contributes None.
NormalPredictor = Callable[[list[tuple[float, float | None]]], "float | None"]


def _nearest_normal(ordered: list[tuple[float, float | None]]) -> float | None:
    """The single nearest station's normal for this week (None if it lacks the week)."""
    return ordered[0][1] if ordered else None


def _equal_weight_normal(ordered: list[tuple[float, float | None]]) -> float | None:
    present = [value for _, value in ordered if value is not None]
    return fmean(present) if present else None


def _inverse_distance_normal(ordered: list[tuple[float, float | None]]) -> float | None:
    present = [(dist, value) for dist, value in ordered if value is not None]
    if not present:
        return None
    weights = [1.0 / max(dist, 1.0) for dist, _ in present]
    return sum(w * value for w, (_, value) in zip(weights, present, strict=True)) / sum(weights)


def _normal_mae(
    points: list[features.StationPoint],
    neighbours: dict[int, list[tuple[int, float]]],
    normals: WeekOfYearNormals,
    predict: NormalPredictor,
) -> PerStation:
    """Each station's MAE estimating its OWN woy normal from the neighbours' woy normals."""
    out: PerStation = {}
    for point in points:
        truth = normals.get(point.id)
        neigh = neighbours.get(point.id)
        if not truth or not neigh:
            continue
        errors: list[float] = []
        for woy, true_value in truth.items():
            ordered = [(dist, normals.get(nid, {}).get(woy)) for nid, dist in neigh]
            estimate = predict(ordered)
            if estimate is not None:
                errors.append(abs(estimate - true_value))
        if errors:
            out[point.id] = fmean(errors)
    return out


def _gbm_per_station(
    df: Any, predictions: Any, week_of_year: Any, normals: WeekOfYearNormals
) -> tuple[PerStation, PerStation]:
    """Fold the GBM's out-of-fold predictions into per-station weekly and normal MAE.

    Weekly: mean |pred - obs| over the station's weeks. Normal: collapse the weekly
    predictions to a week-of-year mean (the predicted normal curve) and score it against
    the station's own observed woy normal — the same truth the baselines use.
    """
    weekly_err: dict[int, list[float]] = {}
    predicted_by_woy: dict[int, dict[int, list[float]]] = {}
    station_ids = df["station_id"].to_numpy()
    targets = df["target_cloud"].to_numpy()
    for sid, target, pred, woy in zip(station_ids, targets, predictions, week_of_year, strict=True):
        if pred != pred:  # NaN: row a fold never predicted
            continue
        station = int(sid)
        weekly_err.setdefault(station, []).append(abs(float(pred) - float(target)))
        predicted_by_woy.setdefault(station, {}).setdefault(int(woy), []).append(float(pred))

    gbm_weekly = {sid: fmean(errs) for sid, errs in weekly_err.items() if errs}
    gbm_normal: PerStation = {}
    for sid, by_woy in predicted_by_woy.items():
        truth = normals.get(sid)
        if not truth:
            continue
        errors = [abs(fmean(preds) - truth[woy]) for woy, preds in by_woy.items() if woy in truth]
        if errors:
            gbm_normal[sid] = fmean(errors)
    return gbm_weekly, gbm_normal


# --- artifact assembly ---------------------------------------------------------


def _summary(per_station: PerStation) -> dict[str, Any]:
    values = sorted(per_station.values())
    n = len(values)
    return {
        "median_mae": round(median(values), 2),
        "mean_mae": round(fmean(values), 2),
        "p25": round(values[n // 4], 2),
        "p75": round(values[(3 * n) // 4], 2),
        "n_stations": n,
    }


def _task_block(
    per_task: dict[str, PerStation], *, reference: str, compared: tuple[str, ...]
) -> dict[str, Any]:
    """Per-estimator summaries plus each compared estimator's paired test vs the reference."""
    order = ["nearest", "knn_equalweight", "knn_idw", "gbm"]
    estimators = [{"id": key, **_summary(per_task[key])} for key in order if per_task.get(key)]
    ref = per_task[reference]
    comparisons = []
    for key in compared:
        if not per_task.get(key):
            continue
        result = significance.compare(per_task[key], ref)
        comparisons.append(
            {
                "id": key,
                "vs": reference,
                "win_pct": round(result.win_pct, 1),
                "median_delta": round(result.median_delta, 3),
                "ci": [round(result.ci_low, 3), round(result.ci_high, 3)],
                "significant": result.significant,
            }
        )
    return {"estimators": estimators, "comparisons": comparisons}

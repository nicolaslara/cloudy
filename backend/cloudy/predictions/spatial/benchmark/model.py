"""The LightGBM spatial model + its honest leave-station-out cross-validation.

Gradient-boosted trees over the feature frame: hundreds of small trees, each
correcting the last ensemble's error, on a table whose rows are (location, week) and
whose answer is the held-out station's own observed cloud. We score it the only honest
way for a "predict an unseen location" claim — **leave-station-out**: every fold trains
on one group of stations and predicts a *different*, held-out group (grouped K-fold by
``station_id``, not random rows), so the model is never graded on a location it trained
on. The out-of-fold predictions feed ``evaluate``.

``lightgbm`` is imported lazily so importing this package never requires it; the dep is
dev-only (see pyproject ``dev`` group) and only ``cloudy spatial-backtest`` pulls it in.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

import numpy as np
import pandas as pd

# MAE objective so the model optimises the same error the scorecard reports, and
# robust, fast settings sized for ~1e5 rows. verbose=-1 keeps it quiet. Typed Any so
# the **unpack into LGBMRegressor's many typed kwargs satisfies mypy.
DEFAULT_PARAMS: dict[str, Any] = {
    "objective": "regression_l1",
    "n_estimators": 400,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 50,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
}


def grouped_folds(
    station_ids: np.ndarray, n_folds: int = 5
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield (train_mask, test_mask) where each fold's test stations are disjoint.

    Stations are round-robin assigned to folds (sorted for determinism), so a fold's
    held-out locations never appear in its training rows — leave-station-out, the
    spatial generalisation test.
    """
    unique = sorted({int(s) for s in station_ids})
    fold_of = {station: index % n_folds for index, station in enumerate(unique)}
    row_fold = np.array([fold_of[int(s)] for s in station_ids])
    for fold in range(n_folds):
        test_mask = row_fold == fold
        if test_mask.any():
            yield ~test_mask, test_mask


def cross_val_predict(
    df: pd.DataFrame,
    feature_cols: Sequence[str],
    n_folds: int = 5,
    params: dict[str, Any] | None = None,
) -> np.ndarray:
    """Out-of-fold LightGBM predictions under leave-station-out CV.

    NaNs (data gaps, missing neighbours) are passed straight to LightGBM, which routes
    them down a learned default branch — no imputation. DataFrames (not numpy) are kept
    through fit/predict so LightGBM carries the feature names.
    """
    import lightgbm as lgb

    settings: dict[str, Any] = {**DEFAULT_PARAMS, **(params or {})}
    features = df[list(feature_cols)]
    target = df["target_cloud"]
    station_ids = df["station_id"].to_numpy()
    out_of_fold = np.full(len(df), np.nan)
    for train_mask, test_mask in grouped_folds(station_ids, n_folds):
        model = lgb.LGBMRegressor(**settings)
        model.fit(features[train_mask], target[train_mask])
        out_of_fold[test_mask] = model.predict(features[test_mask])
    return out_of_fold


def per_station_median_mae(
    station_ids: np.ndarray, y_true: np.ndarray, y_pred: np.ndarray
) -> float:
    """Median over locations of each location's mean absolute error vs observed truth.

    Aggregate per location first, then take the median — "the typical place", matching
    the baselines' metric so model and baselines compare directly.
    """
    frame = pd.DataFrame({"sid": station_ids, "err": np.abs(y_pred - y_true)}).dropna()
    if frame.empty:
        return float("nan")
    return float(frame.groupby("sid")["err"].mean().median())

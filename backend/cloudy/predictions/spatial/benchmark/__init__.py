"""The dropped learned-spatial-model evidence — a benchmark, not a served model.

This subpackage is the *lab* counterpart to the shipped spatial estimate in
``spatial.statistical`` (the nearest / kNN-of-normals rungs). It exists to answer one
question honestly and reproducibly: does a learned model (LightGBM over the neighbour
geometry) beat the parameter-free kNN average on real station observations? It does
not — it ties on the seasonal-normal task and posts no gain on the harder weekly task
(see ``evaluate.spatial_scorecard`` and the deck's spatial-results slide) — so the
model was dropped and the cheap, explainable kNN ships.

It is kept in the tree so the slide's numbers are reproducible (``cloudy
spatial-backtest`` regenerates the committed artifact), not because anything imports it
at serve time:

  - The serving path (``spatial.statistical`` / ``spatial.features``) NEVER imports this
    subpackage, so the API and the production image carry none of its weight.
  - Its dependencies (lightgbm, pandas, numpy) live in the ``dev`` group only; they are
    excluded from the runtime image (``uv sync --no-dev``) and imported lazily here.
"""

"""The Predictions API: the weekly near-term outlooks + the static leaderboard.

Thin controllers, mirroring climatology/api.py: validate the query (a bad request
becomes a 422), compute the outlook, cache the cheap result. The model's real edge
is the *weekly* outlook — the monthly next-month forecast was honestly marginal and
has been removed. One model forecasts cloud (damped persistence), plus a hedged
lightning line on the same model. The cross-station backtest leaderboard is
read-only — `cloudy backtest` writes it. A missing precondition (no data for the
location) surfaces as LookupError → 503.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from cloudy.config import get_settings
from cloudy.core.cache import get_cache
from cloudy.db import session as db
from cloudy.predictions import outlook
from cloudy.predictions.query import (
    BacktestSeriesQuery,
    PredictionsCloudQuery,
    PredictionsLightningQuery,
    SpatialQuery,
)
from cloudy.predictions.spatial import statistical
from cloudy.predictions.types import (
    BacktestArtifact,
    BacktestSeriesResponse,
    CloudOutlook,
    LightningOutlook,
    PredictionsMeta,
    SpatialNormalResponse,
)

router = APIRouter()

# The outlook only moves when new data is ingested; one-hour TTL matches the rest.
CACHE_TTL_S = 3600


def _meta(sources: list[str]) -> PredictionsMeta:
    return {
        "sources": sources,
        "attribution": "Source: SMHI",
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.get("/predictions/backtest")
def backtest_route() -> BacktestArtifact:
    # Read-only: the cross-station benchmark is written by `cloudy backtest` and
    # committed as a static file shipped with the app, so it serves out of the box.
    # A missing file means the model hasn't been evaluated yet — a precondition
    # (503), not a bad request.
    path = Path(get_settings().predictions_scorecard_path)
    if not path.exists():
        raise HTTPException(503, "model not evaluated yet — run: cloudy backtest")
    return cast(BacktestArtifact, json.loads(path.read_text(encoding="utf-8")))


@router.get("/predictions/outlook")
def outlook_route(
    lat: Annotated[float | None, Query()] = None,
    lon: Annotated[float | None, Query()] = None,
    radius_km: Annotated[int, Query()] = 50,
) -> CloudOutlook:
    try:
        query = PredictionsCloudQuery.model_validate(
            {"lat": lat, "lon": lon, "radius_km": radius_km}
        )
    except ValidationError as exc:
        raise HTTPException(422, _first_error(exc)) from exc

    cache = get_cache()
    # None coords cache under their own key — Sweden-wide never collides with a
    # located query, mirroring the climatology caching convention.
    key = f"pred:outlook:{query.lat}:{query.lon}:{query.radius_km}"
    cached = cache.get(key)
    if cached is not None:
        return cast(CloudOutlook, json.loads(cached))

    try:
        engine = db.get_engine()
        body = outlook.cloud_outlook(
            engine, query.lat, query.lon, float(query.radius_km), meta=_meta(["smhi-metobs"])
        )
    except LookupError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    cache.set(key, json.dumps(body), CACHE_TTL_S)
    return body


@router.get("/predictions/lightning-outlook")
def lightning_outlook_route(
    lat: Annotated[float | None, Query()] = None,
    lon: Annotated[float | None, Query()] = None,
    radius_km: Annotated[int, Query()] = 25,
) -> LightningOutlook:
    try:
        query = PredictionsLightningQuery.model_validate(
            {"lat": lat, "lon": lon, "radius_km": radius_km}
        )
    except ValidationError as exc:
        raise HTTPException(422, _first_error(exc)) from exc

    cache = get_cache()
    key = f"pred:lightning-outlook:{query.lat}:{query.lon}:{query.radius_km}"
    cached = cache.get(key)
    if cached is not None:
        return cast(LightningOutlook, json.loads(cached))

    try:
        engine = db.get_engine()
        body = outlook.lightning_outlook(
            engine, query.lat, query.lon, float(query.radius_km), meta=_meta(["smhi-lightning"])
        )
    except LookupError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    cache.set(key, json.dumps(body), CACHE_TTL_S)
    return body


@router.get("/predictions/backtest-series")
def backtest_series_route(
    lat: Annotated[float | None, Query()] = None,
    lon: Annotated[float | None, Query()] = None,
    radius_km: Annotated[int, Query()] = 50,
    model: Annotated[str, Query()] = "damped",
    lead: Annotated[int, Query()] = 1,
) -> BacktestSeriesResponse:
    # A model's forecast-vs-actual over the rolling-origin backtest at a point (or
    # Sweden-wide). Computed live like the outlooks; cached, since it only moves with
    # new data. A bad coordinate/model/lead is a 422.
    try:
        query = BacktestSeriesQuery.model_validate(
            {"lat": lat, "lon": lon, "radius_km": radius_km, "model": model, "lead": lead}
        )
    except ValidationError as exc:
        raise HTTPException(422, _first_error(exc)) from exc

    cache = get_cache()
    key = (
        f"pred:backtest-series:{query.lat}:{query.lon}:{query.radius_km}:{query.model}:{query.lead}"
    )
    cached = cache.get(key)
    if cached is not None:
        return cast(BacktestSeriesResponse, json.loads(cached))

    try:
        engine = db.get_engine()
        body = cast(
            BacktestSeriesResponse,
            outlook.cloud_backtest_series(
                engine,
                query.lat,
                query.lon,
                float(query.radius_km),
                query.lead,
                meta=_meta(["smhi-metobs"]),
            ),
        )
    except LookupError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    cache.set(key, json.dumps(body), CACHE_TTL_S)
    return body


@router.get("/predictions/spatial")
def spatial_route(
    lat: Annotated[float | None, Query()] = None,
    lon: Annotated[float | None, Query()] = None,
    model: Annotated[str, Query()] = "knn",
) -> SpatialNormalResponse:
    # A point's week-of-year cloud normal, estimated nearest | knn — the two rungs of
    # the spatial ladder, both pure statistics over the nearby SMHI stations. Both
    # coordinates required (no Sweden-wide point estimate), so a lone or missing
    # coordinate (or an unknown model id) is a 422. No data near the point is a
    # precondition (503).
    try:
        query = SpatialQuery.model_validate({"lat": lat, "lon": lon, "model": model})
    except ValidationError as exc:
        raise HTTPException(422, _first_error(exc)) from exc

    cache = get_cache()
    key = f"pred:spatial:{query.lat}:{query.lon}:{query.model}"
    cached = cache.get(key)
    if cached is not None:
        return cast(SpatialNormalResponse, json.loads(cached))

    try:
        engine = db.get_engine()
        result = statistical.estimate_statistical_normal(
            engine, query.lat, query.lon, pool=query.model
        )
    except LookupError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    body: SpatialNormalResponse = {
        "lat": result.lat,
        "lon": result.lon,
        "model": query.model,
        "nearest_station": {
            "station_id": result.nearest_station.station_id,
            "name": result.nearest_station.name,
            "distance_km": result.nearest_station.distance_km,
        },
        "n_neighbours": result.n_neighbours,
        "series": [
            {"week": point.week, "estimated_cloud_pct": point.estimated_cloud_pct}
            for point in result.series
        ],
        "meta": _meta(["smhi-metobs"]),
    }
    cache.set(key, json.dumps(body), CACHE_TTL_S)
    return body


def _first_error(exc: ValidationError) -> str:
    errors = exc.errors()
    return errors[0]["msg"] if errors else str(exc)

"""GET /climatology/cloud and /climatology/lightning — the "Normals" API.

Thin controllers, exactly like the exploration routes: parse the query (a bad
request becomes a 422), read "now" once from the database so the current-month
blend uses the same UTC clock as the stored timestamps, delegate the real work to
cloud.py / lightning.py, and cache the JSON for an hour. A missing precondition
(no stations ingested) surfaces as LookupError → 503; a validly-typed but wrong
request surfaces as ValueError → 422.

This router is intentionally NOT registered with the app here — the step that
moves exploration under /api/v1 mounts it alongside the others. Export name is
`router` so the include site is uniform across packages.
"""

import json
from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import Engine, text

from cloudy.climatology import cloud, lightning
from cloudy.climatology.query import (
    DEFAULT_PERIOD,
    ClimatologyCloudQuery,
    ClimatologyLightningQuery,
    Period,
)
from cloudy.climatology.types import (
    CloudClimatologyResponse,
    LightningClimatologyResponse,
)
from cloudy.core.cache import get_cache
from cloudy.db import session as db

router = APIRouter()

CACHE_TTL_S = 3600


def _now(engine: Engine) -> datetime:
    # Take "now" from the database, not the app process: the timestamps we blend
    # against are stored by Postgres, so its clock is the authority and the blend
    # stays correct even if an app host's clock drifts. Tag UTC defensively in
    # case the column comes back naive.
    with engine.connect() as conn:
        value: datetime = conn.execute(text("SELECT now()")).scalar_one()
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@router.get("/climatology/cloud")
def cloud_route(
    lat: Annotated[float | None, Query()] = None,
    lon: Annotated[float | None, Query()] = None,
    period: Annotated[Period, Query()] = DEFAULT_PERIOD,
    radius_km: Annotated[int, Query()] = 50,
) -> CloudClimatologyResponse:
    try:
        query = ClimatologyCloudQuery.model_validate(
            {"lat": lat, "lon": lon, "period": period, "radius_km": radius_km}
        )
    except ValidationError as exc:
        raise HTTPException(422, _first_error(exc)) from exc

    cache = get_cache()
    # None coords stringify distinctly from a coordinate, so the Sweden-wide normal
    # caches under its own key and never collides with a located one.
    key = f"clim:cloud:{query.lat}:{query.lon}:{query.radius_km}:{query.period}"
    cached = cache.get(key)
    if cached is not None:
        return cast(CloudClimatologyResponse, json.loads(cached))

    try:
        engine = db.get_engine()
        body = cloud.compute(engine, query, _now(engine))
    except LookupError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    cache.set(key, json.dumps(body), CACHE_TTL_S)
    return body


@router.get("/climatology/lightning")
def lightning_route(
    lat: Annotated[float | None, Query()] = None,
    lon: Annotated[float | None, Query()] = None,
    period: Annotated[Period, Query()] = DEFAULT_PERIOD,
    radius_km: Annotated[int, Query()] = 10,
) -> LightningClimatologyResponse:
    try:
        query = ClimatologyLightningQuery.model_validate(
            {"lat": lat, "lon": lon, "period": period, "radius_km": radius_km}
        )
    except ValidationError as exc:
        raise HTTPException(422, _first_error(exc)) from exc

    cache = get_cache()
    key = f"clim:lightning:{query.lat}:{query.lon}:{query.radius_km}:{query.period}"
    cached = cache.get(key)
    if cached is not None:
        return cast(LightningClimatologyResponse, json.loads(cached))

    try:
        engine = db.get_engine()
        body = lightning.compute(engine, query, _now(engine))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    cache.set(key, json.dumps(body), CACHE_TTL_S)
    return body


def _first_error(exc: ValidationError) -> str:
    errors = exc.errors()
    return errors[0]["msg"] if errors else str(exc)

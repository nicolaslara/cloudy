"""GET /api/v1/exploration/lightning — unified lightning read API.

One endpoint, two presentations (query param `format`):
  - series  — aggregated buckets for the bar chart (Aggregates view)
  - strokes — individual events for the map explorer

Spatial filter (mutually exclusive — see LightningQuery in lightning_query.py):
  - default   — all of Sweden
  - radius    — lat + lon + radius_km (bbox derived for SQL prefilter)
  - bbox      — minLon,minLat,maxLon,maxLat (cannot combine with radius)
"""

import json
from datetime import date
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from cloudy.core.cache import get_cache
from cloudy.db import session as db
from cloudy.exploration import lightning_read
from cloudy.exploration.lightning_limits import DEFAULT_MAP_STROKE_POINTS, MAX_MAP_STROKE_POINTS
from cloudy.exploration.lightning_query import (
    DEFAULT_AGGREGATION,
    DEFAULT_FROM,
    LightningFormat,
    LightningQuery,
)
from cloudy.exploration.lightning_types import LightningResponse
from cloudy.exploration.series_plan import MAX_TARGET_POINTS, Aggregation, QueryRejected

router = APIRouter()

CACHE_TTL_S = 3600


def parse_lightning_query(
    date_from: Annotated[date, Query(alias="from")] = DEFAULT_FROM,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    lat: Annotated[float | None, Query(ge=54.0, le=70.0)] = None,
    lon: Annotated[float | None, Query(ge=9.0, le=26.0)] = None,
    radius_km: Annotated[int | None, Query()] = None,
    bbox: Annotated[str | None, Query()] = None,
    format: Annotated[LightningFormat, Query()] = "series",
    aggregation: Annotated[Aggregation, Query()] = DEFAULT_AGGREGATION,
    width_px: Annotated[int | None, Query(ge=100, le=10_000)] = None,
    max_points: Annotated[int | None, Query(ge=1, le=MAX_TARGET_POINTS)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_MAP_STROKE_POINTS)] = DEFAULT_MAP_STROKE_POINTS,
) -> LightningQuery:
    try:
        return LightningQuery.model_validate(
            {
                "from": date_from,
                "to": date_to,
                "lat": lat,
                "lon": lon,
                "radius_km": radius_km,
                "bbox": bbox,
                "format": format,
                "aggregation": aggregation,
                "width_px": width_px,
                "max_points": max_points,
                "limit": limit,
            },
        )
    except ValidationError as exc:
        detail = exc.errors()[0]["msg"] if exc.errors() else str(exc)
        raise HTTPException(422, detail) from exc


@router.get("/exploration/lightning")
def lightning_route(
    query: Annotated[LightningQuery, Depends(parse_lightning_query)],
) -> LightningResponse:
    try:
        cache = get_cache()
        key = query.cache_key()
        cached = cache.get(key)
        if cached is not None:
            return cast(LightningResponse, json.loads(cached))

        body = lightning_read.execute(db.get_engine(), query)
        cache.set(key, json.dumps(body), CACHE_TTL_S)
        return body
    # Same error→status contract as /cloud, minus LookupError: lightning needs no
    # station lookup, so there is no "no stations ingested" precondition to hit.
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except QueryRejected as exc:
        raise HTTPException(413, exc.as_detail()) from exc

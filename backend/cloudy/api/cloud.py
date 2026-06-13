"""GET /api/v1/cloud — cloud history for Sweden or a lat/lon filter."""

import json
from datetime import date
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlmodel import Session

from cloudy.core import cloud_read
from cloudy.core.cache import get_cache
from cloudy.core.cloud_query import DEFAULT_AGGREGATION, DEFAULT_FROM, CloudQuery
from cloudy.core.cloud_types import CloudSeriesResponse
from cloudy.core.series_plan import MAX_TARGET_POINTS, Aggregation, QueryRejected
from cloudy.db import session as db
from cloudy.ingest import stations

router = APIRouter()

CACHE_TTL_S = 3600


def parse_cloud_query(
    lat: Annotated[float | None, Query(ge=54.0, le=70.0)] = None,
    lon: Annotated[float | None, Query(ge=9.0, le=26.0)] = None,
    date_from: Annotated[date, Query(alias="from")] = DEFAULT_FROM,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    aggregation: Annotated[Aggregation, Query()] = DEFAULT_AGGREGATION,
    width_px: Annotated[int | None, Query(ge=100, le=10_000)] = None,
    max_points: Annotated[int | None, Query(ge=1, le=MAX_TARGET_POINTS)] = None,
) -> CloudQuery:
    try:
        return CloudQuery.model_validate(
            {
                "lat": lat,
                "lon": lon,
                "from": date_from,
                "to": date_to,
                "aggregation": aggregation,
                "width_px": width_px,
                "max_points": max_points,
            },
        )
    except ValidationError as exc:
        detail = exc.errors()[0]["msg"] if exc.errors() else str(exc)
        raise HTTPException(422, detail) from exc


def _cache_key(query: CloudQuery) -> str:
    if not query.has_location:
        return query.cache_key(None)
    with Session(db.get_engine()) as session:
        assert query.lat is not None
        assert query.lon is not None
        nearest, _ = stations.nearest_active(session, query.lat, query.lon)
    return query.cache_key(nearest.id)


@router.get("/cloud")
def cloud_route(
    query: Annotated[CloudQuery, Depends(parse_cloud_query)],
) -> CloudSeriesResponse:
    try:
        cache = get_cache()
        key = _cache_key(query)
        cached = cache.get(key)
        if cached is not None:
            return cast(CloudSeriesResponse, json.loads(cached))

        body = cloud_read.execute(db.get_engine(), query)
        cache.set(key, json.dumps(body), CACHE_TTL_S)
        return body
    except LookupError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except QueryRejected as exc:
        raise HTTPException(413, exc.as_detail()) from exc

"""GET /api/v1/station — nearest active cloud station for a lat/lon.

The honesty line: cloud history (arriving in M4) is measured this far away
from the point the user picked.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session

from cloudy.api.schemas import StationResponse
from cloudy.db import session as db
from cloudy.ingest import stations

router = APIRouter()


@router.get("/station")
def station(
    lat: Annotated[float, Query(ge=54.0, le=70.0)],  # Sweden + buffer; the data boundary
    lon: Annotated[float, Query(ge=9.0, le=26.0)],
) -> StationResponse:
    with Session(db.get_engine()) as session:
        try:
            nearest, distance_km = stations.nearest_active(session, lat, lon)
        except LookupError as exc:
            raise HTTPException(503, str(exc)) from exc
    return {
        "station_id": nearest.id,
        "name": nearest.name,
        "distance_km": round(distance_km, 1),
    }

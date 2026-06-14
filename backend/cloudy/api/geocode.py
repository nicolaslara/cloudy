"""GET /api/v1/geocode — address → coordinate candidates via the active provider.

Thin pass-through to the geocode seam; the only real logic is mapping upstream
failures to honest statuses so the frontend can degrade autocomplete cleanly.
"""

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query

from cloudy.api.schemas import GeocodeCandidate
from cloudy.geocode import get_geocoder

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/geocode")
def geocode(q: str = Query(min_length=3, max_length=200)) -> list[GeocodeCandidate]:
    geocoder = get_geocoder()
    try:
        candidates = geocoder.search(q)
    # Surface upstream rate-limiting verbatim as 429 (the frontend pauses
    # autocomplete on it); fold every other upstream failure into 502 so a
    # provider outage reads as "bad gateway", never our own 500.
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:  # frontend degrades autocomplete on this
            raise HTTPException(429, "geocoder rate-limited") from exc
        logger.exception("geocode: %s failed", geocoder.name)
        raise HTTPException(502, f"geocoder {geocoder.name} error") from exc
    except httpx.HTTPError as exc:
        logger.exception("geocode: %s unreachable", geocoder.name)
        raise HTTPException(502, f"geocoder {geocoder.name} unreachable") from exc
    return [
        {"label": c.label, "lat": c.lat, "lon": c.lon, "provider": geocoder.name}
        for c in candidates
    ]

"""HTTP response shapes for non-lightning routes."""

from typing import Literal, TypedDict


class HealthResponse(TypedDict):
    status: Literal["ok", "degraded"]
    db: Literal["up", "down"]
    version: str


class GeocodeCandidate(TypedDict):
    label: str
    lat: float
    lon: float
    provider: str


class StationResponse(TypedDict):
    station_id: int
    name: str
    distance_km: float

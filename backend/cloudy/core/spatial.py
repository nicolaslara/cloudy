"""Spatial bounds for Sweden-scoped queries: a bbox plus optional radius.

This is a foundation primitive because both read layers reach for the same
geometry: exploration filters raw strokes by viewport or radius, and
climatology counts lightning within a radius of a point. Keeping it here (rather
than in either read package) is what lets the two stay siblings that never
import each other.

The box is only ever a cheap index prefilter; the exact circle is enforced
downstream by the haversine clause in series_sql.py. Erring slightly large is
therefore safe, while erring small would clip real events.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians
from typing import Literal, Self

# Canonical Sweden extent (min_lon, min_lat, max_lon, max_lat). The default,
# unfiltered query uses exactly this box, which is how `mode` tells "all of
# Sweden" apart from an explicit viewport that merely happens to be large.
SWEDEN_BBOX = (9.0, 55.0, 26.0, 70.0)

_KM_PER_DEG_LAT = 111.0


@dataclass(frozen=True)
class SpatialBounds:
    """Resolved lon/lat bounds plus optional haversine radius refinement."""

    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float
    center_lat: float | None = None
    center_lon: float | None = None
    radius_km: float | None = None

    @property
    def use_radius(self) -> bool:
        return (
            self.radius_km is not None
            and self.center_lat is not None
            and self.center_lon is not None
        )

    @property
    def mode(self) -> Literal["sweden", "bbox", "radius"]:
        # Mode is inferred, not stored: a radius refinement always wins; otherwise
        # bounds that differ from the canonical Sweden box mean an explicit
        # viewport; bounds equal to it mean the unfiltered Sweden default.
        if self.use_radius:
            return "radius"
        if (self.min_lon, self.min_lat, self.max_lon, self.max_lat) != SWEDEN_BBOX:
            return "bbox"
        return "sweden"

    @classmethod
    def sweden(cls) -> Self:
        return cls(*SWEDEN_BBOX)

    @classmethod
    def from_bbox(cls, min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> Self:
        return cls(min_lon, min_lat, max_lon, max_lat)

    @classmethod
    def from_radius(cls, lat: float, lon: float, radius_km: float) -> Self:
        # Turn a circle into a generous square: latitude degrees are ~constant
        # length, but a longitude degree shrinks toward the poles, so we widen the
        # lon span by 1/cos(lat). This box is only a cheap index prefilter — the
        # exact circle is enforced later by the haversine clause in SQL — so
        # erring slightly large is fine; erring small would clip real strikes.
        dlat = radius_km / _KM_PER_DEG_LAT
        dlon = radius_km / (_KM_PER_DEG_LAT * cos(radians(lat)))
        return cls(
            lon - dlon,
            lat - dlat,
            lon + dlon,
            lat + dlat,
            center_lat=lat,
            center_lon=lon,
            radius_km=radius_km,
        )


def parse_bbox(raw: str) -> tuple[float, float, float, float]:
    """Parse a "minLon,minLat,maxLon,maxLat" string, clamped to Sweden's extent.

    Out-of-bounds or malformed input is a client error (ValueError), so the API
    can turn it into a 422 rather than silently widening the query.
    """
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be minLon,minLat,maxLon,maxLat")
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    except ValueError as exc:
        raise ValueError("bbox values must be numbers") from exc
    if not (SWEDEN_BBOX[0] <= min_lon < max_lon <= SWEDEN_BBOX[2]):
        raise ValueError("bbox longitude outside Sweden bounds")
    if not (SWEDEN_BBOX[1] <= min_lat < max_lat <= SWEDEN_BBOX[3]):
        raise ValueError("bbox latitude outside Sweden bounds")
    return min_lon, min_lat, max_lon, max_lat

"""Address → coordinate candidates, behind one seam.

Provider is selected by the GEOCODER setting (env-switchable without redeploy —
a Nominatim-policy requirement). Photon serves autocomplete; Nominatim is
on-submit only (its usage policy forbids autocomplete).
"""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Protocol

from cloudy.config import get_settings
from cloudy.core.cache import get_cache

CACHE_TTL_S = 600


@dataclass(frozen=True)
class Candidate:
    label: str
    lat: float
    lon: float


class Geocoder(Protocol):
    name: str

    def search(self, query: str, limit: int = 6) -> list[Candidate]: ...


def cached_search(
    provider: str, query: str, limit: int, fetch: Callable[[], list[Candidate]]
) -> list[Candidate]:
    """Cache wrapper shared by providers; absorbs repeated keystrokes/queries."""
    cache = get_cache()
    key = f"geocode:{provider}:{limit}:{query}"
    hit = cache.get(key)
    if hit is not None:
        return [Candidate(**c) for c in json.loads(hit)]
    candidates = fetch()
    cache.set(key, json.dumps([asdict(c) for c in candidates]), ttl_s=CACHE_TTL_S)
    return candidates


def get_geocoder() -> Geocoder:
    from cloudy.geocode import nominatim, photon

    providers: dict[str, Geocoder] = {"photon": photon.Photon(), "nominatim": nominatim.Nominatim()}
    return providers[get_settings().geocoder]

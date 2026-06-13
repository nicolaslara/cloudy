from typing import Any

import httpx

from cloudy.geocode import Candidate, cached_search

API = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "cloudy/0.1 (personal weather-history app)"  # required by the usage policy


class Nominatim:
    name = "nominatim"

    def search(self, query: str, limit: int = 6) -> list[Candidate]:
        q = query.strip().lower()
        return cached_search(self.name, q, limit, lambda: list(_search(q, limit)))


def _search(query: str, limit: int) -> tuple[Candidate, ...]:
    response = httpx.get(
        API,
        params={"q": query, "format": "jsonv2", "countrycodes": "se", "limit": limit},
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    response.raise_for_status()
    return parse(response.json())


def parse(payload: list[dict[str, Any]]) -> tuple[Candidate, ...]:
    candidates = []
    for item in payload:
        try:
            candidates.append(
                Candidate(
                    label=str(item["display_name"]),
                    lat=float(item["lat"]),
                    lon=float(item["lon"]),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    return tuple(candidates)

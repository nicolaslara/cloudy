from typing import Any

import httpx

from cloudy.geocode import Candidate, cached_search

API = "https://photon.komoot.io/api/"
SWEDEN_BBOX = "9.5,54.5,25,69.5"  # lon/lat min→max, generous buffer
USER_AGENT = "cloudy/0.1 (personal weather-history app)"  # generic UAs get 403


class Photon:
    name = "photon"

    def search(self, query: str, limit: int = 6) -> list[Candidate]:
        q = query.strip().lower()
        return cached_search(self.name, q, limit, lambda: list(_search(q, limit)))


def _search(query: str, limit: int) -> tuple[Candidate, ...]:
    response = httpx.get(
        API,
        params={"q": query, "limit": limit, "bbox": SWEDEN_BBOX},
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    response.raise_for_status()
    return parse(response.json())


def parse(payload: dict[str, Any]) -> tuple[Candidate, ...]:
    candidates = []
    for feature in payload.get("features", []):
        try:
            lon, lat = feature["geometry"]["coordinates"]
            props = feature.get("properties", {})
            parts = [
                props.get(key)
                for key in ("name", "street", "housenumber", "postcode", "city", "county")
            ]
            label = ", ".join(str(p) for p in parts if p)
            candidates.append(Candidate(label=label or "(unnamed)", lat=lat, lon=lon))
        except (KeyError, ValueError, TypeError):
            continue  # tolerate odd features, keep the rest
    return tuple(candidates)

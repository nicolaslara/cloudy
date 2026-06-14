"""Contract tests for GET /api/v1/exploration/cloud with the SQL seam monkeypatched."""

from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from cloudy.api import create_app
from cloudy.core import cache as cache_module
from cloudy.db import session as db_session
from cloudy.exploration import cloud_read, cloud_series

SERIES: list[dict[str, Any]] = [
    {
        "period": "2018-07",
        "bucket_start": "2018-07-01T00:00:00Z",
        "bucket_end": "2018-08-01T00:00:00Z",
        "mean_cloud_pct": 42.5,
        "min_cloud_pct": 10.0,
        "max_cloud_pct": 100.0,
        "p05_cloud_pct": 12.0,
        "p50_cloud_pct": 38.0,
        "p95_cloud_pct": 100.0,
        "observed_count": 120,
        "expected_count": 744,
        "missing_count": 624,
    }
]

RESPONSE: dict[str, Any] = {
    "aggregation": "auto",
    "resolved_resolution": "month",
    "station": {"station_id": 98040, "name": "Berga", "distance_km": 29.2},
    "series": SERIES,
    "meta": {
        "from": "2015-01-01",
        "to": "2018-12-31",
        "coverage_fraction": 0.161,
        "scope": "station",
        "station_count": None,
        "sources": ["smhi-metobs"],
        "attribution": "Source: SMHI",
        "generated_at": "2026-06-11T00:00:00+00:00",
        "total_matched": 1,
        "returned": 1,
        "requested_aggregation": "auto",
        "resolved_resolution": "month",
        "mode": "aggregate",
        "representation": "cloud_aggregate_month",
        "target_points": 1800,
        "point_count": 1,
        "is_complete": True,
    },
}


class QuerySpy:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def __call__(
        self,
        engine: Engine,
        station_id: int,
        aggregation: str,
        date_from: date,
        date_to: date,
    ) -> list[dict[str, Any]]:
        self.calls.append((station_id, aggregation, date_from, date_to))
        return SERIES


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[QuerySpy]:
    cache_module.get_cache.cache_clear()
    query_spy = QuerySpy()
    monkeypatch.setattr(cloud_series, "query_series", query_spy)
    monkeypatch.setattr(db_session, "get_engine", lambda: object())

    def fake_execute(engine: Engine, query: Any) -> dict[str, Any]:
        scope = "station" if query.has_location else "sweden"
        return {
            **RESPONSE,
            "aggregation": query.aggregation,
            "station": RESPONSE["station"] if query.has_location else None,
            "meta": {
                **RESPONSE["meta"],
                "from": query.date_from.isoformat(),
                "to": query.resolved_date_to().isoformat(),
                "requested_aggregation": query.aggregation,
                "scope": scope,
                "station_count": None if query.has_location else 8,
            },
        }

    monkeypatch.setattr(
        cloud_read,
        "execute",
        fake_execute,
    )
    yield query_spy
    cache_module.get_cache.cache_clear()


@pytest.fixture
def client(spy: QuerySpy, stations_sample: Engine, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(db_session, "get_engine", lambda: stations_sample)
    return TestClient(create_app())


def test_cloud_defaults_to_sweden_scope(client: TestClient) -> None:
    response = client.get("/api/v1/exploration/cloud")
    assert response.status_code == 200
    body = response.json()
    assert body["station"] is None
    assert body["meta"]["scope"] == "sweden"
    assert body["meta"]["station_count"] == 8


def test_cloud_series_defaults(client: TestClient, spy: QuerySpy) -> None:
    response = client.get("/api/v1/exploration/cloud", params={"lat": 59.33, "lon": 18.06})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["aggregation"] == "auto"
    assert body["resolved_resolution"] == "month"
    assert body["station"]["name"]
    assert body["series"] == SERIES
    assert body["meta"]["coverage_fraction"] == 0.161


def test_cloud_passes_params(client: TestClient) -> None:
    response = client.get(
        "/api/v1/exploration/cloud",
        params={
            "lat": 59.33,
            "lon": 18.06,
            "aggregation": "week",
            "from": "2018-01-01",
            "to": "2018-12-31",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["aggregation"] == "week"


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 48.85, "lon": 2.35},
        {"lat": 59.33},
        {"from": "not-a-date"},
        {"lat": 59.33, "lon": 18.06, "aggregation": "granularity"},
        {"lat": 59.33, "lon": 18.06, "from": "2020-01-01", "to": "2019-01-01"},
    ],
)
def test_invalid_params_are_422(client: TestClient, params: dict[str, Any]) -> None:
    assert client.get("/api/v1/exploration/cloud", params=params).status_code == 422


def test_legacy_granularity_param_is_not_public_contract(client: TestClient) -> None:
    response = client.get(
        "/api/v1/exploration/cloud",
        params={"lat": 59.33, "lon": 18.06, "granularity": "month"},
    )
    assert response.status_code == 200
    assert response.json()["aggregation"] == "auto"


def test_second_identical_call_is_served_from_cache(client: TestClient) -> None:
    params = {"lat": 59.33, "lon": 18.06, "to": "2026-01-01"}
    first = client.get("/api/v1/exploration/cloud", params=params)
    second = client.get("/api/v1/exploration/cloud", params=params)
    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()

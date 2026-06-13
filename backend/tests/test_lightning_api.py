"""Contract tests for GET /api/v1/lightning with the SQL seam monkeypatched."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from cloudy.api import create_app
from cloudy.core import cache as cache_module
from cloudy.core import lightning_read, lightning_series
from cloudy.core.lightning_query import SpatialBounds
from cloudy.db import session as db_session

SERIES = [
    {
        "period": "2018-07",
        "bucket_start": "2018-07-01T00:00:00Z",
        "bucket_end": "2018-08-01T00:00:00Z",
        "cg_count": 142,
        "all_count": 388,
        "lightning_days": 6,
        "max_abs_peak_ka": 110.2,
        "strongest_event_time": "2018-07-25T12:00:00Z",
    }
]


class QuerySpy:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def __call__(
        self,
        engine: Engine,
        spatial: SpatialBounds,
        plan: Any,
        date_from: date,
        date_to: date,
    ) -> list[dict[str, Any]]:
        self.calls.append((spatial.mode, plan.resolved_resolution, date_from, date_to))
        return SERIES


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[QuerySpy]:
    cache_module.get_cache.cache_clear()
    query_spy = QuerySpy()
    monkeypatch.setattr(lightning_series, "query_series", query_spy)
    monkeypatch.setattr(lightning_series, "count_events", lambda *args: 388)
    monkeypatch.setattr(db_session, "get_engine", lambda: object())
    yield query_spy
    cache_module.get_cache.cache_clear()


@pytest.fixture
def client(spy: QuerySpy) -> TestClient:
    return TestClient(create_app())


def test_series_defaults_without_location(client: TestClient, spy: QuerySpy) -> None:
    response = client.get("/api/v1/lightning", params={"format": "series"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["format"] == "series"
    assert body["aggregation"] == "auto"
    assert body["resolved_resolution"] == "month"
    assert body["spatial"]["mode"] == "sweden"
    assert body["series"] == SERIES
    assert spy.calls == [("sweden", "month", date(2015, 1, 1), datetime.now(UTC).date())]


def test_series_with_radius_filter(client: TestClient, spy: QuerySpy) -> None:
    response = client.get(
        "/api/v1/lightning",
        params={"format": "series", "lat": 59.33, "lon": 18.06, "radius_km": 10},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["spatial"]["mode"] == "radius"
    assert spy.calls[0][0] == "radius"


def test_explicit_params_are_passed_through(client: TestClient, spy: QuerySpy) -> None:
    response = client.get(
        "/api/v1/lightning",
        params={
            "format": "series",
            "lat": 59.33,
            "lon": 18.06,
            "radius_km": 25,
            "aggregation": "week",
            "from": "2018-01-01",
            "to": "2018-12-31",
        },
    )
    assert response.status_code == 200, response.text
    assert spy.calls == [("radius", "week", date(2018, 1, 1), date(2018, 12, 31))]


@pytest.mark.parametrize(
    "params",
    [
        {"format": "series", "lon": 18.06},
        {"format": "series", "lat": 48.85, "lon": 2.35},
        {"format": "series", "lat": 59.33, "lon": 18.06, "radius_km": 15},
        {"format": "series", "aggregation": "granularity"},
        {"format": "series", "from": "not-a-date"},
        {
            "format": "strokes",
            "lat": 59.33,
            "lon": 18.06,
            "radius_km": 10,
            "bbox": "9,55,20,65",
        },
    ],
)
def test_invalid_params_are_422(client: TestClient, spy: QuerySpy, params: dict[str, Any]) -> None:
    assert client.get("/api/v1/lightning", params=params).status_code == 422
    assert spy.calls == []


def test_unsafe_manual_aggregation_rejects_before_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_module.get_cache.cache_clear()

    def should_not_count(*_args: object, **_kwargs: object) -> int:
        pytest.fail("unsafe bucket request should reject before counting events")

    def should_not_query(*_args: object, **_kwargs: object) -> list[dict[str, Any]]:
        pytest.fail("unsafe bucket request should reject before querying events")

    monkeypatch.setattr(lightning_series, "count_events", should_not_count)
    monkeypatch.setattr(lightning_series, "query_series", should_not_query)
    monkeypatch.setattr(db_session, "get_engine", lambda: object())

    response = TestClient(create_app()).get(
        "/api/v1/lightning",
        params={
            "format": "series",
            "from": "2015-01-01",
            "to": "2026-06-12",
            "aggregation": "day",
            "width_px": 1200,
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"]["error"] == "too_many_buckets_for_response"
    assert response.json()["detail"]["suggested_aggregation"] == "month"


def test_strokes_format_uses_events_reader(
    client: TestClient,
    spy: QuerySpy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events_body = {
        "format": "strokes",
        "columns": ["lon", "lat", "peak_ka", "cg", "ts"],
        "rows": [[18.0, 59.0, -10.0, 1, 1_532_520_000]],
        "meta": {
            "from": "2018-07-25",
            "to": "2018-07-25",
            "total_matched": 1,
            "returned": 1,
            "downsampled": False,
            "stride": None,
            "sample_method": None,
            "dropped_count": 0,
            "representation": "raw_strokes",
            "is_complete": True,
            "sources": ["smhi-lightning"],
            "attribution": "Source: SMHI",
            "generated_at": "2026-06-11T00:00:00+00:00",
        },
    }

    def fake_execute(engine: Engine, query: Any) -> dict[str, Any]:
        assert query.format == "strokes"
        return {**events_body, "spatial": query.spatial().as_meta()}

    monkeypatch.setattr(lightning_read, "execute", fake_execute)
    response = client.get(
        "/api/v1/lightning",
        params={"format": "strokes", "from": "2018-07-25", "to": "2018-07-25", "limit": 5},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["format"] == "strokes"
    assert body["columns"] == ["lon", "lat", "peak_ka", "cg", "ts"]
    assert spy.calls == []


def test_second_identical_call_is_served_from_cache(client: TestClient, spy: QuerySpy) -> None:
    params = {"format": "series", "lat": 59.33, "lon": 18.06, "to": "2026-01-01"}
    first = client.get("/api/v1/lightning", params=params)
    second = client.get("/api/v1/lightning", params=params)
    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert len(spy.calls) == 1

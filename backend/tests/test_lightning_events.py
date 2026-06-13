"""Tests for format=strokes presentation (core query_events)."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from cloudy.api import create_app
from cloudy.core import lightning_events
from cloudy.core.lightning_query import SpatialBounds
from cloudy.db import session as db_session


@pytest.fixture
def client(db: Engine, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(db_session, "get_engine", lambda: db)
    return TestClient(create_app())


def test_query_events_returns_compact_rows(lightning_sample: Engine) -> None:
    body = lightning_events.query_events(
        lightning_sample,
        date(2018, 7, 25),
        date(2018, 7, 25),
        SpatialBounds.sweden(),
        limit=100,
    )
    assert body["columns"] == ["lon", "lat", "peak_ka", "cg", "ts"]
    assert body["meta"]["total_matched"] == 40
    assert body["meta"]["returned"] == 40
    assert body["meta"]["downsampled"] is False
    assert len(body["rows"]) == 40


def test_query_events_returns_priority_sample_when_over_limit(lightning_sample: Engine) -> None:
    body = lightning_events.query_events(
        lightning_sample,
        date(2018, 7, 25),
        date(2018, 7, 25),
        SpatialBounds.sweden(),
        limit=10,
    )
    assert body["meta"]["total_matched"] == 40
    assert body["meta"]["returned"] == 10
    assert body["meta"]["downsampled"] is True
    assert body["meta"]["stride"] is None
    assert body["meta"]["sample_method"] == "priority_abs_peak"
    assert body["meta"]["dropped_count"] == 30
    assert body["meta"]["representation"] == "priority_sampled_strokes"


def test_strokes_api_shape(client: TestClient, lightning_sample: Engine) -> None:
    response = client.get(
        "/api/v1/lightning",
        params={"format": "strokes", "from": "2018-07-25", "to": "2018-07-25", "limit": 5},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["format"] == "strokes"
    assert body["columns"] == ["lon", "lat", "peak_ka", "cg", "ts"]
    assert len(body["rows"]) == 5
    assert body["meta"]["downsampled"] is True
    assert body["meta"]["sample_method"] == "priority_abs_peak"
    assert body["meta"]["attribution"] == "Source: SMHI"
    assert body["spatial"]["mode"] == "sweden"


def test_strokes_api_rejects_invalid_bbox(client: TestClient) -> None:
    response = client.get("/api/v1/lightning", params={"format": "strokes", "bbox": "1,2,3"})
    assert response.status_code == 422


def test_strokes_api_rejects_bbox_with_radius(client: TestClient) -> None:
    response = client.get(
        "/api/v1/lightning",
        params={
            "format": "strokes",
            "lat": 59.33,
            "lon": 18.06,
            "radius_km": 10,
            "bbox": "9,55,20,65",
        },
    )
    assert response.status_code == 422


def test_strokes_api_location_filter(client: TestClient, lightning_sample: Engine) -> None:
    response = client.get(
        "/api/v1/lightning",
        params={
            "format": "strokes",
            "from": "2018-07-25",
            "to": "2018-07-25",
            "lat": 59.33,
            "lon": 18.06,
            "radius_km": 10,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total_matched"] == 0
    assert body["spatial"]["mode"] == "radius"

"""Contract tests for the climatology endpoints.

The router isn't mounted by the app factory yet (the exploration-move step does
that), so the test mounts it under /api/v1 itself — the same prefix it will get
in production — and drives it end to end against the isolated database.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from cloudy.climatology.api import router
from cloudy.core import cache as cache_module
from cloudy.db import session as db_session
from cloudy.db.models import CloudHourly, LightningEvent

STATION_ID = 98040
BERGA_LAT, BERGA_LON = 59.068, 18.115


@pytest.fixture
def client(stations_sample: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    cache_module.get_cache.cache_clear()
    monkeypatch.setattr(db_session, "get_engine", lambda: stations_sample)

    with Session(stations_sample) as session:
        session.add_all(
            [
                CloudHourly(
                    station_id=STATION_ID,
                    ts_utc=datetime(year, 7, 1, hour, tzinfo=UTC),
                    cloud_pct=float(pct),
                )
                for year, pct in ((2020, 40), (2021, 60))
                for hour in range(24)
            ]
        )
        session.add(
            LightningEvent(
                ts_utc=datetime(2020, 7, 10, 14, tzinfo=UTC),
                day=datetime(2020, 7, 10).date(),
                lat=BERGA_LAT,
                lon=BERGA_LON,
                peak_current_ka=-15.0,
                multiplicity=0,
                number_of_sensors=4,
                cloud_indicator=0,
            )
        )
        session.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    yield TestClient(app)
    cache_module.get_cache.cache_clear()


def test_cloud_endpoint_returns_chart_ready_normals(client: TestClient) -> None:
    response = client.get(
        "/api/v1/climatology/cloud",
        params={"lat": BERGA_LAT, "lon": BERGA_LON, "period": "month"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "station"
    assert body["station"]["station_id"] == STATION_ID
    july = {p["period"]: p for p in body["series"]}["7"]
    assert july["mean_cloud_pct"] == 50.0
    assert body["current_month"]["month"] in range(1, 13)
    assert body["meta"]["attribution"] == "Source: SMHI"


def test_cloud_endpoint_without_location_is_sweden_wide(client: TestClient) -> None:
    response = client.get("/api/v1/climatology/cloud", params={"period": "month"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "sweden"
    assert body["station"] is None
    assert body["station_count"] is not None


def test_lightning_endpoint_without_location_is_sweden_wide(client: TestClient) -> None:
    response = client.get("/api/v1/climatology/lightning", params={"period": "month"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "sweden"
    assert body["radius_km"] is None


def test_lightning_endpoint_returns_chart_ready_normals(client: TestClient) -> None:
    response = client.get(
        "/api/v1/climatology/lightning",
        params={"lat": BERGA_LAT, "lon": BERGA_LON, "period": "month", "radius_km": 10},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "radius"
    assert body["radius_km"] == 10
    july = {p["period"]: p for p in body["series"]}["7"]
    assert july["expected_lightning_days"] == 1.0
    assert body["meta"]["sources"] == ["smhi-lightning"]


@pytest.mark.parametrize(
    "path, params",
    [
        ("/api/v1/climatology/cloud", {"lat": 48.85, "lon": 2.35}),  # outside Sweden
        ("/api/v1/climatology/cloud", {"lat": 59.0}),  # missing lon
        ("/api/v1/climatology/cloud", {"lat": 59.0, "lon": 18.0, "period": "decade"}),
        ("/api/v1/climatology/lightning", {"lat": 59.0, "lon": 18.0, "radius_km": 50}),
    ],
)
def test_invalid_params_are_422(client: TestClient, path: str, params: dict[str, object]) -> None:
    assert client.get(path, params=params).status_code == 422

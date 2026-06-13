"""GET /api/v1/station against the captured metobs station registry fixture."""

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from cloudy.api import create_app


def test_returns_nearest_active_station(stations_sample: Engine) -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/station", params={"lat": 68.35, "lon": 18.82})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Abisko Aut"
    assert isinstance(body["station_id"], int)
    assert body["distance_km"] < 5


def test_out_of_bounds_is_422(stations_sample: Engine) -> None:
    client = TestClient(create_app())
    assert client.get("/api/v1/station", params={"lat": 48.85, "lon": 2.35}).status_code == 422


def test_empty_registry_is_503_with_message(db: Engine) -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/station", params={"lat": 68.35, "lon": 18.82})
    assert response.status_code == 503
    assert "cloudy ingest stations" in response.json()["detail"]

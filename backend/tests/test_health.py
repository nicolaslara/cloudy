import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

import cloudy.api.health as health_module
from cloudy import __version__
from cloudy.api import create_app


class DownEngine:
    def connect(self) -> None:
        raise OperationalError("SELECT 1", None, Exception("connection refused"))


def test_health_ok_when_db_up(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_module, "get_engine", lambda: db)
    response = TestClient(create_app()).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "up", "version": __version__}


def test_health_degraded_when_db_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_module, "get_engine", DownEngine)
    response = TestClient(create_app()).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "db": "down", "version": __version__}


def test_unknown_route_returns_404() -> None:
    response = TestClient(create_app()).get("/api/v1/nope")
    assert response.status_code == 404


def test_unwired_root_returns_404() -> None:
    response = TestClient(create_app()).get("/")
    assert response.status_code == 404


def test_default_cors_allows_localhost_not_every_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    from cloudy.config import get_settings

    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        local = client.get("/api/v1/health", headers={"Origin": "http://localhost:5273"})
        other = client.get("/api/v1/health", headers={"Origin": "https://example.test"})

        assert local.headers["access-control-allow-origin"] == "http://localhost:5273"
        assert "access-control-allow-origin" not in other.headers
    finally:
        get_settings.cache_clear()


def test_api_docs_disabled_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_DOCS", "false")
    from cloudy.config import get_settings

    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404
    finally:
        get_settings.cache_clear()

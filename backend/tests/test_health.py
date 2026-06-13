import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import OperationalError

import cloudy.api.health as health_module
from cloudy import __version__
from cloudy.api import create_app


class DownEngine:
    def connect(self) -> None:
        raise OperationalError("SELECT 1", None, Exception("connection refused"))


def test_health_ok_when_db_up(monkeypatch: pytest.MonkeyPatch) -> None:
    def sqlite_engine() -> Engine:
        return create_engine("sqlite://")

    monkeypatch.setattr(health_module, "get_engine", sqlite_engine)
    response = TestClient(create_app()).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "up", "version": __version__}


def test_health_degraded_when_db_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_module, "get_engine", DownEngine)
    response = TestClient(create_app()).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "db": "down", "version": __version__}

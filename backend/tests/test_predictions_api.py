"""Contract tests for the predictions endpoint — the weekly near-term outlook.

Mirrors tests/test_climatology_api.py: mount the router under /api/v1, seed cloud
history at Berga, and assert the outlook JSON shape (recent gap + per-lead damped
deviation + skill) for both the located and Sweden-wide paths, plus 422s.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from cloudy.core import cache as cache_module
from cloudy.db import session as db_session
from cloudy.db.models import CloudHourly, LightningEvent
from cloudy.ingest.cloud import refresh_rollups
from cloudy.predictions.api import router

STATION_ID = 98040
BERGA_LAT, BERGA_LON = 59.068, 18.115


@pytest.fixture
def client(stations_sample: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """App seeded with ~3 years of weekly cloud + lightning at Berga.

    Cloud is a smooth drift so weekly anomalies have something to persist; lightning
    is a repeating 0-3 strike-days-per-week pattern (some weeks empty, to exercise
    the zero-fill) at the same place, so both outlooks return a non-trivial series.
    """
    cache_module.get_cache.cache_clear()
    monkeypatch.setattr(db_session, "get_engine", lambda: stations_sample)

    base = datetime(2021, 1, 4, 12, tzinfo=UTC)  # a Monday
    cloud = [
        CloudHourly(
            station_id=STATION_ID,
            ts_utc=base + timedelta(weeks=w),
            # A drifting series so weekly anomalies have something to persist.
            cloud_pct=50.0 + 30.0 * ((w % 8) / 8.0),
        )
        for w in range(160)
    ]
    strikes = [
        _strike(base + timedelta(weeks=w, days=d))
        for w in range(160)
        for d in range(w % 4)  # 0-3 distinct strike-days per week, some weeks empty
    ]
    with Session(stations_sample) as session:
        session.add_all(cloud)
        session.add_all(strikes)
        session.commit()
    # The cloud outlook reads the weekly serving rollups (not the raw hourly
    # archive), so materialize them here exactly as ingest does — the same step
    # the exploration Sweden tests perform after seeding hourly rows.
    refresh_rollups(stations_sample, STATION_ID)

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    yield TestClient(app)
    cache_module.get_cache.cache_clear()


def _strike(ts: datetime) -> LightningEvent:
    """One discharge at Berga; only ts/day/lat/lon and the NOT NULL columns matter."""
    return LightningEvent(
        ts_utc=ts,
        day=ts.date(),
        lat=BERGA_LAT,
        lon=BERGA_LON,
        peak_current_ka=-12.0,
        multiplicity=1,
        number_of_sensors=5,
        cloud_indicator=0,
    )


def test_outlook_returns_recent_gap_and_damped_leads(client: TestClient) -> None:
    response = client.get(
        "/api/v1/predictions/outlook", params={"lat": BERGA_LAT, "lon": BERGA_LON}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["scope"] == "station"
    assert body["radius_km"] == 50
    assert body["weeks_observed"] > 0
    assert body["recent_anomaly_pct"] is not None

    leads = {lead["lead_weeks"]: lead for lead in body["leads"]}
    assert set(leads) == {1, 2}
    for lead in body["leads"]:
        assert 0.0 <= lead["alpha"] <= 1.0
        assert isinstance(lead["skill"], float)
        assert isinstance(lead["n_origins"], int)
        # The lead names the ISO week it forecasts, so the UI can align a point's
        # week-of-year normal (nearest / kNN / spatial) to it.
        assert 1 <= lead["target_week"] <= 52
    # Two consecutive leads forecast two consecutive weeks (modulo the year wrap).
    assert leads[2]["target_week"] - leads[1]["target_week"] in (1, -51)

    assert body["meta"]["attribution"] == "Source: SMHI"
    assert "smhi-metobs" in body["meta"]["sources"]


def test_outlook_sweden_wide_without_location(client: TestClient) -> None:
    body = client.get("/api/v1/predictions/outlook").json()
    assert body["scope"] == "sweden"
    # The Sweden-wide series is pooled from the active stations' weekly rollups, so
    # the seeded history surfaces here too (not just on the located path).
    assert body["weeks_observed"] > 0
    assert body["recent_anomaly_pct"] is not None


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 48.85, "lon": 2.35},  # outside Sweden
        {"lat": 59.0},  # lone coordinate
        {"lat": 59.0, "lon": 18.0, "radius_km": 25},  # invalid cloud radius
    ],
)
def test_invalid_params_are_422(client: TestClient, params: dict[str, object]) -> None:
    assert client.get("/api/v1/predictions/outlook", params=params).status_code == 422


# --- Lightning outlook (the sparse second statement) --------------------------


def test_lightning_outlook_returns_recent_gap_and_damped_leads(client: TestClient) -> None:
    response = client.get(
        "/api/v1/predictions/lightning-outlook", params={"lat": BERGA_LAT, "lon": BERGA_LON}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["scope"] == "radius"
    assert body["radius_km"] == 25
    assert body["weeks_observed"] > 0
    assert body["recent_anomaly_days"] is not None
    # The series trails the calendar: it names the week it's as-of (an ISO date).
    assert body["as_of_week"] and body["as_of_week"].count("-") == 2

    leads = {lead["lead_weeks"]: lead for lead in body["leads"]}
    assert set(leads) == {1, 2}
    for lead in body["leads"]:
        assert 0.0 <= lead["alpha"] <= 1.0
        assert isinstance(lead["skill"], float)
        assert isinstance(lead["n_origins"], int)

    assert "smhi-lightning" in body["meta"]["sources"]


def test_lightning_outlook_sweden_wide_without_location(client: TestClient) -> None:
    body = client.get("/api/v1/predictions/lightning-outlook").json()
    assert body["scope"] == "sweden"
    # Sweden-wide ignores the radius, so it isn't echoed back.
    assert body["radius_km"] is None


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 48.85, "lon": 2.35},  # outside Sweden
        {"lat": 59.0},  # lone coordinate
        {"lat": 59.0, "lon": 18.0, "radius_km": 50},  # invalid lightning radius
    ],
)
def test_lightning_invalid_params_are_422(client: TestClient, params: dict[str, object]) -> None:
    assert client.get("/api/v1/predictions/lightning-outlook", params=params).status_code == 422


# --- Backtest benchmark (static, persisted, served read-only) -----------------


def test_backtest_503_before_evaluation(
    client: TestClient, tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    missing = tmp_path / "nope.json"  # type: ignore[operator]
    monkeypatch.setattr(
        "cloudy.predictions.api.get_settings",
        lambda: SimpleNamespace(predictions_scorecard_path=str(missing)),
    )
    assert client.get("/api/v1/predictions/backtest").status_code == 503


def test_backtest_serves_the_persisted_artifact(
    client: TestClient,
    stations_sample: Engine,
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The endpoint serves what `cloudy backtest` wrote — it does not recompute."""
    import json
    from types import SimpleNamespace

    from cloudy.predictions import evaluate

    artifact = evaluate.evaluate(stations_sample)
    path = tmp_path / "backtest_scores.json"  # type: ignore[operator]
    path.write_text(json.dumps(artifact), encoding="utf-8")
    monkeypatch.setattr(
        "cloudy.predictions.api.get_settings",
        lambda: SimpleNamespace(predictions_scorecard_path=str(path)),
    )

    body = client.get("/api/v1/predictions/backtest").json()
    assert body["n_stations"] >= 1  # Berga has enough weekly history to score
    # The damped model appears on the leaderboard with its per-station spread.
    scores = body["models"]["damped"]
    assert isinstance(scores["lead1_skills"], list)
    assert "median_skill_pct" in scores
    assert 0.0 <= scores["fraction_beating"] <= 1.0


# --- Spatial normal (statistical estimate at an arbitrary point) ---------------


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 48.85, "lon": 2.35},  # outside Sweden
        {"lat": 59.0},  # lone coordinate (both required here)
        {},  # no coordinates at all (no Sweden-wide point estimate)
    ],
)
def test_spatial_invalid_params_are_422(client: TestClient, params: dict[str, object]) -> None:
    assert client.get("/api/v1/predictions/spatial", params=params).status_code == 422


@pytest.mark.parametrize("model", ["nearest", "knn"])
def test_spatial_statistical_models_need_no_trained_model(client: TestClient, model: str) -> None:
    """The nearest/kNN rungs are pure statistics — they serve from the seeded cloud
    history alone, with no trained AI model on disk, and echo back the chosen model."""
    response = client.get(
        "/api/v1/predictions/spatial",
        params={"lat": BERGA_LAT, "lon": BERGA_LON, "model": model},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model"] == model
    assert body["series"]
    assert {p["week"] for p in body["series"]} <= set(range(1, 54))
    assert all(0.0 <= p["estimated_cloud_pct"] <= 100.0 for p in body["series"])
    # nearest uses one station; knn pools the k nearest (the seeded fixture has cloud
    # at one station, but the neighbour set is still the k nearest active stations).
    assert body["n_neighbours"] == (1 if model == "nearest" else 5)


def test_spatial_unknown_model_is_422(client: TestClient) -> None:
    response = client.get(
        "/api/v1/predictions/spatial",
        params={"lat": BERGA_LAT, "lon": BERGA_LON, "model": "bogus"},
    )
    assert response.status_code == 422


# --- Backtest series (forecast vs actual over the rolling origins) -------------


def test_backtest_series_returns_forecast_vs_actual(client: TestClient) -> None:
    response = client.get(
        "/api/v1/predictions/backtest-series",
        params={"lat": BERGA_LAT, "lon": BERGA_LON, "model": "damped", "lead": 1},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model"] == "damped"
    assert body["scope"] == "station"
    assert body["lead_weeks"] == 1
    assert body["n_origins"] == len(body["points"]) > 0
    for point in body["points"]:
        # An ISO date and three cloud percentages (actual, the model's forecast, the
        # seasonal-normal baseline) — the three lines the chart draws.
        assert point["week"].count("-") == 2
        for field in ("actual", "forecast", "normal"):
            assert 0.0 <= point[field] <= 100.0
    # Chronological so the line reads left to right.
    weeks = [p["week"] for p in body["points"]]
    assert weeks == sorted(weeks)


def test_backtest_series_skill_matches_the_leaderboard_metric(
    client: TestClient, stations_sample: Engine
) -> None:
    """The chart's skill is the same rolling-origin number the backtest reports."""
    from cloudy.predictions import outlook

    series = outlook.weekly_cloud_series(stations_sample, BERGA_LAT, BERGA_LON, 50.0)
    expected_skill, expected_n = outlook.backtest_skill(series, 1)

    body = client.get(
        "/api/v1/predictions/backtest-series",
        params={"lat": BERGA_LAT, "lon": BERGA_LON, "model": "damped", "lead": 1},
    ).json()
    assert body["n_origins"] == expected_n
    assert body["skill"] == round(expected_skill, 3)


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 48.85, "lon": 2.35},  # outside Sweden
        {"lat": 59.0},  # lone coordinate
        {"lat": BERGA_LAT, "lon": BERGA_LON, "model": "bogus"},  # unknown model
        {"lat": BERGA_LAT, "lon": BERGA_LON, "lead": 3},  # unsupported lead
    ],
)
def test_backtest_series_invalid_params_are_422(
    client: TestClient, params: dict[str, object]
) -> None:
    assert client.get("/api/v1/predictions/backtest-series", params=params).status_code == 422

"""Cross-station evaluation of the weekly model — the static backtest benchmark.

Run once via `cloudy backtest`, never per request: for every active station, run
the weekly rolling-origin backtest for the damped model and collect the lead-1 (and
lead-2) skill vs climatology. The *spread across stations* is the honest answer to
"how good is this model" — most stations beat the normal, with a long good tail
and some flat ones — so we keep the whole per-station list (the UI histograms it)
plus the median as the headline. The shape stays a per-model leaderboard so a
future model can be added and scored on the same stations and harness. Written to
disk; the API only reads.
"""

from __future__ import annotations

from datetime import UTC, datetime
from statistics import median

from sqlalchemy import Engine
from sqlmodel import Session, select

from cloudy.db.models import Station
from cloudy.predictions import outlook
from cloudy.predictions.types import BacktestArtifact, ModelScores

# The default cloud pool radius — the benchmark should reflect how the product
# actually resolves a located query.
_CLOUD_RADIUS = 50.0


def evaluate(engine: Engine) -> BacktestArtifact:
    """Per-station weekly lead-1/2 skill vs climatology for the damped model.

    A station counts only where its lead-1 backtest actually scored origins
    (`n > 0`) — a station with too little history is honestly absent rather than a
    zero.
    """
    with Session(engine) as session:
        stations = list(session.exec(select(Station).where(Station.active)).all())

    damped1: list[float] = []
    damped2: list[float] = []
    for station in stations:
        series = outlook.weekly_cloud_series(engine, station.lat, station.lon, _CLOUD_RADIUS)

        d1, dn1 = outlook.backtest_skill(series, 1)
        d2, _ = outlook.backtest_skill(series, 2)
        if dn1 > 0:
            damped1.append(round(d1 * 100, 1))
            damped2.append(round(d2 * 100, 1))

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "n_stations": len(damped1),
        "models": {
            "damped": _scores(damped1, damped2),
        },
    }


def _scores(lead1: list[float], lead2: list[float]) -> ModelScores:
    """Fold a model's per-station skills into its leaderboard summary + raw spread."""
    return {
        "median_skill_pct": round(median(lead1), 1) if lead1 else 0.0,
        "fraction_beating": round(sum(1 for x in lead1 if x > 0) / len(lead1), 3) if lead1 else 0.0,
        "lead2_median_skill_pct": round(median(lead2), 1) if lead2 else 0.0,
        "lead1_skills": lead1,
    }

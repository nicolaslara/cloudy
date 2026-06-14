"""Typed shapes for the predictions API — the weekly near-term outlook.

One product in two flavours: recent weeks ran some amount off the seasonal normal,
and (because weekly anomalies persist) the next week or two are expected to run a
damped fraction of that off normal. Cloud states it in percentage points; lightning
in lightning-days. Each response carries the recent gap, the per-lead expected
deviation, and the backtested skill so the UI can state it honestly in words.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class PredictionsMeta(TypedDict):
    sources: list[str]
    attribution: str
    generated_at: str


class OutlookLead(TypedDict):
    """One week ahead: how far the model expects to sit off the seasonal normal.

    `expected_anomaly_pct` is the damped recent anomaly (alpha * recent), in cloud
    percentage points — the "+Y%" the outlook sentence quotes. `expected_cloud_pct`
    is the *absolute* prediction — the target week's seasonal normal plus that anomaly,
    clamped 0-100 — so the UI can say "expect ~68% cloud", not just the gap. `alpha` is
    the fraction of the recent gap expected to carry to this lead (the lag-k weekly
    autocorrelation, fading with lead). `skill` is the weekly rolling-origin MAE skill
    vs climatology at this lead — the honest "is this worth saying".
    """

    lead_weeks: int
    alpha: float
    expected_anomaly_pct: float | None
    expected_cloud_pct: float | None
    # The ISO week-of-year this lead forecasts (latest observed week + lead, wrapping
    # the year): lets the UI align a point's week-of-year normal to this lead.
    target_week: int
    skill: float
    n_origins: int


class ModelScores(TypedDict):
    """One model's cross-station backtest result — the spread the UI histograms.

    `lead1_skills` is each station's lead-1 MAE skill (%) vs climatology; the
    summaries headline it. The spread is the honest answer to "how good is this
    model": most stations positive, a long good tail, some flat. Every model on the
    leaderboard reports this same shape so they're compared apples-to-apples.
    """

    median_skill_pct: float
    fraction_beating: float
    lead2_median_skill_pct: float
    lead1_skills: list[float]


class BacktestModels(TypedDict):
    """The leaderboard: every weekly model scored on the same stations and harness.

    One field per model so the comparison is type-safe; a new model adds a field
    here (and its own page). Today: damped persistence.
    """

    damped: ModelScores


class BacktestArtifact(TypedDict):
    """Static cross-station benchmark of the weekly models — computed once.

    Not live data: `cloudy backtest` runs the weekly rolling-origin backtest for
    every active station, for every model, and writes this; the API only reads it.
    `n_stations` is the station universe evaluated; `models` carries each model's
    per-station skill spread so the UI can histogram one and rank them side by side.
    """

    generated_at: str
    n_stations: int
    models: BacktestModels


class SpatialNormalPoint(TypedDict):
    """One week-of-year slot of a point's estimated cloud normal.

    `week` is the ISO week (1..53); `estimated_cloud_pct` is the served model's mean
    estimate for that week across all the years the point's neighbours cover. This is
    the same week-of-year shape the climatology series carries, so the frontend can
    overlay an estimate curve on the Normals chart without adapting.
    """

    week: int
    estimated_cloud_pct: float | None


class SpatialStationMeta(TypedDict):
    """The nearest station to the queried point — the anchor the UI names."""

    station_id: int
    name: str
    distance_km: float


class SpatialNormalResponse(TypedDict):
    """A point's estimated week-of-year cloud normal from the nearby SMHI stations.

    `model` is a string id ("nearest" | "knn") so the source/model toggle can add more
    spatial estimators later without a shape change. `nearest_station` is the closest
    station and `n_neighbours` how many fed the estimate — the honest provenance for a
    point with no station of its own.
    """

    lat: float
    lon: float
    model: str
    nearest_station: SpatialStationMeta
    n_neighbours: int
    series: list[SpatialNormalPoint]
    meta: PredictionsMeta


class CloudOutlook(TypedDict):
    """The near-term cloud outlook: recent gap from normal + the damped forward view.

    Weekly resolution on purpose — month-to-month anomalies barely persist, but
    weekly ones do, so this is where a simple model genuinely beats the normal.
    `recent_anomaly_pct` is the latest observed week's deviation from its
    week-of-year normal; each lead damps it forward. No chart: the UI states it in
    a sentence.
    """

    scope: Literal["station", "sweden"]
    radius_km: int
    recent_anomaly_pct: float | None
    recent_cloud_pct: float | None  # the latest week's absolute cloud %, for context
    weeks_observed: int
    leads: list[OutlookLead]
    meta: PredictionsMeta


class LightningOutlookLead(TypedDict):
    """One week ahead for lightning, mirroring OutlookLead but in lightning-days.

    `expected_anomaly_days` is the damped recent anomaly (alpha * recent), in
    lightning-days — strike-days above or below the week-of-year normal. Same
    damped-persistence machinery as cloud; the unit differs because lightning is
    counted, not measured.
    """

    lead_weeks: int
    alpha: float
    expected_anomaly_days: float | None
    expected_lightning_days: float | None  # absolute: normal + anomaly, floored at 0
    skill: float
    n_origins: int


class LightningOutlook(TypedDict):
    """The near-term lightning outlook — the same damped model, the sparse cousin.

    Lightning is counted in **lightning-days per week** (calendar days with at
    least one discharge in the area), so anomalies are strike-days off the
    week-of-year normal rather than percentage points. The series is zero-filled
    across its observed span — a quiet week is a real 0, not a gap — which is what
    lets a winter lull read as "below an already-low normal" instead of vanishing.

    `as_of_week` is the latest week the series covers (the last week with strikes
    in range): unlike cloud, lightning data can trail the calendar by months out
    of season, so the UI names the date rather than implying "this week". Treat the
    whole statement as indicative — weekly lightning is sparse and bursty.
    """

    scope: Literal["radius", "sweden"]
    radius_km: int | None
    recent_anomaly_days: float | None
    recent_lightning_days: float | None  # the latest week's absolute lightning-days
    weeks_observed: int
    as_of_week: str | None
    leads: list[LightningOutlookLead]
    meta: PredictionsMeta


class BacktestSeriesPoint(TypedDict):
    """One scored target week of the rolling-origin backtest, for the chart.

    `week` is the ISO date (Monday) the forecast was *for*; `actual` is what cloud
    cover that week turned out to be; `forecast` is the model's absolute estimate
    (the as-of-origin normal plus its predicted anomaly, clamped 0-100); `normal` is
    the seasonal-normal baseline the model is judged against. The chart draws all
    three so "does the model sit closer to actual than the flat normal does" is visible.
    """

    week: str
    actual: float
    forecast: float
    normal: float


class BacktestSeriesResponse(TypedDict):
    """A model's forecast-vs-actual over its rolling-origin backtest at one place.

    `points` is the per-target-week series (chronological, scored origins only — the
    warm-up and any unscorable weeks are absent). `skill` and `n_origins` are the same
    rolling-origin MAE skill the leaderboard reports, recomputed here so the chart and
    the number can't disagree. `model` says which forward model produced the forecast.
    """

    scope: Literal["station", "sweden"]
    radius_km: int
    model: Literal["damped"]
    lead_weeks: int
    skill: float
    n_origins: int
    points: list[BacktestSeriesPoint]
    meta: PredictionsMeta

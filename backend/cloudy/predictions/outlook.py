"""Near-term outlook — damped anomaly persistence at WEEKLY resolution.

Monthly anomalies barely persist (the month-ahead forecast is ~climatology), but
weekly ones do — lag-1 weekly autocorrelation runs ~0.3 Sweden-wide and higher
locally — so this is where a simple model genuinely beats the seasonal normal.

The statement is deliberately plain: recent weeks have run some amount off normal,
and because that gap persists (damped), the next week or two are expected to run a
fraction of it off normal. That fraction is `alpha(k)`, the lag-k autocorrelation
of weekly anomalies learned from history; it fades with lead, so the outlook melts
back into the normal within a few weeks. `alpha=0` would reproduce the normal
exactly, which is why this can only help on average.

Two products share the machinery. Cloud is the clean, continuous case the owner
framed ("differ by +-X%"). Lightning is the sparse cousin: the same damped model,
but counted in weekly lightning-days and stated as an indicative second line —
weekly strikes are bursty and seasonal, so the series is zero-filled and the
statement is hedged rather than headlined.

A note on honesty in the backtest: the live outlook and the Normals product define
the seasonal normal over all data we hold (which at forecast time is all *past*
data — causal). But the rolling-origin backtest simulates standing in the past, so
it must rebuild the normal from only the weeks up to each origin; otherwise a
simulated past forecast would be scored against a normal that averaged in its own
future. So the live path forms anomalies with `full_anomalies`, while the backtest
(`rolling_skill`) re-derives the normal per origin — the shared rolling harness any
forward `predict` plugs into.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, timedelta
from statistics import fmean

from sqlalchemy import Engine, text
from sqlmodel import Session

from cloudy.core.series_sql import haversine_filter_sql
from cloudy.core.spatial import SpatialBounds
from cloudy.ingest import stations
from cloudy.predictions import persistence
from cloudy.predictions.types import (
    CloudOutlook,
    LightningOutlook,
    LightningOutlookLead,
    OutlookLead,
    PredictionsMeta,
)

# Resolve which stations a cloud query pools, identical to the climatology rule:
# the active stations within the radius, the single nearest if the radius is empty,
# or every active station when no location is given.
_SWEDEN_FILTER = "station_id IN (SELECT id FROM stations WHERE active)"


def _resolve_cloud_filter(
    engine: Engine, lat: float | None, lon: float | None, radius_km: float
) -> str:
    if lat is None or lon is None:
        return _SWEDEN_FILTER
    with Session(engine) as session:
        members = stations.active_within_radius(session, lat, lon, radius_km)
        if not members:
            members = [stations.nearest_active(session, lat, lon)]
    # Station ids are our own ints, so inlining them is safe and sidesteps the
    # expanding-bindparam dance an IN clause would otherwise need.
    ids = [s.id for s, _ in members]
    return f"station_id IN ({', '.join(str(i) for i in ids)})"


# We state the next two weeks (the owner's "1-2 weeks"); beyond that alpha is ~0.
LEADS = (1, 2)
# Warm-up before a backtest origin counts: ~2 years of weeks, so a skill number
# rests on a real training span rather than a handful of lucky weeks.
MIN_TRAIN_WEEKS = 104

# Mean cloud percent per ISO week. `week_start` is the Monday of the ISO week, used
# to lay the rows onto a gap-free calendar grid downstream. One row per observed ISO
# week, chronological; weeks with no observation simply don't appear here.
_WEEKLY_CLOUD_SQL = """
    SELECT
        date_trunc('week', ts_utc)::date AS week_start,
        avg(cloud_pct) AS mean_cloud_pct
    FROM cloud_hourly
    WHERE {station_filter}
      AND cloud_pct IS NOT NULL
    GROUP BY week_start
    ORDER BY week_start
"""


# A forward model for the backtest: given the anomaly series and its weeks-of-year
# known up to `origin` (causally de-meaned), predict the anomaly `lead` weeks out.
# The series lives on a gap-free weekly calendar grid, so a missing week is `None` —
# index distance is calendar distance. A forward model differs only here, so any
# variant shares one rolling-origin harness.
PredictFn = Callable[[Sequence[float | None], list[int], int, int], "float | None"]


def cloud_outlook(
    engine: Engine,
    lat: float | None,
    lon: float | None,
    radius_km: float,
    *,
    meta: PredictionsMeta,
) -> CloudOutlook:
    """Recent weekly cloud gap from normal + the damped 1-2 week forward view."""
    series = weekly_cloud_series(engine, lat, lon, radius_km)
    anomalies = full_anomalies(series)
    recent = anomalies[-1] if anomalies else None
    # The week-of-year normal lets us turn each damped anomaly into an absolute cloud %.
    woys = [woy for woy, _ in series]
    values = [value for _, value in series]
    climatology = _climatology(woys, values, len(series) - 1) if series else {}
    last_woy = woys[-1] if woys else 0
    leads: list[OutlookLead] = []
    for k in LEADS:
        alpha = persistence.fit_alpha(anomalies, k)
        skill, n = backtest_skill(series, k)
        expected_anomaly = alpha * recent if recent is not None else None
        leads.append(
            {
                "lead_weeks": k,
                "alpha": round(alpha, 3),
                "expected_anomaly_pct": round(expected_anomaly, 1)
                if expected_anomaly is not None
                else None,
                "expected_cloud_pct": _expected_absolute(
                    climatology, last_woy, k, expected_anomaly, low=0.0, high=100.0, ndigits=1
                ),
                "target_week": _target_week(last_woy, k),
                "skill": round(skill, 3),
                "n_origins": n,
            }
        )

    return {
        "scope": "station" if (lat is not None and lon is not None) else "sweden",
        "radius_km": int(radius_km),
        "recent_anomaly_pct": round(recent, 1) if recent is not None else None,
        "recent_cloud_pct": _round_or_none(_latest_present(values)),
        "weeks_observed": sum(1 for _, value in series if value is not None),
        "leads": leads,
        "meta": meta,
    }


def weekly_cloud_series(
    engine: Engine, lat: float | None, lon: float | None, radius_km: float
) -> list[tuple[int, float | None]]:
    """Chronological `(week_of_year, mean cloud percent)` on a gap-free week grid.

    The *raw* weekly series — no de-meaning — laid onto a complete calendar grid from
    the first observed week to the last, so a week with no observation is an explicit
    `None`, not a missing row. That makes list index equal calendar distance, which is
    what lets the damped lag refuse to span a hole (a "lag-1" that secretly jumped a
    month would otherwise corrupt the signal).

    Anomalies are formed downstream, and by whom matters: the live outlook subtracts
    the all-data normal (built only from past data at forecast time, so causal), while
    the backtest rebuilds the normal causally *per origin*. Both need the raw values,
    not a pre-baked anomaly — the single source the two models share.
    """
    station_filter = _resolve_cloud_filter(engine, lat, lon, radius_km)
    with engine.connect() as conn:
        rows = conn.execute(text(_WEEKLY_CLOUD_SQL.format(station_filter=station_filter))).all()
    if not rows:
        return []
    observed = {r.week_start: float(r.mean_cloud_pct) for r in rows}
    return _weekly_grid(rows[0].week_start, rows[-1].week_start, observed)


def weekly_cloud_series_dated(
    engine: Engine, lat: float | None, lon: float | None, radius_km: float
) -> list[tuple[date, int, float | None]]:
    """`weekly_cloud_series` but carrying each row's week-start date.

    The backtest-over-time chart needs a real calendar x-axis, which the (woy, value)
    series throws away. Same pooled stations, same gap-free weekly grid — just the
    Monday of each ISO week alongside its week-of-year and mean cloud.
    """
    station_filter = _resolve_cloud_filter(engine, lat, lon, radius_km)
    with engine.connect() as conn:
        rows = conn.execute(text(_WEEKLY_CLOUD_SQL.format(station_filter=station_filter))).all()
    if not rows:
        return []
    observed = {r.week_start: float(r.mean_cloud_pct) for r in rows}
    grid: list[tuple[date, int, float | None]] = []
    cursor = rows[0].week_start
    last = rows[-1].week_start
    one_week = timedelta(weeks=1)
    while cursor <= last:
        grid.append((cursor, cursor.isocalendar().week, observed.get(cursor)))
        cursor += one_week
    return grid


def _weekly_grid(
    first: date, last: date, observed: dict[date, float], fill: float | None = None
) -> list[tuple[int, float | None]]:
    """Lay observed weekly values onto a gap-free Monday-to-Monday calendar grid.

    Each cell is `(week_of_year, value)`; the week-of-year comes from the grid date
    itself so empty cells still occupy their slot. `fill` is what an unobserved week
    becomes: `None` for cloud (a gap is genuinely missing) or `0.0` for lightning (a
    quiet week is a real zero). Either way the grid makes list index == calendar
    distance, which is what lets the damped lag refuse to span a hole.
    """
    grid: list[tuple[int, float | None]] = []
    cursor = first
    one_week = timedelta(weeks=1)
    while cursor <= last:
        grid.append((cursor.isocalendar().week, observed.get(cursor, fill)))
        cursor += one_week
    return grid


def full_anomalies(series: Sequence[tuple[int, float | None]]) -> list[float | None]:
    """De-mean a weekly `(week_of_year, value)` series by its all-data normal.

    The normal is each week-of-year's mean across every (present) year in the series.
    Correct for the *live* outlook and the Normals product, where "all data" is all
    the data we hold — which at forecast time is all *past* data, so nothing leaks. A
    missing week stays `None` (no value to de-mean). The backtest must NOT use this
    (it would hand a simulated past origin a normal that averaged in later years);
    `rolling_skill` rebuilds the normal causally instead.
    """
    if not series:
        return []
    woys = [woy for woy, _ in series]
    values = [value for _, value in series]
    climatology = _climatology(woys, values, len(series) - 1)
    return [None if value is None else value - climatology[woy] for woy, value in series]


def _climatology(
    woys: Sequence[int], values: Sequence[float | None], end_idx: int
) -> dict[int, float]:
    """Mean of the *present* values per week-of-year over indices `0..end_idx`."""
    total: dict[int, float] = {}
    count: dict[int, int] = {}
    for i in range(end_idx + 1):
        value = values[i]
        if value is None:
            continue
        total[woys[i]] = total.get(woys[i], 0.0) + value
        count[woys[i]] = count.get(woys[i], 0) + 1
    return {woy: total[woy] / count[woy] for woy in total}


def _expected_absolute(
    climatology: dict[int, float],
    last_woy: int,
    lead: int,
    expected_anomaly: float | None,
    *,
    low: float,
    high: float | None,
    ndigits: int,
) -> float | None:
    """The absolute expected value `lead` weeks out: the *target* week's normal plus the
    damped anomaly, clamped to a sensible range.

    This is what turns the outlook from "+8 pp off normal" into "expect ~68% cloud" — the
    number a user actually wants. None when we hold no normal for that future week or have
    no anomaly to carry forward (then the UI falls back to stating the normal alone).
    """
    if expected_anomaly is None:
        return None
    target_woy = _target_week(last_woy, lead)
    base = climatology.get(target_woy)
    if base is None:
        return None
    value = max(low, base + expected_anomaly)
    if high is not None:
        value = min(high, value)
    return round(value, ndigits)


def _target_week(last_woy: int, lead: int) -> int:
    """The ISO week-of-year `lead` weeks after `last_woy`, wrapping a 52-week year.

    The week the lead forecasts — what the UI uses to read a point's week-of-year
    normal at the same slot the damped anomaly is carried into. We wrap on 52 (not 53)
    because the climatology is keyed 1..52; the rare ISO week 53 folds into 52's slot.
    """
    return ((last_woy - 1 + lead) % 52) + 1


def _latest_present(values: Sequence[float | None]) -> float | None:
    """The most recent non-missing value — the 'recent' absolute level for the outlook."""
    return next((value for value in reversed(values) if value is not None), None)


def _round_or_none(value: float | None, ndigits: int = 1) -> float | None:
    return round(value, ndigits) if value is not None else None


def rolling_skill(
    series: Sequence[tuple[int, float | None]], lead: int, predict: PredictFn
) -> tuple[float, int]:
    """Causal weekly rolling-origin MAE skill vs climatology at `lead` weeks.

    The honest backtest: walk an expanding window over the raw series; at each origin
    past the warm-up, rebuild the week-of-year normal from *only* the weeks up to that
    origin, de-mean the history into causal anomalies, and ask `predict` for the
    anomaly `lead` weeks out. Score it and the climatology baseline (which predicts
    anomaly 0) against the actual — itself de-meaned with that same as-of-origin
    normal, so neither side peeks at the future. Skill = 1 - model_MAE/baseline_MAE.
    Origins whose target week-of-year hasn't been seen yet, or where `predict`
    abstains, are skipped rather than scored.
    """
    woys = [woy for woy, _ in series]
    values = [value for _, value in series]
    n = len(series)
    total: dict[int, float] = {}
    count: dict[int, int] = {}
    model_err: list[float] = []
    base_err: list[float] = []
    for origin in range(n):
        # Fold week `origin` into the running normal first: it's the "current" week,
        # observed by a forecaster standing here, so the as-of-origin normal includes
        # it (when present — a gap contributes nothing).
        here = values[origin]
        if here is not None:
            total[woys[origin]] = total.get(woys[origin], 0.0) + here
            count[woys[origin]] = count.get(woys[origin], 0) + 1
        if origin < MIN_TRAIN_WEEKS or origin + lead >= n:
            continue
        # Need both ends of the lead present to score (and the grid makes them exactly
        # `lead` calendar weeks apart); a never-seen target season is unscorable too.
        actual = values[origin + lead]
        target_woy = woys[origin + lead]
        if here is None or actual is None or target_woy not in count:
            continue
        climatology = {woy: total[woy] / count[woy] for woy in total}
        causal: list[float | None] = []
        for i in range(origin + 1):
            value = values[i]
            causal.append(None if value is None else value - climatology[woys[i]])
        prediction = predict(causal, woys, origin, lead)
        if prediction is None:
            continue
        target = actual - climatology[target_woy]
        model_err.append(abs(target - prediction))
        base_err.append(abs(target))  # climatology predicts zero anomaly
    if not model_err:
        return 0.0, 0
    base_mae = fmean(base_err)
    skill = 1.0 - fmean(model_err) / base_mae if base_mae else 0.0
    return skill, len(model_err)


def damped_predict(
    causal: Sequence[float | None], woys: list[int], origin: int, lead: int
) -> float | None:
    """The damped forward model: a fraction (alpha) of the latest causal anomaly.

    Fit alpha on the anomalies known at the origin and carry a damped fraction of the
    latest anomaly forward. alpha floored at 0 means the worst case collapses to the
    baseline, which is why damped can't lose on average. The shared predictor for both
    the skill backtest and the forecast-vs-actual series, so they can't diverge.
    """
    current = causal[origin]
    if current is None:  # rolling_skill only scores present origins, but be explicit
        return None
    return persistence.fit_alpha(causal, lead) * current


def backtest_skill(series: Sequence[tuple[int, float | None]], lead: int) -> tuple[float, int]:
    """Causal rolling-origin skill of damped persistence vs climatology."""
    return rolling_skill(series, lead, damped_predict)


def rolling_backtest(
    series_dated: Sequence[tuple[date, int, float | None]], lead: int, predict: PredictFn
) -> tuple[list[dict[str, object]], float, int]:
    """The rolling-origin backtest as a per-target-week record list (for plotting).

    The visual twin of `rolling_skill`: identical causal walk — rebuild the
    week-of-year normal from only the weeks up to each origin, de-mean to anomalies,
    ask `predict` for the lead-ahead anomaly — but instead of only accumulating the
    error it emits, per scored target week, the absolute `actual`, the model
    `forecast` (normal + predicted anomaly, clamped 0-100), and the seasonal `normal`
    baseline. The returned skill is computed the same way as `rolling_skill`, so the
    chart and the headline number agree by construction.
    """
    dates = [d for d, _, _ in series_dated]
    woys = [w for _, w, _ in series_dated]
    values = [v for _, _, v in series_dated]
    n = len(series_dated)
    total: dict[int, float] = {}
    count: dict[int, int] = {}
    model_err: list[float] = []
    base_err: list[float] = []
    points: list[dict[str, object]] = []
    for origin in range(n):
        here = values[origin]
        if here is not None:
            total[woys[origin]] = total.get(woys[origin], 0.0) + here
            count[woys[origin]] = count.get(woys[origin], 0) + 1
        if origin < MIN_TRAIN_WEEKS or origin + lead >= n:
            continue
        actual = values[origin + lead]
        target_woy = woys[origin + lead]
        if here is None or actual is None or target_woy not in count:
            continue
        climatology = {woy: total[woy] / count[woy] for woy in total}
        causal: list[float | None] = []
        for i in range(origin + 1):
            value = values[i]
            causal.append(None if value is None else value - climatology[woys[i]])
        prediction = predict(causal, woys, origin, lead)
        if prediction is None:
            continue
        normal = climatology[target_woy]
        model_err.append(abs((actual - normal) - prediction))
        base_err.append(abs(actual - normal))
        points.append(
            {
                "week": dates[origin + lead].isoformat(),
                "actual": round(actual, 1),
                "forecast": round(max(0.0, min(100.0, normal + prediction)), 1),
                "normal": round(normal, 1),
            }
        )
    if not model_err:
        return [], 0.0, 0
    base_mae = fmean(base_err)
    skill = 1.0 - fmean(model_err) / base_mae if base_mae else 0.0
    return points, round(skill, 3), len(model_err)


def cloud_backtest_series(
    engine: Engine,
    lat: float | None,
    lon: float | None,
    radius_km: float,
    lead: int,
    *,
    meta: PredictionsMeta,
) -> dict[str, object]:
    """Damped persistence's forecast-vs-actual over the rolling-origin backtest."""
    series = weekly_cloud_series_dated(engine, lat, lon, radius_km)
    points, skill, n = rolling_backtest(series, lead, damped_predict)
    located = lat is not None and lon is not None
    return {
        "scope": "station" if located else "sweden",
        "radius_km": int(radius_km),
        "model": "damped",
        "lead_weeks": lead,
        "skill": skill,
        "n_origins": n,
        "points": points,
        "meta": meta,
    }


# --- Lightning: the same damped model on weekly lightning-days -----------------

_HAVERSINE = haversine_filter_sql()

# Distinct lightning-days per ISO week inside the area. We take DISTINCT day first
# so a busy storm day counts once (the metric is "days with strikes", matching the
# climatology), then group those days into weeks. Weeks with no strikes simply
# don't appear — we zero-fill them in Python so the anomaly series is continuous.
_WEEKLY_LIGHTNING_SQL = """
    WITH strike_days AS (
        SELECT DISTINCT day
        FROM lightning_events
        WHERE lat BETWEEN :lat_min AND :lat_max
          AND lon BETWEEN :lon_min AND :lon_max
          AND {haversine}
    )
    SELECT date_trunc('week', day)::date AS week_start, count(*)::int AS lightning_days
    FROM strike_days
    GROUP BY week_start
    ORDER BY week_start
"""


def lightning_outlook(
    engine: Engine,
    lat: float | None,
    lon: float | None,
    radius_km: float,
    *,
    meta: PredictionsMeta,
) -> LightningOutlook:
    """Recent weekly lightning-day gap from normal + the damped 1-2 week view.

    Structurally identical to `cloud_outlook`, but the unit is lightning-days and
    the series can trail the calendar, so we also report the week it's `as_of`.
    """
    series, as_of = weekly_lightning_series(engine, lat, lon, radius_km)
    anomalies = full_anomalies(series)
    recent = anomalies[-1] if anomalies else None
    woys = [woy for woy, _ in series]
    values = [value for _, value in series]
    climatology = _climatology(woys, values, len(series) - 1) if series else {}
    last_woy = woys[-1] if woys else 0
    leads: list[LightningOutlookLead] = []
    for k in LEADS:
        alpha = persistence.fit_alpha(anomalies, k)
        skill, n = backtest_skill(series, k)
        expected_anomaly = alpha * recent if recent is not None else None
        leads.append(
            {
                "lead_weeks": k,
                "alpha": round(alpha, 3),
                "expected_anomaly_days": round(expected_anomaly, 2)
                if expected_anomaly is not None
                else None,
                # Lightning-days can't go negative; no upper clamp (a stormy week can be 7).
                "expected_lightning_days": _expected_absolute(
                    climatology, last_woy, k, expected_anomaly, low=0.0, high=None, ndigits=2
                ),
                "skill": round(skill, 3),
                "n_origins": n,
            }
        )

    located = lat is not None and lon is not None
    return {
        "scope": "radius" if located else "sweden",
        "radius_km": int(radius_km) if located else None,
        "recent_anomaly_days": round(recent, 2) if recent is not None else None,
        "recent_lightning_days": _round_or_none(_latest_present(values), 2),
        "weeks_observed": len(series),
        "as_of_week": as_of.isoformat() if as_of is not None else None,
        "leads": leads,
        "meta": meta,
    }


def weekly_lightning_series(
    engine: Engine, lat: float | None, lon: float | None, radius_km: float
) -> tuple[list[tuple[int, float | None]], date | None]:
    """Chronological `(week_of_year, lightning-days)` for the area, plus the last week.

    The query returns only weeks that had strikes; the grid fills the gaps between the
    first and last such week with `fill=0.0` — a quiet week is a real 0 lightning-days,
    not missing data (unlike cloud, where an absent week is genuinely unobserved). Raw
    counts (not anomalies) so the live outlook and the causal backtest can each form
    the normal as they need it. Returns an empty series (and no `as_of`) when the area
    has never seen a strike.
    """
    bounds = (
        SpatialBounds.from_radius(lat, lon, radius_km)
        if (lat is not None and lon is not None)
        else SpatialBounds.sweden()
    )
    sql = text(_WEEKLY_LIGHTNING_SQL.format(haversine=_HAVERSINE))
    with engine.connect() as conn:
        rows = conn.execute(sql, _lightning_bbox_params(bounds)).all()
    if not rows:
        return [], None

    observed = {r.week_start: float(r.lightning_days) for r in rows}
    last = rows[-1].week_start
    return _weekly_grid(rows[0].week_start, last, observed, fill=0.0), last


def _lightning_bbox_params(bounds: SpatialBounds) -> dict[str, object]:
    # Mirrors climatology.lightning: radius mode binds the exact circle; Sweden mode
    # leaves use_radius false so the haversine clause passes everything in the (huge)
    # country bbox. Unused center/radius binds are harmless zeros.
    return {
        "lat_min": bounds.min_lat,
        "lat_max": bounds.max_lat,
        "lon_min": bounds.min_lon,
        "lon_max": bounds.max_lon,
        "use_radius": bounds.use_radius,
        "lat": bounds.center_lat if bounds.use_radius else 0.0,
        "lon": bounds.center_lon if bounds.use_radius else 0.0,
        "radius_km": bounds.radius_km if bounds.use_radius else 0.0,
    }

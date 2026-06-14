"""Typed response shapes for the climatology ("Normals") API.

These mirror the meta/attribution/source convention used by the exploration
responses (sources + "Source: SMHI" + generated_at) so the frontend can treat
every cloudy payload the same way. A "period" here is not an instant on a
timeline but a *recurring* bucket — calendar month 1-12, day-of-year 1-366, or a
calendar year — because a normal answers "what is typical for this slot",
averaged across all the years we hold.
"""

from __future__ import annotations

from typing import Literal, TypedDict

# What a normal is grouped by. Distinct from the exploration "resolution": there
# is no raw/hour/week here — a climatology only makes sense at recurring slots.
Period = Literal["day", "month", "year"]


class ClimatologyMeta(TypedDict):
    sources: list[str]
    attribution: str
    generated_at: str
    # How many distinct calendar years fed the normal. This is the honesty knob:
    # a "normal" from one or two years is barely a normal, and the client can
    # warn on a thin baseline instead of presenting it as settled truth.
    year_count: int


class ClimatologyStationMeta(TypedDict):
    station_id: int
    name: str
    distance_km: float


# --- Cloud --------------------------------------------------------------------


class CloudNormalPoint(TypedDict):
    """The typical cloud cover for one recurring slot, with a spread band.

    The percentile triple (p10/p50/p90) is what turns a flat average into an
    honest expectation: a place can average 60% cloud either by being reliably
    grey or by swinging between clear and overcast, and only the band shows that.
    Counts are carried so a thin slot can't masquerade as a confident one.
    """

    period: str
    mean_cloud_pct: float | None
    p10_cloud_pct: float | None
    p50_cloud_pct: float | None
    p90_cloud_pct: float | None
    # Share of usable hours in each sky state (percent, ~sums to 100). This is the
    # honest spread for U-shaped cloud — a month is "grey" because it's overcast
    # most hours, not because it sits at a flat mean — and it's what the stacked
    # column in the UI draws. clear <25%, overcast >75%, partial in between.
    clear_pct: float | None
    partial_pct: float | None
    overcast_pct: float | None
    observed_count: int
    year_count: int


class CloudCurrentMonthExpectation(TypedDict):
    """Live expectation for the month in progress: observed-so-far + tail.

    `expected_pct` blends the mean of hours already observed this month with the
    month's climatological mean for the days not yet elapsed, weighted by how
    much of the month each part covers. `baseline_pct` is the plain all-years
    monthly normal — what you'd have guessed with no current observations — so
    the UI can show how far this month is running from typical.
    """

    month: int
    observed_so_far_pct: float | None
    observed_days: int
    climatology_tail_pct: float | None
    expected_pct: float | None
    baseline_pct: float | None


class CloudClimatologyResponse(TypedDict):
    # "station" when resolved to the nearest station, "sweden" when aggregated
    # across every active station. station is null in the Sweden-wide case;
    # station_count says how many stations fed that aggregate.
    scope: Literal["station", "sweden"]
    station: ClimatologyStationMeta | None
    station_count: int | None
    period: Period
    series: list[CloudNormalPoint]
    current_month: CloudCurrentMonthExpectation
    meta: ClimatologyMeta


# --- Lightning ----------------------------------------------------------------


class LightningNormalPoint(TypedDict):
    """The typical lightning activity for one recurring slot within a radius.

    `strike_day_probability` is the headline: the chance that any given day in
    this slot sees at least one discharge nearby — the same notion as SMHI's
    thunder-day maps. `expected_lightning_days` is that probability expressed as
    days-per-occurrence of the slot (e.g. per July), and `mean_count` is the raw
    discharge volume for callers who want intensity rather than incidence.
    """

    period: str
    strike_day_probability: float | None
    expected_lightning_days: float | None
    mean_count: float | None
    year_count: int


class LightningCurrentMonthExpectation(TypedDict):
    """Live lightning expectation for the month in progress.

    Lightning days are additive (a count, not an average), so the blend is a sum:
    the days already observed this month plus the climatological expectation for
    the days still to come. `baseline_days` is the plain monthly normal.
    """

    month: int
    observed_lightning_days: int
    observed_days: int
    climatology_tail_days: float | None
    expected_lightning_days: float | None
    baseline_days: float | None


class LightningClimatologyResponse(TypedDict):
    # "radius" for a point+radius normal, "sweden" for the whole country. The
    # lat/lon/radius_km echo the filter and are null in the Sweden-wide case.
    scope: Literal["radius", "sweden"]
    lat: float | None
    lon: float | None
    radius_km: int | None
    period: Period
    series: list[LightningNormalPoint]
    current_month: LightningCurrentMonthExpectation
    meta: ClimatologyMeta

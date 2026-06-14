"""Truth tests for lightning normals against the isolated test database.

Lightning normals turn on two things: the radius filter (events outside the
circle must not count) and the lightning-day denominator (days with strikes over
days we could have observed). The fixtures seed strikes across two years, inside
and outside the radius, so both can be asserted directly.
"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from cloudy.climatology import lightning
from cloudy.climatology.query import ClimatologyLightningQuery
from cloudy.climatology.types import LightningNormalPoint
from cloudy.db.models import LightningEvent

# A center far from anything else; near/far points are placed relative to it.
CENTER_LAT, CENTER_LON = 59.0, 18.0
# ~0.05 deg lat north is ~5.6 km — comfortably inside 10 km.
NEAR_LAT, NEAR_LON = 59.05, 18.0
# ~0.5 deg lat north is ~55 km — outside both 10 and 25 km.
FAR_LAT, FAR_LON = 59.5, 18.0


def _event(when: datetime, lat: float, lon: float) -> LightningEvent:
    return LightningEvent(
        ts_utc=when,
        day=when.date(),
        lat=lat,
        lon=lon,
        peak_current_ka=-12.0,
        multiplicity=0,
        number_of_sensors=5,
        cloud_indicator=0,
    )


@pytest.fixture
def engine(db: Engine) -> Engine:
    rows: list[LightningEvent] = []
    # Two July lightning-days near the center in each of two years (4 near
    # lightning-days total across the two Julys), plus a second strike on one day
    # to prove "lightning day" counts the day once, not the strikes.
    for year in (2020, 2021):
        rows.append(_event(datetime(year, 7, 10, 14, tzinfo=UTC), NEAR_LAT, NEAR_LON))
        rows.append(_event(datetime(year, 7, 10, 15, tzinfo=UTC), NEAR_LAT, NEAR_LON))
        rows.append(_event(datetime(year, 7, 20, 16, tzinfo=UTC), NEAR_LAT, NEAR_LON))
    # A far strike on a day with no near strike: must be excluded entirely.
    rows.append(_event(datetime(2020, 7, 15, 12, tzinfo=UTC), FAR_LAT, FAR_LON))
    with Session(db) as session:
        session.add_all(rows)
        session.commit()
    return db


def _july(engine: Engine, radius_km: int) -> LightningNormalPoint:
    query = ClimatologyLightningQuery(
        lat=CENTER_LAT,
        lon=CENTER_LON,
        period="month",
        radius_km=radius_km,  # type: ignore[arg-type]
    )
    body = lightning.compute(engine, query, datetime(2022, 1, 15, tzinfo=UTC))
    return {p["period"]: p for p in body["series"]}["7"]


def test_expected_lightning_days_per_july(engine: Engine) -> None:
    july = _july(engine, 10)
    # 2 distinct near lightning-days per July, over 2 Julys -> 2.0 days/July.
    assert july["expected_lightning_days"] == 2.0
    assert july["year_count"] == 2
    # 3 near strikes per year (two on the 10th, one on the 20th) -> mean 3.0.
    assert july["mean_count"] == 3.0


def test_strike_day_probability_uses_calendar_denominator(engine: Engine) -> None:
    july = _july(engine, 10)
    # Observed span is 2020-07-10 .. 2021-07-20. July days in that span: 22 days
    # of July 2020 (the 10th onward) plus 20 of July 2021 = 42 candidate days; 4
    # of them had strikes. The denominator is honest about partial-month coverage.
    assert july["strike_day_probability"] == round(4 / 42, 3)


def test_radius_excludes_far_events(engine: Engine) -> None:
    # The far strike is the only event on 2020-07-15; if the radius leaked it,
    # the strike count and lightning-days would both rise. They don't.
    july = _july(engine, 25)
    assert july["mean_count"] == 3.0  # far strike still excluded at 25 km too


def test_sweden_wide_counts_every_event(engine: Engine) -> None:
    """With no location the normal spans all of Sweden, so the far strike the
    radius excludes is now counted — scope 'sweden', no lat/lon/radius echo."""
    query = ClimatologyLightningQuery(period="month")  # no location
    body = lightning.compute(engine, query, datetime(2022, 1, 15, tzinfo=UTC))

    assert body["scope"] == "sweden"
    assert body["lat"] is None
    assert body["lon"] is None
    assert body["radius_km"] is None

    july = {p["period"]: p for p in body["series"]}["7"]
    # Near lightning-days (Jul 10 & 20 each year) = 4, plus the far Jul 15 2020 the
    # radius dropped = 5 distinct days over 2 Julys -> 2.5 days/July.
    assert july["expected_lightning_days"] == 2.5


def test_current_month_blends_observed_days_and_tail(engine: Engine) -> None:
    """A July in progress: observed near lightning-days so far + climatology tail."""
    with Session(engine) as session:
        session.add_all(
            [
                _event(datetime(2022, 7, 3, 12, tzinfo=UTC), NEAR_LAT, NEAR_LON),
                _event(datetime(2022, 7, 5, 13, tzinfo=UTC), NEAR_LAT, NEAR_LON),
            ]
        )
        session.commit()

    query = ClimatologyLightningQuery(lat=CENTER_LAT, lon=CENTER_LON, period="month", radius_km=10)
    # July 8th: days 1-7 elapsed, 24 remaining in a 31-day month.
    body = lightning.compute(engine, query, datetime(2022, 7, 8, 9, tzinfo=UTC))
    current = body["current_month"]

    assert current["month"] == 7
    assert current["observed_lightning_days"] == 2  # the 3rd and the 5th
    assert current["observed_days"] == 7
    assert current["climatology_tail_days"] is not None
    # Expectation is observed + tail; baseline is the full-month climatology rate.
    assert current["expected_lightning_days"] == round(2 + current["climatology_tail_days"], 2)
    assert current["baseline_days"] is not None


def test_first_day_in_span_helper_counts_calendar_days() -> None:
    # Direct check of the denominator helper: month 7 spanning two partial Julys.
    # July 2020 contributes the 10th..31st (22 days), July 2021 the 1st..20th (20).
    days = lightning._observed_days_for_slot("month", 7, date(2020, 7, 10), date(2021, 7, 20))
    assert days == 22 + 20

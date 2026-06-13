from datetime import date

import pytest

from cloudy.core.series_plan import (
    MAX_RAW_LIGHTNING_EVENTS,
    QueryRejected,
    bucket_count,
    choose_target_points,
    plan_series,
)


def test_target_points_uses_width_and_clamps() -> None:
    assert choose_target_points(100) == 300
    assert choose_target_points(1200) == 1800
    assert choose_target_points(5000) == 3000
    assert choose_target_points(1200, max_points=600) == 600


def test_auto_cloud_uses_raw_for_small_ranges() -> None:
    plan = plan_series("cloud", date(2024, 1, 1), date(2024, 1, 2), "auto", width_px=1000)
    assert plan.resolved_resolution == "raw"
    assert plan.mode == "raw"
    assert plan.estimated_points == 48


def test_auto_cloud_uses_semantic_resolution_for_large_ranges() -> None:
    plan = plan_series("cloud", date(2015, 1, 1), date(2026, 1, 1), "auto", width_px=1200)
    assert plan.resolved_resolution == "month"
    assert plan.estimated_points == bucket_count("month", date(2015, 1, 1), date(2026, 1, 1))


def test_auto_cloud_uses_week_for_year_windows() -> None:
    plan = plan_series("cloud", date(2025, 6, 13), date(2026, 6, 12), "auto", width_px=1200)
    assert plan.resolved_resolution == "week"
    assert plan.estimated_points == bucket_count("week", date(2025, 6, 13), date(2026, 6, 12))


def test_manual_day_rejects_when_too_many_buckets() -> None:
    with pytest.raises(QueryRejected) as exc:
        plan_series("cloud", date(2015, 1, 1), date(2026, 1, 1), "day", width_px=1200)
    assert exc.value.code == "too_many_buckets_for_response"
    assert exc.value.suggested_aggregation == "month"


def test_manual_lightning_day_rejects_without_event_count() -> None:
    with pytest.raises(QueryRejected) as exc:
        plan_series("lightning", date(2015, 1, 1), date(2026, 1, 1), "day", width_px=1200)
    assert exc.value.code == "too_many_buckets_for_response"
    assert exc.value.suggested_aggregation == "month"


def test_auto_lightning_can_use_raw_for_low_event_count() -> None:
    plan = plan_series(
        "lightning",
        date(2024, 7, 1),
        date(2024, 7, 1),
        "auto",
        width_px=1200,
        lightning_event_count=100,
    )
    assert plan.resolved_resolution == "raw"
    assert plan.mode == "raw"


def test_auto_lightning_uses_hour_for_short_multi_day_ranges() -> None:
    plan = plan_series(
        "lightning",
        date(2024, 7, 1),
        date(2024, 7, 7),
        "auto",
        width_px=1200,
        lightning_event_count=10,
    )
    assert plan.resolved_resolution == "hour"
    assert plan.mode == "aggregate"


def test_auto_lightning_uses_week_for_year_windows() -> None:
    plan = plan_series(
        "lightning",
        date(2025, 6, 13),
        date(2026, 6, 12),
        "auto",
        width_px=1200,
        lightning_event_count=600_000,
    )
    assert plan.resolved_resolution == "week"
    assert plan.mode == "aggregate"


def test_auto_lightning_uses_month_for_multi_year_windows() -> None:
    plan = plan_series(
        "lightning",
        date(2015, 1, 1),
        date(2026, 6, 12),
        "auto",
        width_px=1200,
        lightning_event_count=4_200_000,
    )
    assert plan.resolved_resolution == "month"
    assert plan.mode == "aggregate"


def test_manual_raw_lightning_rejects_over_cap() -> None:
    with pytest.raises(QueryRejected) as exc:
        plan_series(
            "lightning",
            date(2024, 7, 1),
            date(2024, 7, 31),
            "raw",
            width_px=1200,
            lightning_event_count=MAX_RAW_LIGHTNING_EVENTS + 1,
        )
    assert exc.value.code == "too_many_points_for_raw_response"
    assert exc.value.limit == MAX_RAW_LIGHTNING_EVENTS

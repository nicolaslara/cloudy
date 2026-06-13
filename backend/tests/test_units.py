"""Sentinel and unit rules for cloud cover normalization."""

import pytest

from cloudy.core.units import normalize_cloud_pct


@pytest.mark.parametrize(
    ("raw", "octas", "expected"),
    [
        (0, False, 0.0),
        (50, False, 50.0),
        (100, False, 100.0),
        (4, True, 50.0),
        (8, True, 100.0),
        (113, False, None),
        (9999, False, None),
        (-9999, False, None),
        (-1, False, None),
        (101, False, None),
        (9, True, None),
        ("", False, None),
        (None, False, None),
    ],
)
def test_normalize_cloud_pct(
    raw: int | float | str | None, octas: bool, expected: float | None
) -> None:
    assert normalize_cloud_pct(raw, octas=octas) == expected

import pytest

from cloudy.core.geo import haversine_km, initial_bearing_deg


def test_haversine_known_distance() -> None:
    # Stockholm centralstation → Uppsala centralstation ≈ 63.5 km
    d = haversine_km(59.3303, 18.0561, 59.8586, 17.6464)
    assert 62 < d < 65


def test_haversine_zero() -> None:
    assert haversine_km(59.33, 18.06, 59.33, 18.06) == 0.0


def test_initial_bearing_cardinals() -> None:
    # Due north and due east from a point, with the 0-360° clockwise-from-north convention.
    assert initial_bearing_deg(59.0, 18.0, 60.0, 18.0) == 0.0  # straight north
    assert initial_bearing_deg(59.0, 18.0, 59.0, 19.0) == pytest.approx(90.0, abs=0.5)  # east
    assert initial_bearing_deg(59.0, 18.0, 58.0, 18.0) == pytest.approx(180.0)  # south

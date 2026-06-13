from cloudy.core.geo import haversine_km


def test_haversine_known_distance() -> None:
    # Stockholm centralstation → Uppsala centralstation ≈ 63.5 km
    d = haversine_km(59.3303, 18.0561, 59.8586, 17.6464)
    assert 62 < d < 65


def test_haversine_zero() -> None:
    assert haversine_km(59.33, 18.06, 59.33, 18.06) == 0.0

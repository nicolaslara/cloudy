from math import asin, atan2, cos, degrees, radians, sin, sqrt

# The same radius the SQL haversine uses; re-exported from series_sql so the
# Python and SQL distance implementations can never drift apart.
from cloudy.core.series_sql import EARTH_RADIUS_KM


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance. Error (<0.5%) is below SMHI's own position uncertainty."""
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compass bearing (0-360°, N=0, clockwise) from point 1 toward point 2.

    Distance alone can't tell an *upwind* neighbour from a *downwind* one, so the
    spatial benchmark's features carry direction too: which way a neighbour's cloud has
    to travel to reach the point. Standard forward-azimuth formula.
    """
    phi1, phi2 = radians(lat1), radians(lat2)
    dlon = radians(lon2 - lon1)
    x = sin(dlon) * cos(phi2)
    y = cos(phi1) * sin(phi2) - sin(phi1) * cos(phi2) * cos(dlon)
    return (degrees(atan2(x, y)) + 360.0) % 360.0

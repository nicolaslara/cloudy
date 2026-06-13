"""Unit and sentinel normalization — the only place raw SMHI values become cloud %."""

from __future__ import annotations

# metobs param 16 ships percent (0-100). MESAN/SNOW use octas (0-8); convert at ingest.
# 113 is SMHI's "sky obscured / not observable" code — sky is hidden (fog, etc.),
# which is genuinely unknown cloud cover, not 100%. 9999/-9999 are generic
# no-data fills. All three must read as missing so they never inflate a mean or
# look like real overcast.
MISSING_SENTINELS = frozenset({113, 9999, -9999})


def normalize_cloud_pct(raw: int | float | str | None, *, octas: bool = False) -> float | None:
    """Return cloud cover 0-100, or None for missing / not observable.

    octas=True for sources that encode total cloud as okta steps (MESAN, SNOW).
    """
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    # Negatives are always nonsense for cloud cover, regardless of source.
    if value in MISSING_SENTINELS or value < 0:
        return None
    if octas:
        # Out-of-range octas (>8) are corrupt, not "extra cloudy" — drop them
        # rather than letting them map past 100%.
        if value > 8:
            return None
        return value / 8.0 * 100.0
    # Percent sources >100 are likewise bad data, not a saturated sky.
    if value > 100:
        return None
    return value

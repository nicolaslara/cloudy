"""Unit and sentinel normalization — the only place raw SMHI values become cloud %."""

from __future__ import annotations

# metobs param 16 ships percent (0-100). MESAN/SNOW use octas (0-8); convert at ingest.
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
    if value in MISSING_SENTINELS or value < 0:
        return None
    if octas:
        if value > 8:
            return None
        return value / 8.0 * 100.0
    if value > 100:
        return None
    return value

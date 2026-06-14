"""Damped anomaly persistence: how much of a recent anomaly to carry forward.

`fit_alpha` is the whole model in one number per lead: the lag-k autocorrelation
of the anomaly series, clamped to [0, 1]. The outlook then nudges a slot's normal
by `alpha * recent_anomaly`.

Two clamps carry the honesty. alpha is floored at 0 so a noisy negative
autocorrelation can't invert the signal (forecast a dry spell from a wet one); it
is capped at 1 so we never amplify an anomaly beyond its observed size. The floor
is load-bearing: at alpha=0 the forecast *is* the normal, which is why the model
can't do worse than the baseline on average — it only leans on a recent surprise
when the history says such surprises persist.
"""

from __future__ import annotations

from collections.abc import Sequence
from statistics import fmean


def fit_alpha(anomalies: Sequence[float | None], lead: int) -> float:
    """Lag-`lead` anomaly autocorrelation coefficient, clamped to [0, 1].

    cov(a_t, a_{t+lead}) / var(a_t) over the chronological anomaly series — the
    least-squares slope of a_{t+lead} on a_t, i.e. "how much of an anomaly persists
    `lead` steps out". The series lives on a complete weekly calendar grid where a
    missing week is `None`, so the index gap *is* the calendar gap: we count only
    lag-`lead` pairs where both ends are present (a real `lead`-week step, never one
    that jumps a hole), and take the variance over the present values. Too short a
    series, no valid pairs, or a degenerate flat one with no variance yields alpha=0
    — fall back to the normal rather than divide by ~zero and invent persistence.
    """
    if lead <= 0:
        raise ValueError("lead must be a positive number of steps ahead")
    present = [a for a in anomalies if a is not None]
    if len(present) <= lead:
        return 0.0
    mean = fmean(present)
    var = sum((a - mean) ** 2 for a in present) / len(present)
    if var == 0:
        return 0.0
    pairs: list[tuple[float, float]] = []
    for t in range(len(anomalies) - lead):
        a, b = anomalies[t], anomalies[t + lead]
        if a is not None and b is not None:
            pairs.append((a, b))
    if not pairs:
        return 0.0
    cov = sum((a - mean) * (b - mean) for a, b in pairs) / len(pairs)
    return max(0.0, min(1.0, cov / var))

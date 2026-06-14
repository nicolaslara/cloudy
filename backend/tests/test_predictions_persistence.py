"""Unit truths for fit_alpha, the one number the damped-persistence model rests on.

Pure-Python, no database: a genuinely persistent series fits a positive clamped
alpha; an anti-persistent or degenerate one floors to 0 (fall back to the normal).
"""

from cloudy.predictions import persistence


def test_alpha_is_clamped_into_unit_interval() -> None:
    # A strongly persistent series has high lag-1 autocorrelation, clamped to [0,1].
    persistent = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    alpha = persistence.fit_alpha(persistent, lead=1)
    assert 0.0 <= alpha <= 1.0
    assert alpha > 0.5

    # Alternating-sign anomalies have negative lag-1 autocorrelation -> floored to 0.
    alternating = [1.0, -1.0, 1.0, -1.0, 1.0, -1.0]
    assert persistence.fit_alpha(alternating, lead=1) == 0.0


def test_alpha_zero_on_degenerate_or_short_series() -> None:
    assert persistence.fit_alpha([], lead=1) == 0.0
    assert persistence.fit_alpha([5.0, 5.0, 5.0], lead=1) == 0.0  # no variance
    assert persistence.fit_alpha([1.0, 2.0], lead=3) == 0.0  # shorter than the lead

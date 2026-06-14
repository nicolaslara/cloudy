"""Unit tests for the weekly near-term outlook's skill logic.

The DB-backed series is exercised through the API test; here we pin the part that
matters most — that the causal rolling-origin backtest credits genuine persistence
and doesn't credit noise — without needing two years of seeded weekly rows. The
backtest now takes the *raw* `(week_of_year, value)` series and rebuilds the normal
causally per origin, so the synthetic series carries a week-of-year too.
"""

from __future__ import annotations

import math

from cloudy.predictions.outlook import MIN_TRAIN_WEEKS, backtest_skill


def _ar1(phi: float, n: int) -> list[tuple[int, float]]:
    """A deterministic AR(1) series as `(week_of_year, value)`.

    No RNG (forbidden, and we want determinism): the wobble is a fixed sinusoid,
    which keeps the series stationary while leaving real lag-1 persistence for the
    model to find when phi is high. Weeks-of-year cycle 1..52; the value carries no
    seasonal mean, so the causal climatology subtracts ~0 and the persistence in the
    residual is what the backtest must reward.
    """
    out = [0.0]
    for t in range(1, n):
        out.append(phi * out[-1] + math.sin(t))
    return [((i % 52) + 1, v) for i, v in enumerate(out)]


def test_backtest_rewards_real_persistence() -> None:
    # Strong persistence: damped-persistence should beat the "predict normal" baseline.
    skill, n = backtest_skill(_ar1(0.8, MIN_TRAIN_WEEKS + 200), lead=1)
    assert n > 0
    assert skill > 0.1


def test_backtest_does_not_reward_a_flat_series() -> None:
    # A constant series -> no anomalies to persist; skill collapses to zero, not a
    # spurious positive (model and baseline both predict ~0).
    flat = [((i % 52) + 1, 50.0) for i in range(MIN_TRAIN_WEEKS + 50)]
    skill, n = backtest_skill(flat, lead=1)
    assert n > 0
    assert skill == 0.0


def test_backtest_too_short_returns_zero() -> None:
    # Below the warm-up there are no scorable origins; report (0, 0) honestly.
    assert backtest_skill([(1, 1.0), (2, -1.0), (3, 1.0)], lead=1) == (0.0, 0)


def test_backtest_handles_a_calendar_gap() -> None:
    # A missing week is an explicit None on the grid; the backtest must skip lags
    # that touch the hole (never treat the rows either side as 1 week apart) and
    # still score the rest rather than crashing or crediting a phantom step.
    series: list[tuple[int, float | None]] = list(_ar1(0.8, MIN_TRAIN_WEEKS + 200))
    series[150] = (series[150][0], None)  # punch a hole mid-series
    skill, n = backtest_skill(series, lead=1)
    assert n > 0
    assert skill > 0.1  # the gap costs a few origins, not the signal

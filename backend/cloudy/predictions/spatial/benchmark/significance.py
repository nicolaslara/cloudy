"""Per-station paired significance: is a method really better than the shipped kNN?

A lower *median* MAE can hide a per-station tie — a better median with a heavier tail
wins only half the head-to-head matchups. So we compare estimators the honest way:
pair each station's MAE under the two estimators, and report the median paired delta,
the share of stations where the method wins, and a bootstrap 95% CI on that median. A
CI that straddles zero is a tie, however the medians look. Pure stdlib (seeded
bootstrap), so the verdict is deterministic and testable.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from statistics import fmean, median


@dataclass(frozen=True)
class Comparison:
    """One method's paired comparison against a reference estimator (e.g. the shipped kNN)."""

    n_stations: int
    median_delta: float  # method MAE - reference MAE; < 0 means the method is better
    mean_delta: float
    win_pct: float  # share of stations where the method beats the reference
    ci_low: float  # 2.5th percentile of the bootstrap median delta
    ci_high: float  # 97.5th percentile

    @property
    def significant(self) -> bool:
        """A gap whose 95% CI excludes zero. Otherwise the two estimators tie."""
        return self.ci_low > 0.0 or self.ci_high < 0.0


def compare(
    method: dict[int, float],
    reference: dict[int, float],
    *,
    seed: int = 42,
    iterations: int = 10_000,
) -> Comparison:
    """Pair two per-station MAE maps and bootstrap a 95% CI on the median delta."""
    stations = sorted(set(method) & set(reference))
    deltas = [method[s] - reference[s] for s in stations]
    if not deltas:
        return Comparison(0, 0.0, 0.0, 0.0, 0.0, 0.0)
    rng = random.Random(seed)
    n = len(deltas)
    boots = sorted(median(deltas[rng.randrange(n)] for _ in range(n)) for _ in range(iterations))
    return Comparison(
        n_stations=n,
        median_delta=median(deltas),
        mean_delta=fmean(deltas),
        win_pct=100.0 * sum(1 for d in deltas if d < 0) / n,
        ci_low=boots[int(iterations * 0.025)],
        ci_high=boots[int(iterations * 0.975)],
    )

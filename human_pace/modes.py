"""1-D k-means: split message gaps into fast / mid / slow clusters.

Why clustering instead of percentiles
-------------------------------------
Typing gaps are not one distribution. Measured over 200 real messages, the
histogram had three peaks - roughly 0-4s (streaming short fragments), 4-8s
(normal), 10-26s (thinking, or doing something else). Asking for "the P75
gap" of a three-peaked distribution gives a number that describes nobody.

What actually matters is *which mode the user is in right now*, and the only
evidence for that is the most recent gap. So: cluster, then look at where the
latest gap landed.

A hand-written 1-D k-means is ~25 lines and needs no dependencies, which
matters more than theoretical purity for k=3 and n=20.
"""

from __future__ import annotations

import statistics


def kmeans1d(values: list[float], k: int = 3, iters: int = 25):
    """Cluster 1-D values into ``k`` groups.

    Returns ``(centers, groups)`` where ``groups[i]`` holds the values nearest
    to ``centers[i]``. Cluster order follows initial center order, i.e. sorted
    from small to large.

    Degenerate input is handled by collapsing to a single cluster: if the
    spread is under 0.5s there is nothing to separate, and if there are fewer
    points than clusters we cannot do better than one group.

    Medians are used for the update step rather than means so that a single
    outlier (he walked away for 20 seconds) cannot drag a center.
    """
    if not values:
        return [], []

    lo, hi = min(values), max(values)
    if hi - lo < 0.5 or len(values) < k:
        return [statistics.median(values)], [list(values)]

    centers = [lo + (hi - lo) * i / (k - 1) for i in range(k)]
    groups: list[list[float]] = [[] for _ in range(k)]

    for _ in range(iters):
        groups = [[] for _ in range(k)]
        for v in values:
            j = nearest(centers, v)
            groups[j].append(v)
        new_centers = [
            statistics.median(g) if g else centers[i] for i, g in enumerate(groups)
        ]
        if new_centers == centers:
            break
        centers = new_centers

    return centers, groups


def nearest(centers: list[float], value: float) -> int:
    """Index of the center closest to ``value``."""
    return min(range(len(centers)), key=lambda i: abs(value - centers[i]))


def percentile(values: list[float], p: float) -> float:
    """Linear-interpolated percentile, matching numpy's default convention."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return float(s[lo] + (s[hi] - s[lo]) * (k - lo))

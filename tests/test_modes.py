"""1-D k-means and percentile helpers."""

import pytest

from human_pace.modes import kmeans1d, nearest, percentile


def test_percentile_matches_numpy_convention():
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([5], 90) == 5.0
    assert percentile([], 50) == 0.0


def test_nearest_picks_closest_center():
    assert nearest([1.0, 5.0, 9.0], 4.4) == 1
    assert nearest([1.0, 5.0, 9.0], 0.1) == 0
    assert nearest([1.0, 5.0, 9.0], 100.0) == 2


def test_kmeans_separates_three_modes():
    values = [1.0, 1.5, 2.0, 5.0, 5.5, 6.0, 12.0, 13.0, 14.0]
    centers, groups = kmeans1d(values, k=3)
    assert len(centers) == 3
    assert centers == sorted(centers)
    # Every value lands in exactly one group.
    assert sum(len(g) for g in groups) == len(values)


def test_kmeans_collapses_when_spread_is_tiny():
    centers, groups = kmeans1d([5.0, 5.1, 5.2], k=3)
    assert len(centers) == 1
    assert len(groups[0]) == 3


def test_kmeans_handles_too_few_points():
    centers, groups = kmeans1d([3.0, 9.0], k=3)
    assert len(centers) == 1


def test_kmeans_handles_empty():
    assert kmeans1d([], k=3) == ([], [])

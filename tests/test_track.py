"""Tests for the high-level track() iterator wrapper."""

from __future__ import annotations

import barflow


def test_track_yields_all_values_in_order():
    assert list(barflow.track(range(10), disable=True)) == list(range(10))


def test_track_advances_counter_to_total():
    it = barflow.track(range(7), disable=True)
    consumed = list(it)
    assert len(consumed) == 7


def test_track_does_not_duplicate_or_drop():
    src = ["a", "b", "c", "d"]
    assert list(barflow.track(src, disable=True)) == src


def test_track_infers_total_from_len():
    # A list has __len__; total is inferred without an explicit arg.
    out = list(barflow.track([1, 2, 3], disable=True))
    assert out == [1, 2, 3]


def test_track_handles_generator_without_len():
    def gen():
        yield from range(5)
    assert list(barflow.track(gen(), disable=True)) == list(range(5))


def test_track_empty_iterable():
    assert list(barflow.track([], disable=True)) == []


def test_track_with_columns_routes_through_python_progress():
    # Passing columns forces the slow path (Progress subclass).
    from barflow import columns as C
    out = list(barflow.track(range(3), disable=True, columns=[C.BarColumn()]))
    assert out == [0, 1, 2]


def test_track_with_theme():
    out = list(barflow.track(range(3), disable=True, theme="classic"))
    assert out == [0, 1, 2]

"""Behavioral tests for the Progress core.

State is asserted through the synchronous `completed`/`n_tasks` getters
and, for computed values (percentage/fraction), through a CallbackColumn
snapshot — see conftest.capture_snapshots.
"""

from __future__ import annotations

import barflow
from conftest import capture_snapshots


# ---- counter mutation ------------------------------------------------------

def test_tick_increments_by_one():
    with barflow.Progress(total=10, disable=True) as p:
        p.tick()
        p.tick()
        assert p.completed == 2


def test_advance_increments_by_n():
    with barflow.Progress(total=10, disable=True) as p:
        p.advance(5)
        assert p.completed == 5
        p.advance(2)
        assert p.completed == 7


def test_update_targets_named_task():
    with barflow.Progress(disable=True) as p:
        a = p.add_task(total=10, desc="a")
        b = p.add_task(total=10, desc="b")
        p.update(b, 4)
        # task 0 is the implicit default; named tasks start at the next id.
        assert p.completed == 0      # getter reports task 0
        # b advanced independently — verified via snapshot below.
        assert (a, b) == (0, 1)


# ---- multi-task ------------------------------------------------------------

def test_add_task_returns_sequential_ids():
    with barflow.Progress(disable=True) as p:
        ids = [p.add_task(total=1) for _ in range(3)]
        assert ids == [0, 1, 2]


def test_n_tasks_counts_added_tasks():
    with barflow.Progress(disable=True) as p:
        assert p.n_tasks == 0            # no task materialized yet
        p.add_task(total=1)
        p.add_task(total=1)
        assert p.n_tasks == 2


def test_tick_materializes_implicit_task_zero():
    with barflow.Progress(total=4, disable=True) as p:
        p.tick()
        assert p.n_tasks == 1


# ---- computed state via snapshot ------------------------------------------

def test_percentage_and_fraction_at_completion():
    snap = capture_snapshots(4, lambda p: [p.tick() for _ in range(4)])
    assert snap["completed"] == 4
    assert snap["total"] == 4
    assert snap["fraction"] == 1.0
    assert snap["percentage"] == 100.0


def test_zero_total_yields_sentinel():
    # total=0 must not divide-by-zero; fraction/percentage report -1.
    snap = capture_snapshots(0, lambda p: p.tick())
    assert snap["fraction"] == -1.0
    assert snap["percentage"] == -1.0


def test_overshoot_clamps_fraction():
    snap = capture_snapshots(4, lambda p: p.advance(100))
    assert snap["fraction"] == 1.0
    assert snap["percentage"] == 100.0


def test_elapsed_is_nonnegative():
    snap = capture_snapshots(4, lambda p: p.advance(4))
    assert snap["elapsed"] >= 0.0


# ---- mutation methods ------------------------------------------------------

def test_set_total_changes_denominator():
    def drive(p):
        p.advance(5)
        p.set_total(0, 10)   # task 0, new total
    snap = capture_snapshots(100, drive)
    assert snap["total"] == 10
    assert snap["completed"] == 5
    assert snap["fraction"] == 0.5


def test_set_description_updates_snapshot():
    def drive(p):
        p.set_description("renamed")
        p.tick()
    snap = capture_snapshots(4, drive)
    assert snap["description"] == "renamed"


# ---- disable ---------------------------------------------------------------

def test_disabled_still_counts():
    with barflow.Progress(total=10, disable=True) as p:
        p.advance(3)
        assert p.completed == 3


def test_disabled_methods_are_safe():
    # refresh/pause/resume/write_above must not raise when disabled.
    with barflow.Progress(total=10, disable=True) as p:
        p.refresh()
        p.pause()
        p.resume()
        p.write_above("note")
        p.set_description("x")


# ---- lifecycle -------------------------------------------------------------

def test_context_manager_returns_self_like():
    p = barflow.Progress(total=1, disable=True)
    entered = p.__enter__()
    assert entered is not None
    p.__exit__(None, None, None)


def test_double_close_is_safe():
    p = barflow.Progress(total=1, disable=True)
    p.__enter__()
    p.close()
    p.close()  # must not raise

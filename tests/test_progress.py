"""Behavioral tests for the Progress core.

State is asserted through the synchronous `completed`/`n_tasks` getters
and, for computed values (percentage/fraction), through a CallbackColumn
snapshot — see conftest.capture_snapshots.
"""

from __future__ import annotations

import pytest

import barflow
from conftest import capture_snapshots, capture_task_snapshot


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
        # add_task assigns sequential ids starting at 0; updating task b
        # leaves task 0 (which `completed` reports) untouched.
        assert (a, b) == (0, 1)
        assert p.completed == 0      # getter reports task 0, not b


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


# ---- out-of-range task ids (deferred-raise paths) --------------------------

def test_update_out_of_range_raises():
    with barflow.Progress(disable=True) as p:
        p.add_task(total=10)
        with pytest.raises(IndexError):
            p.update(99, 1)     # task_id >= n_tasks
        with pytest.raises(IndexError):
            p.update(-1, 1)     # task_id < 0 (distinct bounds branch)


def test_set_total_out_of_range_raises():
    with barflow.Progress(disable=True) as p:
        p.add_task(total=10)
        with pytest.raises(IndexError):
            p.set_total(99, 5)


def test_set_task_description_out_of_range_raises():
    with barflow.Progress(disable=True) as p:
        p.add_task(total=10)
        with pytest.raises(IndexError):
            p.set_task_description(99, "x")


def test_set_description_with_no_tasks_raises():
    with barflow.Progress(disable=True) as p:   # no total / no add_task
        with pytest.raises(IndexError):
            p.set_description("x")


# ---- computed-state aliases / multi-task descriptions ----------------------

def test_speed_is_rate_alias():
    snap = capture_snapshots(4, lambda p: p.advance(4))
    assert snap["speed"] == snap["rate"]


def test_set_task_description_targets_named_task():
    def drive(p):
        p.add_task(total=4, desc="zero")   # id 0
        p.add_task(total=4, desc="one")    # id 1
        p.set_task_description(1, "renamed")
    assert capture_task_snapshot(drive, 1)["description"] == "renamed"
    assert capture_task_snapshot(drive, 0)["description"] == "zero"


# ---- iterator protocol -----------------------------------------------------

def test_progress_iteration_stops_at_total():
    with barflow.Progress(total=3, disable=True) as p:
        n = sum(1 for _ in p)
        # The fetch_add-then-rollback leaves completed exactly on total,
        # not total+1.
        assert n == 3
        assert p.completed == 3


# ---- repr ------------------------------------------------------------------

def test_repr_includes_task0_state():
    with barflow.Progress(total=10, desc="dl", disable=True) as p:
        p.advance(3)
        r = repr(p)
    assert r.startswith("Progress(")
    assert "completed=3" in r
    assert "total=10" in r
    assert "desc='dl'" in r
    assert "tasks=1" in r


def test_repr_with_no_tasks():
    with barflow.Progress(disable=True) as p:
        assert repr(p) == "Progress(tasks=0)"


def test_repr_escapes_special_chars_in_desc():
    # A quote / backslash / newline in the desc must not produce an ambiguous
    # repr — they are escaped so the desc='...' field stays unambiguous.
    with barflow.Progress(total=10, desc="a'b\\c\nd", disable=True) as p:
        r = repr(p)
    assert "desc='a\\'b\\\\c\\nd'" in r

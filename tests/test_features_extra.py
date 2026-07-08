"""Tests for the reusability / reporting / humanization additions:

  * ``reset(task_id, total)`` — restart a task's counter, timers, and
    completion/EMA state so a bar can be reused across phases.
  * ``set_postfix(**fields)`` / ``set_postfix_str`` + ``PostfixColumn`` — a
    tqdm-style trailing annotation that the default column set carries
    invisibly until something is set.
  * ``unit`` / ``unit_scale`` / ``unit_divisor`` — SI/binary humanization of
    the count and rate columns (byte-transfer bars).
  * ``smoothing`` — EMA-smoothed instantaneous rate.
  * ``leave`` — clear the bar on close instead of leaving the final frame.
  * ``Progress.total`` / ``Progress.elapsed`` getters.
  * ``Tracker.__length_hint__`` so ``list(track(...))`` can preallocate.

Deterministic assertions go through ``render_line()`` (the exact live column
pipeline into a string, no console side effects); rate/elapsed, which depend
on wall time, are asserted structurally (suffix / non-negativity) only.
"""

from __future__ import annotations

import operator

import pytest

import barflow
from barflow import columns as C
from barflow._core import COL_POSTFIX


# ---- reset -----------------------------------------------------------------

def test_reset_clears_counter_and_completion():
    with barflow.Progress(total=10, disable=True) as p:
        p.advance(7)
        assert p.completed == 7
        p.reset()
        assert p.completed == 0
        assert p.total == 10          # total preserved when not overridden


def test_reset_installs_new_total():
    with barflow.Progress(total=10, disable=True) as p:
        p.advance(10)
        p.reset(total=50)
        assert p.completed == 0
        assert p.total == 50


def test_reset_out_of_range_raises():
    with barflow.Progress(total=10, disable=True) as p:
        with pytest.raises(IndexError):
            p.reset(5)


def test_reset_rerenders_from_zero():
    # A finished bar shows "10/10"; after reset it must render "0/10" again.
    with barflow.Progress(C.CountColumn(), total=10, disable=True) as p:
        p.advance(10)
        assert p.render_line() == "10/10"
        p.reset()
        assert p.render_line() == "0/10"


# ---- postfix ---------------------------------------------------------------

def test_postfix_column_wire_shape():
    col = C.PostfixColumn()
    assert col[0] == COL_POSTFIX
    assert len(col) == 5


def test_postfix_column_renders_with_leading_space():
    with barflow.Progress(C.DescriptionColumn(), C.PostfixColumn(),
                          total=5, desc="x", disable=True) as p:
        assert p.render_line() == "x"          # empty until set
        p.set_postfix_str(0, "k=1")
        assert p.render_line() == "x k=1"       # self-prefixed single space


def test_set_postfix_formats_floats():
    with barflow.Progress(total=10, desc="job", disable=True) as p:
        p.advance(3)
        base = p.render_line()
        assert "loss" not in base               # invisible until set
        p.set_postfix(loss=0.03125, acc=0.5)
        line = p.render_line()
        assert line.endswith("loss=0.0312, acc=0.5"), line


def test_set_postfix_targets_named_task():
    with barflow.Progress(C.DescriptionColumn(), C.PostfixColumn(),
                          disable=True) as p:
        t1 = p.add_task(total=5, desc="a")
        t2 = p.add_task(total=5, desc="b")
        p.set_postfix(t2, phase="warmup")
        assert p.render_line(t1) == "a"
        assert p.render_line(t2) == "b phase=warmup"


def test_default_columns_carry_postfix():
    # The default set ends with an (empty) postfix column, so set_postfix
    # works with no custom layout.
    with barflow.Progress(total=10, desc="dl", disable=True) as p:
        p.advance(5)
        p.set_postfix(eta="soon")
        assert p.render_line().endswith("eta=soon")


# ---- unit humanization -----------------------------------------------------

def test_unit_scale_count_is_humanized():
    with barflow.Progress(C.CountColumn(), total=4_100_000, unit="B",
                          unit_scale=True, unit_divisor=1000, disable=True) as p:
        p.advance(1_500_000)
        assert p.render_line() == "1.50M/4.10M"


def test_unit_scale_count_binary_divisor():
    with barflow.Progress(C.CountColumn(), total=2 * 1024 * 1024,
                          unit_scale=True, unit_divisor=1024, disable=True) as p:
        p.advance(1024 * 1024)
        assert p.render_line() == "1.00M/2.00M"


def test_unit_scale_off_shows_raw_count():
    with barflow.Progress(C.CountColumn(), total=1_500_000, disable=True) as p:
        p.advance(1_500_000)
        assert p.render_line() == "1500000/1500000"


def test_rate_unit_word():
    with barflow.Progress(C.RateColumn(), total=100, unit="B", disable=True) as p:
        p.advance(10)
        assert p.render_line().endswith(" B/s")


def test_rate_default_unit_is_it():
    with barflow.Progress(C.RateColumn(), total=100, disable=True) as p:
        p.advance(10)
        assert p.render_line().endswith(" it/s")


# ---- total / elapsed getters ----------------------------------------------

def test_total_getter():
    with barflow.Progress(total=42, disable=True) as p:
        assert p.total == 42


def test_total_none_when_unbounded():
    with barflow.Progress(disable=True) as p:           # no task
        assert p.total is None
    with barflow.Progress(total=0, disable=True) as p:  # indeterminate
        assert p.total is None


def test_elapsed_is_non_negative_float():
    with barflow.Progress(total=10, disable=True) as p:
        p.advance(5)
        e = p.elapsed
        assert isinstance(e, float) and e >= 0.0


# ---- length hint -----------------------------------------------------------

def test_length_hint_reports_remaining():
    t = barflow.track(range(1000), disable=True)
    assert operator.length_hint(t) == 1000
    next(t)
    assert operator.length_hint(t) == 999
    list(t)  # exhaust so the wrapped progress closes


def test_length_hint_zero_when_unbounded():
    def gen():
        yield from range(3)
    t = barflow.track(gen(), disable=True)   # no __len__ -> total 0
    assert operator.length_hint(t) == 0
    list(t)


def test_list_track_preallocates():
    # list() consults __length_hint__; result must still be correct.
    assert barflow.track(range(50), disable=True).__length_hint__() == 50
    assert list(barflow.track(range(50), disable=True)) == list(range(50))


# ---- smoothing -------------------------------------------------------------

def test_smoothing_path_runs_and_reports_rate():
    # render_line reports the average (side-effect free), but a live frame's
    # compute_rate must exercise the EMA branch without error and yield a
    # finite, non-negative rate. Drive it via refresh() on a disabled bar
    # (refresh calls render_frame -> compute_rate) and read through a callback.
    import time
    seen = []
    with barflow.Progress(C.CallbackColumn(lambda t: seen.append(t.rate) or ""),
                          total=1000, smoothing=0.5, disable=True) as p:
        for _ in range(4):
            p.advance(100)
            time.sleep(0.003)
            p.refresh()
    assert seen and all(r >= 0.0 for r in seen)
    assert any(r > 0.0 for r in seen)


@pytest.mark.parametrize("s", [-1.0, 0.0, 0.3, 1.0, 5.0])
def test_smoothing_values_accepted(s):
    # Out-of-range smoothing is clamped in the core, not rejected.
    with barflow.Progress(total=10, smoothing=s, disable=True) as p:
        p.advance(10)
        assert p.render_line()  # renders without error


# ---- leave / min_interval guard -------------------------------------------

def test_leave_false_constructs_and_closes():
    # Non-tty stderr in tests => no erase escapes, but the close path must run
    # cleanly for both leave states.
    p = barflow.Progress(total=10, leave=False, min_interval=0.01)
    p.__enter__()
    p.advance(10)
    p.close()


def test_min_interval_zero_is_floored():
    # A non-positive interval must not pin the render thread; construct, run a
    # live bar briefly, and tear down without hanging.
    p = barflow.Progress(total=5, min_interval=0.0)
    p.__enter__()
    p.advance(5)
    p.close()

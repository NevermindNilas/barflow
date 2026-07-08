"""Tests for the second feature batch (competitor-parity additions):

  * ``initial=`` — resume a partially-done job: the count starts seeded, but
    rate/eta measure only the work done in this run.
  * ``set_visible(task_id, bool)`` — hide/show a task's row (it keeps counting).
  * ``delay=`` — suppress the bar until N seconds elapse, so a fast job never
    flashes one.
  * ``disable=None`` — tqdm-style auto-disable when stderr is not a TTY.

The bar writes to the OS stderr handle directly (not ``sys.stderr``), so
live-output assertions capture at the file-descriptor level via
``_capture_fd2``; deterministic state goes through ``render_line`` / getters.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

import pytest

import barflow
from barflow import columns as C


def _capture_fd2(fn):
    """Run fn() with OS fd 2 redirected to a temp file; return what was
    written. Needed because the C core writes frames straight to the stderr
    handle, which a Python-level sys.stderr swap cannot intercept."""
    buf = tempfile.TemporaryFile()
    saved = os.dup(2)
    os.dup2(buf.fileno(), 2)
    try:
        fn()
    finally:
        os.dup2(saved, 2)
        os.close(saved)
    buf.seek(0)
    return buf.read()


# ---- initial= --------------------------------------------------------------

def test_initial_seeds_count():
    with barflow.Progress(C.CountColumn(), total=100, initial=30,
                          disable=True) as p:
        assert p.completed == 30
        assert p.render_line() == "30/100"
        p.advance(20)
        assert p.completed == 50
        assert p.render_line() == "50/100"


def test_initial_excluded_from_rate():
    # done == completed - initial. At entry completed == initial, so done == 0
    # and the rate is exactly 0 regardless of elapsed time — a deterministic
    # proof that the seed is not counted as throughput.
    with barflow.Progress(C.RateColumn(), total=100, initial=50,
                          disable=True) as p:
        time.sleep(0.005)
        assert p.render_line().endswith("0.0 it/s")
        p.advance(10)                       # now done == 10
        assert not p.render_line().endswith("0.0 it/s")


def test_initial_clamped_to_total():
    with barflow.Progress(total=10, initial=999, disable=True) as p:
        assert p.completed == 10


def test_initial_negative_rejected():
    # Signed parse (L) rejects negatives instead of mask-wrapping to ~1.8e19.
    with pytest.raises(ValueError):
        barflow.Progress(total=10, initial=-1, disable=True)


def test_reset_clears_initial():
    with barflow.Progress(C.CountColumn(), total=100, initial=30,
                          disable=True) as p:
        p.reset()
        assert p.completed == 0
        assert p.render_line() == "0/100"


def test_reset_repaints_live_spinnerless_bar():
    # reset() zeroes completed AND last_snapshot, defeating the render loop's
    # dirty check; force_render must drive a repaint so a spinner-less layout
    # doesn't linger on the stale "10/10" frame. Observe via fd capture.
    def run():
        p = barflow.Progress(C.CountColumn(), total=10, min_interval=0.01)
        p.__enter__()
        p.advance(10)
        time.sleep(0.04)     # paint 10/10
        p.reset()
        time.sleep(0.04)     # must repaint 0/10 without any advance
        p.close()

    out = _capture_fd2(run)
    assert b"10/10" in out and b"0/10" in out


def test_track_initial_passthrough():
    it = barflow.track(range(10), total=10, initial=3, disable=True)
    assert it.progress.completed == 3 if hasattr(it, "progress") else True
    # length_hint reflects remaining against the seeded counter.
    import operator
    assert operator.length_hint(it) == 7
    list(it)


# ---- set_visible -----------------------------------------------------------

def test_set_visible_keeps_counting():
    with barflow.Progress(C.CountColumn(), disable=True) as p:
        t = p.add_task(total=10, desc="a")
        p.set_visible(t, False)
        p.update(t, 4)                      # hidden, still counts
        assert p.render_line(t) == "4/10"
        p.set_visible(t, True)


def test_set_visible_out_of_range_raises():
    with barflow.Progress(disable=True) as p:
        p.add_task(total=10)
        with pytest.raises(IndexError):
            p.set_visible(9, True)


def test_set_visible_hides_row_in_output():
    # A task hidden for the bar's whole life must never appear in the frames.
    def run():
        p = barflow.Progress(C.DescriptionColumn(), min_interval=0.01)
        p.__enter__()
        a = p.add_task(total=100, desc="ALPHA")
        b = p.add_task(total=100, desc="BETABETA")
        p.set_visible(b, False)
        for _ in range(6):
            p.update(a, 10)
            p.update(b, 10)
            time.sleep(0.012)
        p.close()

    out = _capture_fd2(run)
    assert b"ALPHA" in out            # visible task rendered
    assert b"BETABETA" not in out     # hidden task never rendered


# ---- delay= ----------------------------------------------------------------

def test_delay_suppresses_fast_job():
    def run():
        p = barflow.Progress(total=100, delay=1.0, min_interval=0.01)
        p.__enter__()
        p.advance(100)
        time.sleep(0.08)
        p.close()

    assert _capture_fd2(run) == b""      # never crossed the delay window


def test_delay_shows_slow_job():
    def run():
        p = barflow.Progress(total=100, delay=0.03, min_interval=0.01)
        p.__enter__()
        for _ in range(15):
            p.advance(6)
            time.sleep(0.012)
        p.close()

    assert len(_capture_fd2(run)) > 0    # window elapsed, bar painted


# ---- disable=None auto -----------------------------------------------------

def test_auto_disable_logic(monkeypatch):
    class _TTY:
        def isatty(self):
            return True

    class _Pipe:
        def isatty(self):
            return False

    monkeypatch.setattr(sys, "stderr", _TTY())
    assert barflow._auto_disable() is False
    monkeypatch.setattr(sys, "stderr", _Pipe())
    assert barflow._auto_disable() is True
    monkeypatch.setattr(sys, "stderr", None)
    assert barflow._auto_disable() is True


def test_disable_none_constructs_everywhere():
    # None must be accepted and resolved (not passed through as a bool) on
    # every entry point.
    list(barflow.track(range(5), disable=None))
    with barflow.Progress(total=5, disable=None) as p:
        p.advance(5)
    with barflow.Progress(C.BarColumn(), total=5, disable=None) as p:  # slow path
        p.advance(5)

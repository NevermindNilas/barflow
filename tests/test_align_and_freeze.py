"""Tests for two multibar behaviors:

  * `align=True` right-pads every description to the widest one so the bar
    (and everything after it) starts at the same column on every task line —
    the rich Table.grid alignment, without a table.
  * A finished task freezes its elapsed/rate/eta at completion instead of
    letting the rate decay every frame while other tasks keep the render
    thread alive.

Both are observed through `render_line()`, which runs the exact column
pipeline a live frame would, into a returned string.
"""

from __future__ import annotations

import re
import time

import pytest

import barflow
from barflow import columns as C
from barflow._core import _display_width as dw

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def _plain(s: str) -> str:
    return ANSI.sub("", s)


def _bar_cell(line: str) -> int:
    """Display-cell column where the bar starts. Must be measured in cells,
    not code points — a CJK char is one code point but two cells."""
    return dw(_plain(line).split("|", 1)[0])


# ---- alignment -------------------------------------------------------------

NAMES = ["short", "a-much-longer-filename.iso", "mid.zip"]


def test_align_bars_share_start_column():
    p = barflow.Progress(C.DescriptionColumn(), " ", C.BarColumn(width=20),
                         " ", C.PercentColumn(), align=True)
    with p:
        ids = [p.add_task(total=100, desc=n) for n in NAMES]
        for t in ids:
            p.update(t, 50)
        starts = [_bar_cell(p.render_line(t)) for t in ids]
    assert len(set(starts)) == 1                      # all bars aligned
    widest = max(dw(n) for n in NAMES)
    assert starts[0] == widest + 1                    # widest desc + one space


def test_no_align_bars_are_ragged():
    p = barflow.Progress(C.DescriptionColumn(), " ", C.BarColumn(width=20),
                         align=False)
    with p:
        ids = [p.add_task(total=100, desc=n) for n in NAMES]
        for t in ids:
            p.update(t, 50)
        starts = [_bar_cell(p.render_line(t)) for t in ids]
    assert len(set(starts)) > 1                       # ragged, not aligned


def test_align_counts_wide_glyphs():
    # CJK is 2 cells/char; the pad must be measured in cells, not chars.
    names = ["下载.zip", "medium-name.iso"]
    p = barflow.Progress(C.DescriptionColumn(), " ", C.BarColumn(width=10),
                         align=True)
    with p:
        ids = [p.add_task(total=100, desc=n) for n in names]
        starts = [_bar_cell(p.render_line(t)) for t in ids]
    assert starts[0] == starts[1]
    assert starts[0] == max(dw(n) for n in names) + 1


def test_align_padding_grows_when_longer_task_added():
    p = barflow.Progress(C.DescriptionColumn(), " ", C.BarColumn(width=10),
                         align=True)
    with p:
        a = p.add_task(total=100, desc="a")
        before = _bar_cell(p.render_line(a))
        p.add_task(total=100, desc="a-very-long-later-arrival")
        after = _bar_cell(p.render_line(a))   # first task re-pads
    assert after > before


# ---- completion freeze -----------------------------------------------------

def _rate_and_elapsed(p, t):
    line = _plain(p.render_line(t))
    return line


def test_finished_task_freezes_rate_and_elapsed():
    p = barflow.Progress(C.RateColumn(), " ", C.ElapsedColumn())
    with p:
        t = p.add_task(total=100, desc="done")
        p.update(t, 100)                              # complete
        first = _rate_and_elapsed(p, t)
        time.sleep(0.25)
        second = _rate_and_elapsed(p, t)
    assert first == second                            # frozen, not decaying


def test_running_task_clock_still_moves():
    p = barflow.Progress(C.ElapsedColumn())
    with p:
        t = p.add_task(total=1_000_000, desc="run")
        p.update(t, 1)                                # nowhere near done
        first = _plain(p.render_line(t))
        time.sleep(1.1)
        second = _plain(p.render_line(t))
    assert first != second                            # still ticking


def test_reextend_past_completion_unfreezes():
    p = barflow.Progress(C.ElapsedColumn())
    with p:
        t = p.add_task(total=100, desc="x")
        p.update(t, 100)                              # complete -> frozen
        p.set_total(t, 1_000_000)                     # re-extend -> running
        first = _plain(p.render_line(t))
        time.sleep(1.1)
        second = _plain(p.render_line(t))
    assert first != second                            # clock resumed

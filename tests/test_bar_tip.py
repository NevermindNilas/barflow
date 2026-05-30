"""Tests for the animated bar tip (alive-progress-style leading-edge motion).

The tip is a list of single-cell frames the C core cycles at the bar's
boundary cell (the cell just past the filled run) by `frame_tick`, but only
while the bar is incomplete. Two halves are exercised:

  * plumbing — `BarColumn(tip=...)` wire shape, `bar_styles.tip_for`, and the
    built-in tips attached to glyph styles;
  * rendering — the boundary cell shows the right tip frame, advances with
    `frame_tick`, and vanishes at 100%.

`frame_tick` is driven deterministically: with `disable=True` no render
thread runs (so the tick is stable) yet `refresh()` still calls the C
`render_frame`, which bumps `frame_tick` and writes nothing (write is a
no-op while disabled). `render_line()` then renders at that exact tick.
"""

from __future__ import annotations

import barflow
from barflow import bar_styles
from barflow import columns as C
from barflow import spinners
from barflow._core import COL_BAR


# ---- tip_for ---------------------------------------------------------------

def test_tip_for_known_style_returns_frames():
    assert bar_styles.tip_for("blocks") == ["▒", "▓", "█", "▓"]


def test_tip_for_style_without_tip_is_empty():
    # smooth (the default) and ascii are intentionally tip-less.
    assert bar_styles.tip_for("smooth") == []
    assert bar_styles.tip_for("ascii") == []


def test_tip_for_unknown_name_is_empty_not_raising():
    assert bar_styles.tip_for("definitely-not-a-style") == []


def test_tip_for_dict_reads_tip_key():
    assert bar_styles.tip_for({"fill": "x", "tip": ["a", "b"]}) == ["a", "b"]
    assert bar_styles.tip_for({"fill": "x"}) == []


def test_tip_for_returns_fresh_copy():
    t = bar_styles.tip_for("blocks")
    t.append("ZZZ")
    assert "ZZZ" not in bar_styles.BAR_STYLES["blocks"]["tip"]


def test_to_tuple_still_five_with_tipped_style():
    # The glyph 5-tuple contract is unchanged — tip travels separately.
    assert len(bar_styles.to_tuple("blocks")) == 5


# ---- BarColumn wire shape --------------------------------------------------

def test_barcolumn_inherits_style_tip_as_seventh_element():
    col = C.BarColumn(glyphs="blocks")
    assert col[0] == COL_BAR
    assert len(col) == 7
    assert col[6] == ["▒", "▓", "█", "▓"]


def test_barcolumn_tipless_style_stays_six_tuple():
    col = C.BarColumn(glyphs="ascii")
    assert len(col) == 6


def test_barcolumn_default_smooth_is_static_six_tuple():
    assert len(C.BarColumn()) == 6


def test_barcolumn_explicit_empty_tip_disables_inherited():
    col = C.BarColumn(glyphs="blocks", tip=[])
    assert len(col) == 6


def test_barcolumn_explicit_tip_list():
    col = C.BarColumn(glyphs="ascii", tip=["x", "y"])
    assert len(col) == 7 and col[6] == ["x", "y"]


def test_barcolumn_tip_borrows_named_style():
    col = C.BarColumn(glyphs="ascii", tip="blocks")
    assert col[6] == ["▒", "▓", "█", "▓"]


def test_barcolumn_dict_glyphs_with_tip_inherits():
    col = C.BarColumn(glyphs={"fill": "#", "empty": "-", "tip": ["o", "0"]})
    assert col[6] == ["o", "0"]


# ---- rendering -------------------------------------------------------------

def _bar(width, glyphs, total, advance, ticks=0, **kw):
    """Render a bar after `ticks` frame advances (via refresh on a disabled
    bar, which is a no-op write but still bumps frame_tick)."""
    p = barflow.Progress(C.BarColumn(width=width, style="", glyphs=glyphs, **kw),
                         total=total, disable=True)
    p.__enter__()
    try:
        if advance:
            p.advance(advance)
        for _ in range(ticks):
            p.refresh()
        return p.render_line()
    finally:
        p.close()


def test_tip_renders_at_boundary_cell():
    # blocks: fill █, empty ░, no borders. width 10, frac 0.5 → 5 full cells,
    # then the tip cell (frame_tick 0 → "▒"), then 4 empties.
    assert _bar(10, "blocks", 4, 2, ticks=0) == "█████▒░░░░"


def test_tip_advances_with_frame_tick():
    # blocks tip = ▒▓█▓ cycles with frame_tick.
    assert _bar(10, "blocks", 4, 2, ticks=1) == "█████▓░░░░"
    assert _bar(10, "blocks", 4, 2, ticks=2) == "██████░░░░"
    assert _bar(10, "blocks", 4, 2, ticks=3) == "█████▓░░░░"
    assert _bar(10, "blocks", 4, 2, ticks=4) == "█████▒░░░░"  # wrapped


def test_tip_absent_at_full():
    # At 100% the boundary block is skipped entirely → solid bar, no tip,
    # and it stays solid no matter how far frame_tick advances.
    assert _bar(10, "blocks", 4, 4, ticks=0) == "██████████"
    assert _bar(10, "blocks", 4, 4, ticks=3) == "██████████"


def test_tip_present_at_zero_fill():
    # frac 0 still animates: tip sits in cell 0, rest empty.
    assert _bar(10, "blocks", 4, 0, ticks=0) == "▒░░░░░░░░░"
    assert _bar(10, "blocks", 4, 0, ticks=2) == "█░░░░░░░░░"


def test_tipless_style_unchanged_by_frame_tick():
    # ascii has no tip → identical to pre-tip behavior, frame-tick-invariant.
    assert _bar(10, "ascii", 4, 2, ticks=0) == "[#####-----]"
    assert _bar(10, "ascii", 4, 2, ticks=5) == "[#####-----]"


def test_explicit_tip_overrides_on_arbitrary_style():
    # A 2-frame explicit tip on the ascii style: boundary cell cycles a/b.
    assert _bar(10, "ascii", 4, 2, ticks=0, tip=["a", "b"]) == "[#####a----]"
    assert _bar(10, "ascii", 4, 2, ticks=1, tip=["a", "b"]) == "[#####b----]"


# ---- spinners: new procedural built-ins ------------------------------------

def test_new_procedural_spinners_registered():
    for name in ("wave", "wave_wide", "dots_wave", "bounce", "scan", "flow"):
        assert name in spinners.SPINNERS, name
        frames = spinners.SPINNERS[name]
        assert frames and all(isinstance(f, str) for f in frames), name


def test_wave_frames_constant_width():
    # Every frame of a given spinner must have one display width so the
    # column doesn't jitter. _wave samples single-cell glyphs.
    for name in ("wave", "wave_wide", "dots_wave"):
        widths = {len(f) for f in spinners.SPINNERS[name]}
        assert len(widths) == 1, (name, widths)

"""Layout regression tests for examples/gallery.py.

The gallery renders every preset as one row in a fixed grid. These guard the
two properties a user expects: every row renders to the SAME display width
(so name, bar, and percent columns stack vertically) and no row exceeds the
terminal width (no overflow / clipped percent), across fills, frame ticks,
terminal widths, and sections with/without spinners.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from barflow import themes

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _load_gallery():
    path = Path(__file__).resolve().parent.parent / "examples" / "gallery.py"
    spec = importlib.util.spec_from_file_location("gallery_example", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


g = _load_gallery()


def _render_rows(section, term):
    lineup = [n for n in g.SECTIONS[section] if n in themes.THEMES]
    parts = {n: g.extract(themes.get(n)) for n in lineup}
    name_width = max(len(n) for n in lineup)
    bar_display = g.plan_layout(parts.values(), name_width, term)
    rows = []  # (name, plain_line, width)
    for frac in (0.0, 0.5, 1.0):
        for n in lineup:
            line = g.render_row(n, parts[n], frac, name_width, bar_display)
            plain = ANSI.sub("", line)
            rows.append((n, plain, g.cell_width(plain)))
    return rows, bar_display


@pytest.mark.parametrize("section,term", [
    ("all", 120),
    ("all", 50),     # narrow: bar must clamp
    ("all", 200),    # wide: bar caps at 40
    ("emoji", 80),   # VS16 emoji (storm) must not overflow
    ("ascii", 120),
    ("neon", 100),
])
def test_rows_align_and_never_overflow(section, term):
    rows, _bar = _render_rows(section, term)
    widths = {w for _n, _p, w in rows}
    assert len(widths) == 1, f"ragged rows for {section}@{term}: {sorted(widths)}"
    assert max(widths) <= term, f"row overflows terminal for {section}@{term}"


def test_rows_start_with_name_not_a_spinner():
    # Every row begins with the (left-justified) preset name — no per-theme
    # spinner prefix, so the left edge is uniform.
    rows, _bar = _render_rows("all", 120)
    for name, plain, _w in rows:
        assert plain.startswith(name), f"{name!r} row starts with {plain[:8]!r}"


def test_storm_emoji_bar_fits():
    # Regression for the VS16 over-count: storm's ⚡️/☁️ bar must stay within
    # the uniform width on terminals that render the selector as a placeholder.
    rows, _bar = _render_rows("emoji", 80)
    storm = [w for n, _p, w in rows if n == "storm"]
    assert storm and max(storm) <= 80


def test_bar_display_caps_at_40_on_wide_terminal():
    _rows, bar_display = _render_rows("all", 300)
    assert bar_display == 40


def test_narrow_terminal_clamps_bar_display():
    _rows, bar_display = _render_rows("all", 50)
    assert bar_display < 40


# ---- animated tip ----------------------------------------------------------

def test_tipped_theme_extracts_tip_frames():
    # matrix uses the braille glyph set, which carries a built-in tip.
    parts = g.extract(themes.get("matrix"))
    assert parts["bar_tip"], "expected matrix to carry an animated tip"


def test_build_bar_tip_cycles_and_vanishes_at_full():
    glyphs = ("#", "-", [], "[", "]")     # no partials → tip owns the edge
    # Incomplete: boundary cell cycles the tip with `tick`.
    assert g.build_bar(glyphs, 10, 0.5, ("a", "b"), 0) == "[#####a----]"
    assert g.build_bar(glyphs, 10, 0.5, ("a", "b"), 1) == "[#####b----]"
    # Complete: no boundary cell, so no dangling tip.
    assert g.build_bar(glyphs, 10, 1.0, ("a", "b"), 0) == "[##########]"
    # No tip → unchanged static edge.
    assert g.build_bar(glyphs, 10, 0.5, (), 0) == "[#####-----]"


def test_all_bars_reach_100_percent(monkeypatch):
    # Regression: per-preset rates are normalized against the slowest pick so
    # the slowest bar still completes within the frame budget. Previously a
    # rate < 1 froze below 100%. Drive the real loop and check the final frame.
    import io

    buf = io.StringIO()
    monkeypatch.setattr(g.sys, "stdout", buf)
    presets = ["fire", "ocean", "matrix", "acid", "neon"]
    g.run_gallery(presets, duration=0.3, fps=10, seed=1)

    plain = ANSI.sub("", buf.getvalue())
    rows = [ln for ln in plain.split("\n") if ln.strip()]
    final = rows[-len(presets):]               # last frame = one row per preset
    assert len(final) == len(presets)
    for ln in final:
        assert ln.rstrip().endswith("100%"), ln


def test_rows_align_across_frame_ticks():
    # The tip cycles by frame; a tip frame wider than the body glyph would
    # ragged the grid. Sweep ticks × fills and demand one uniform width.
    section, term = "all", 120
    lineup = [n for n in g.SECTIONS[section] if n in themes.THEMES]
    parts = {n: g.extract(themes.get(n)) for n in lineup}
    name_width = max(len(n) for n in lineup)
    bar_display = g.plan_layout(parts.values(), name_width, term)
    widths = set()
    for tick in range(8):
        for frac in (0.2, 0.5, 0.8):
            for n in lineup:
                line = g.render_row(n, parts[n], frac, name_width,
                                    bar_display, tick)
                widths.add(g.cell_width(ANSI.sub("", line)))
    assert len(widths) == 1, f"ragged across ticks: {sorted(widths)}"
    assert max(widths) <= term

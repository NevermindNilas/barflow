"""Byte-level tests for the C render pipeline.

These exercise render_column/format logic through two additive C-core hooks
that produce no console output and have no frame-state side effects:

  * `Progress.render_line(task_id=0) -> str` — renders a task's columns
    exactly as a live frame would, into a returned string.
  * `barflow._core._display_width(s) -> int` — the renderer's own cell
    accounting (skips ANSI CSI, counts wide/zero-width glyphs).

Columns are left unstyled so output is plain text regardless of whether
the test process's stderr is a VT-capable console.
"""

from __future__ import annotations

import pytest

import barflow
from barflow import columns as C
from barflow._core import _display_width as dw


# ---- _display_width --------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("abc", 3),
    ("", 0),
    ("██", 2),                      # full-block fill, 1 cell each
    ("★☆", 2),                      # ★ ☆ — 1-cell symbol glyphs
    ("♥♡", 2),                      # ♥ ♡ — 1-cell
    ("⣿⠀", 2),                      # braille — 1-cell
    ("\U0001f525", 2),                        # 🔥 emoji — 2 cells
    ("⬛", 2),                            # ⬛ — 2 cells
    ("⚫", 2),                            # ⚫ — 2 cells
    ("⚡️", 2),                      # ⚡️ base+VS16 — 2 cells
    ("⚡", 1),                            # bare ⚡ text presentation — 1
    ("你好", 4),                      # CJK 你好 — 2 cells each
    ("\x1b[36mab\x1b[0m", 2),                 # ANSI CSI skipped
])
def test_display_width(text, expected):
    assert dw(text) == expected


# ---- render_line: bar fill math --------------------------------------------

def _bar(width, glyphs, total, advance):
    p = barflow.Progress(C.BarColumn(width=width, style="", glyphs=glyphs),
                         total=total, disable=True)
    p.__enter__()
    try:
        if advance:
            p.advance(advance)
        return p.render_line()
    finally:
        p.close()


def test_render_bar_empty():
    assert _bar(10, "ascii", 4, 0) == "[----------]"


def test_render_bar_half():
    assert _bar(10, "ascii", 4, 2) == "[#####-----]"


def test_render_bar_full():
    assert _bar(10, "ascii", 4, 4) == "[##########]"


def test_render_bar_overshoot_is_clamped_full():
    # advance past total must not overflow the bar body.
    assert _bar(10, "ascii", 4, 99) == "[##########]"


# ---- render_line: percent --------------------------------------------------

def _line(total, advance, *cols):
    p = barflow.Progress(*cols, total=total, disable=True)
    p.__enter__()
    try:
        if advance:
            p.advance(advance)
        return p.render_line()
    finally:
        p.close()


def test_render_percent_right_aligned():
    assert _line(100, 0, C.PercentColumn()) == "  0%"
    assert _line(100, 50, C.PercentColumn()) == " 50%"
    assert _line(100, 100, C.PercentColumn()) == "100%"


def test_render_percent_unknown_total_sentinel():
    assert _line(0, 5, C.PercentColumn()) == "  ?%"


# ---- render_line: count ----------------------------------------------------

def test_render_count_with_total():
    assert _line(10, 3, C.CountColumn()) == "3/10"


def test_render_count_overshoot_display_clamped():
    # Display clamps to total ("3/3"), even though the raw counter overshoots.
    p = barflow.Progress(C.CountColumn(), total=3, disable=True)
    p.__enter__()
    try:
        p.advance(10)
        assert p.render_line() == "3/3"
        assert p.completed == 10      # raw counter is intentionally unclamped
    finally:
        p.close()


def test_render_count_unknown_total_no_slash():
    assert _line(0, 7, C.CountColumn()) == "7"


# ---- render_line: text / description ---------------------------------------

def test_render_text_column_literal():
    assert _line(4, 0, C.TextColumn("hello")) == "hello"


def test_render_description_column():
    p = barflow.Progress(C.DescriptionColumn(), total=4, desc="job", disable=True)
    p.__enter__()
    try:
        assert p.render_line() == "job"
    finally:
        p.close()


# ---- render_line: composition + width integration --------------------------

def test_render_line_composition():
    line = _line(4, 1, C.DescriptionColumn(), C.TextColumn(" "),
                 C.PercentColumn(), C.TextColumn(" "),
                 C.BarColumn(width=8, style="", glyphs="ascii"))
    assert line == " " + " 25% " + "[##------]"  # empty desc + " " + percent + bar


def test_render_unstyled_line_has_no_ansi():
    line = _line(4, 2, C.BarColumn(width=6, style="", glyphs="ascii"),
                 C.PercentColumn(), C.CountColumn())
    assert "\x1b" not in line


def test_display_width_matches_render_line_cells():
    # An emoji bar's rendered width in cells should be double its glyph count.
    line = _line(4, 4, C.BarColumn(width=6, style="", glyphs="emoji_fire"))
    assert dw(line) == 12     # 6 fire glyphs * 2 cells (no borders in emoji_fire)


# ---- render_line: errors ---------------------------------------------------

def test_render_line_out_of_range_raises():
    with barflow.Progress(total=4, disable=True) as p:
        with pytest.raises(IndexError):
            p.render_line(5)


# ---- spinner completion receipt ---------------------------------------------

def test_spinner_renders_check_mark_when_task_finished():
    p = barflow.Progress(C.SpinnerColumn(name="dots", style=""),
                         total=4, disable=True)
    p.__enter__()
    try:
        assert p.render_line() != "✔"   # still animating
        p.advance(4)
        assert p.render_line() == "✔"
    finally:
        p.close()


def test_spinner_keeps_spinning_when_total_unknown():
    # Indeterminate task: no total -> never "finished", no check mark.
    p = barflow.Progress(C.SpinnerColumn(name="dots", style=""),
                         total=0, disable=True)
    p.__enter__()
    try:
        p.advance(100)
        assert p.render_line() != "✔"
    finally:
        p.close()


def test_default_columns_show_spinner_then_check_mark():
    p = barflow.Progress(total=2, desc="job", disable=True)
    p.__enter__()
    try:
        assert p.render_line(0, 200).startswith("⠋ job: ")
        p.advance(2)
        assert p.render_line(0, 200).startswith("✔ job: ")
    finally:
        p.close()


def test_default_bar_has_animated_tip_at_boundary():
    # 4/10 of a 40-cell bar = 16 full cells; the next cell is the comet
    # tip (frame 0 = "░" since frame_tick never advances when disabled).
    p = barflow.Progress(total=10, disable=True)
    p.__enter__()
    try:
        p.advance(4)
        line = p.render_line(0, 200)
        assert "█" * 16 + "░" in line
    finally:
        p.close()


# ---- every shipped theme renders -------------------------------------------

def test_every_theme_renders_through_pipeline():
    """Drive every preset through the full render pipeline (emoji glyphs,
    spinners, partials, borders, styles) and confirm none crash and all
    produce a measurable line. Guards the width/render changes against any
    theme-specific regression."""
    from barflow import themes
    failures = []
    for name in themes.names():
        cols = themes.get(name)
        p = barflow.Progress(*cols, total=50, desc="demo", disable=True)
        p.__enter__()
        try:
            p.advance(20)
            line = p.render_line()
            assert isinstance(line, str)
            assert dw(line) >= 0
        except Exception as exc:  # noqa: BLE001 - report which theme broke
            failures.append((name, repr(exc)))
        finally:
            p.close()
    assert not failures, failures

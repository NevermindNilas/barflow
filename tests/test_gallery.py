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


def _row_widths(section, term):
    lineup = [n for n in g.SECTIONS[section] if n in themes.THEMES]
    parts = {n: g.extract(themes.get(n)) for n in lineup}
    name_width = max(len(n) for n in lineup)
    spin_w, bar_display = g.plan_layout(parts.values(), name_width, term)
    widths = []
    for frac in (0.0, 0.5, 1.0):
        for tick in (0, 1, 3, 7):
            for n in lineup:
                line = g.render_row(n, parts[n], frac, tick,
                                    name_width, spin_w, bar_display)
                widths.append(g.cell_width(ANSI.sub("", line)))
    return widths, spin_w, bar_display


@pytest.mark.parametrize("section,term", [
    ("all", 120),
    ("all", 50),     # narrow: bar must clamp
    ("all", 200),    # wide: bar caps at 40
    ("emoji", 80),
    ("ascii", 120),  # no spinners
    ("neon", 100),
])
def test_rows_align_and_never_overflow(section, term):
    widths, _spin_w, _bar = _row_widths(section, term)
    assert len(set(widths)) == 1, f"ragged rows for {section}@{term}: {sorted(set(widths))}"
    assert max(widths) <= term, f"row overflows terminal for {section}@{term}"


def test_ascii_section_reserves_no_spinner_cell():
    # No preset in the ascii lineup has a spinner, so no spinner column.
    _widths, spin_w, _bar = _row_widths("ascii", 120)
    assert spin_w == 0


def test_bar_display_caps_at_40_on_wide_terminal():
    _widths, _spin_w, bar_display = _row_widths("all", 300)
    assert bar_display == 40


def test_narrow_terminal_clamps_bar_display():
    _widths, _spin_w, bar_display = _row_widths("all", 50)
    assert bar_display < 40

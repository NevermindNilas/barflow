"""Unit tests for column factories and resolution (barflow.columns)."""

from __future__ import annotations

import pytest

from barflow import columns as C
from barflow._core import (
    COL_BAR, COL_CALLBACK, COL_COUNT, COL_DESCRIPTION, COL_ETA, COL_PERCENT,
    COL_RATE, COL_SPINNER, COL_TEXT,
)


def test_text_column_shape():
    t = C.TextColumn("hi")
    assert t[0] == COL_TEXT
    assert t[1] == "hi"
    assert len(t) == 5


def test_description_column_type():
    assert C.DescriptionColumn()[0] == COL_DESCRIPTION


def test_simple_columns_types():
    assert C.PercentColumn()[0] == COL_PERCENT
    assert C.CountColumn()[0] == COL_COUNT
    assert C.RateColumn()[0] == COL_RATE
    assert C.EtaColumn()[0] == COL_ETA


def test_bar_column_is_six_tuple_with_glyphs():
    b = C.BarColumn(width=20, glyphs="ascii")
    assert b[0] == COL_BAR
    assert b[2] == 20
    assert len(b) == 6          # carries the glyph tuple
    assert isinstance(b[5], tuple)


def test_bar_column_flex_width_sentinel():
    # width=None encodes as the -1 flex sentinel.
    assert C.BarColumn(width=None)[2] == -1


def test_color_is_alias_for_style():
    by_style = C.PercentColumn(style="cyan")
    by_color = C.PercentColumn(color="cyan")
    assert by_style[4] == by_color[4] == "\x1b[36m"


def test_spinner_column_carries_frames():
    s = C.SpinnerColumn(name="line")
    assert s[0] == COL_SPINNER
    assert isinstance(s[3], list) and s[3]


def test_spinner_unknown_name_falls_back_to_dots():
    fallback = C.SpinnerColumn(name="does-not-exist")
    from barflow.spinners import SPINNERS
    assert fallback[3] == SPINNERS["dots"]


def test_callback_column_requires_callable():
    with pytest.raises(TypeError):
        C.CallbackColumn("not callable")


def test_callback_column_shape():
    col = C.CallbackColumn(lambda task: "")
    assert col[0] == COL_CALLBACK
    assert callable(col[5])


def test_resolve_columns_promotes_strings():
    out = C.resolve_columns(["hello"])
    assert out == [(COL_TEXT, "hello", 0, None, "")]


def test_resolve_columns_passes_through_factories():
    bar = C.BarColumn()
    pct = C.PercentColumn()
    assert C.resolve_columns([bar, pct]) == [bar, pct]


def test_resolve_columns_rejects_bad_type():
    with pytest.raises(TypeError):
        C.resolve_columns([123])

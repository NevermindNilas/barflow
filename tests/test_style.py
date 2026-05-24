"""Unit tests for the ANSI style-spec parser (barflow.style)."""

from __future__ import annotations

import pytest

from barflow import style
from barflow.style import RESET, style as parse


def test_empty_spec_returns_empty():
    assert parse("") == ""
    assert parse(None) == ""


def test_named_foreground():
    assert parse("cyan") == "\x1b[36m"
    assert parse("red") == "\x1b[31m"
    assert parse("bright_green") == "\x1b[92m"


def test_gray_grey_aliases_map_to_bright_black():
    assert parse("gray") == parse("grey") == "\x1b[90m"


def test_text_styles():
    assert parse("bold") == "\x1b[1m"
    assert parse("dim italic") == "\x1b[2;3m"


def test_hex_foreground_truecolor():
    assert parse("#ff8800") == "\x1b[38;2;255;136;0m"


def test_short_hex_expands():
    # #f80 -> #ff8800
    assert parse("#f80") == "\x1b[38;2;255;136;0m"


def test_style_and_hex_combined():
    assert parse("bold #ff8800") == "\x1b[1;38;2;255;136;0m"


def test_256_color_foreground():
    assert parse("color(214)") == "\x1b[38;5;214m"


def test_background_space_form():
    assert parse("white on blue") == "\x1b[37;44m"


def test_background_underscore_form():
    assert parse("bold white on_blue") == "\x1b[1;37;44m"


def test_background_hex():
    assert parse("on #1a001a") == "\x1b[48;2;26;0;26m"


def test_background_256():
    assert parse("on color(33)") == "\x1b[48;5;33m"


def test_raw_escape_passthrough():
    raw = "\x1b[4;38;5;201m"
    assert parse(raw) == raw


def test_reset_constant():
    assert RESET == "\x1b[0m"


@pytest.mark.parametrize("spec", [
    "#zz",            # bad hex digits
    "#abcd",          # wrong hex length
    "color(300)",     # 256 index out of range
    "on",             # background keyword with no color
    "on bogus",       # unknown background name
    "on_bogus",       # unknown underscore background
    "bogustoken",     # unknown token
])
def test_invalid_specs_raise_value_error(spec):
    with pytest.raises(ValueError):
        parse(spec)


def test_module_exports():
    assert set(style.__all__) == {"style", "RESET"}

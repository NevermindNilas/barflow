"""Unit tests for bar glyph sets (barflow.bar_styles)."""

from __future__ import annotations

import pytest

from barflow import bar_styles
from barflow.bar_styles import BAR_STYLES, get, to_tuple


def test_every_builtin_has_required_keys():
    required = {"fill", "empty", "partials", "left", "right"}
    for name, spec in BAR_STYLES.items():
        assert required <= set(spec), name
        assert isinstance(spec["partials"], list), name


def test_get_known():
    assert get("ascii")["fill"] == "#"


def test_get_unknown_raises():
    with pytest.raises(ValueError):
        get("definitely-not-a-style")


def test_to_tuple_from_name():
    fill, empty, partials, left, right = to_tuple("ascii")
    assert (fill, empty, left, right) == ("#", "-", "[", "]")
    assert partials == []


def test_to_tuple_shape_is_five():
    assert len(to_tuple("smooth")) == 5


def test_to_tuple_partial_dict_merges_smooth_defaults():
    # Supplying only `fill` should inherit smooth's borders/partials.
    t = to_tuple({"fill": "X"})
    smooth = to_tuple("smooth")
    assert t[0] == "X"           # overridden fill
    assert t[2] == smooth[2]     # inherited partials
    assert t[3] == smooth[3]     # inherited left border


def test_to_tuple_copies_partials_list():
    # Mutating the returned partials must not corrupt the registry.
    t = to_tuple("smooth")
    t[2].append("ZZZ")
    assert "ZZZ" not in BAR_STYLES["smooth"]["partials"]


def test_to_tuple_unknown_name_raises():
    with pytest.raises(ValueError):
        to_tuple("nope")


def test_to_tuple_bad_type_raises():
    with pytest.raises(TypeError):
        to_tuple(123)

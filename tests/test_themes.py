"""Unit tests for the theme preset registry (barflow.themes)."""

from __future__ import annotations

import random

import pytest

from barflow import themes
from barflow.columns import resolve_columns


def test_get_unknown_raises():
    with pytest.raises(ValueError):
        themes.get("no-such-theme")


def test_names_are_deduped_and_sorted():
    names = themes.names()
    assert names == sorted(names)
    assert len(names) == len(set(names))
    # Aliases collapse: classic exists, random_theme is excluded by name set.
    assert "classic" in names


def test_every_theme_resolves_without_error():
    """Catches a bad glyph/style/spinner name in any preset."""
    failures = []
    for name in themes.names():
        cols = themes.get(name)
        # Strings are literal text columns; factory tuples must resolve.
        factories = [c for c in cols if not isinstance(c, str)]
        try:
            resolved = resolve_columns(factories)
            assert isinstance(resolved, list)
        except Exception as exc:  # noqa: BLE001 - report which theme broke
            failures.append((name, repr(exc)))
    assert not failures, failures


def test_get_returns_fresh_list_each_call():
    a = themes.get("classic")
    b = themes.get("classic")
    assert a is not b


def test_random_theme_reproducible_under_seed():
    random.seed(1234)
    first = themes.random_theme()
    random.seed(1234)
    second = themes.random_theme()
    assert first == second


def test_random_theme_never_returns_itself():
    # Drive several picks; none should recurse into random_theme.
    random.seed(7)
    for _ in range(50):
        cols = themes.random_theme()
        assert isinstance(cols, list)
        assert cols  # a real theme always has columns


def test_aliases_point_at_same_factory():
    assert themes.THEMES["rich"] is themes.THEMES["rich_like"]
    assert themes.THEMES["github"] is themes.THEMES["github_dark"]

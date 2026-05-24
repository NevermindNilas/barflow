"""Unit tests for the spinner frame library and compositional DSL."""

from __future__ import annotations

import pytest

from barflow import spinners
from barflow.spinners import (
    SPINNERS, alongside, bouncing, frame, scrolling, sequential,
)


def test_builtin_spinners_are_nonempty_string_lists():
    assert SPINNERS, "expected built-in spinners"
    for name, frames in SPINNERS.items():
        assert isinstance(frames, list) and frames, name
        assert all(isinstance(f, str) for f in frames), name


def test_frame_is_identity_list():
    assert frame("a", "b", "c") == ["a", "b", "c"]
    assert frame() == []


def test_scrolling_slides_window():
    # "ab" through a width-2 window padded with spaces on both sides.
    assert scrolling("ab", length=2) == ["  ", " a", "ab", "b ", "  "]


def test_scrolling_every_frame_has_window_length():
    frames = scrolling("hello", length=4)
    assert all(len(f) == 4 for f in frames)


def test_scrolling_rejects_nonpositive_length():
    with pytest.raises(ValueError):
        scrolling("x", length=0)
    with pytest.raises(ValueError):
        scrolling("x", length=-3)


def test_bouncing_is_palindrome_of_scrolling():
    fwd = scrolling("ab", length=2)
    assert bouncing("ab", length=2) == fwd + list(reversed(fwd[1:-1]))


def test_sequential_concatenates():
    assert sequential(["a", "b"], ["c"]) == ["a", "b", "c"]
    assert sequential() == []


def test_alongside_steps_together():
    # Longest spec has 2 frames; the shorter cycles via modulo.
    assert alongside(["A", "B"], ["x"]) == ["Ax", "Bx"]


def test_alongside_separator():
    assert alongside(["A", "B"], ["1", "2"], sep="-") == ["A-1", "B-2"]


def test_alongside_empty():
    assert alongside() == []


def test_module_exports():
    assert "SPINNERS" in spinners.__all__
    for fn in ("frame", "scrolling", "bouncing", "sequential", "alongside"):
        assert fn in spinners.__all__

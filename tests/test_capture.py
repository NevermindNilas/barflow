"""Tests for capture_output stdout/stderr redirection and its teardown.

These guard a class of bug where the live-bar stdout proxy is installed but
never uninstalled, leaving `sys.stdout` permanently replaced for the rest of
the process — and where a final newline-less `print(..., end="")` is dropped.
"""

from __future__ import annotations

import sys

import pytest

import barflow
from barflow.hooks import StdoutCapture, _ProgressStream


class _RecordingProgress:
    """Stand-in for a Progress that records write_above payloads."""

    def __init__(self):
        self.lines: list[str] = []

    def write_above(self, text):
        self.lines.append(text)


# ---- hooks-level unit tests ------------------------------------------------

def test_stream_emits_complete_lines_on_newline():
    fp = _RecordingProgress()
    s = _ProgressStream(fp, sys.__stdout__, "stdout")
    s.write("alpha\n")
    assert fp.lines == ["alpha\n"]


def test_stream_holds_partial_until_newline():
    fp = _RecordingProgress()
    s = _ProgressStream(fp, sys.__stdout__, "stdout")
    s.write("no-newline-yet")
    assert fp.lines == []          # held — standard line buffering
    s.write(" rest\n")
    assert fp.lines == ["no-newline-yet rest\n"]


def test_drain_flushes_trailing_partial_line():
    # The regression: a final print(end="") must not be lost on teardown.
    fp = _RecordingProgress()
    s = _ProgressStream(fp, sys.__stdout__, "stdout")
    s.write("tail-without-newline")
    s.drain()
    assert "tail-without-newline" in "".join(fp.lines)


def test_drain_is_noop_when_empty():
    fp = _RecordingProgress()
    s = _ProgressStream(fp, sys.__stdout__, "stdout")
    s.drain()
    assert fp.lines == []


def test_capture_install_uninstall_restores_streams():
    fp = _RecordingProgress()
    cap = StdoutCapture(fp, capture_stdout=True, capture_stderr=True)
    saved_out, saved_err = sys.stdout, sys.stderr
    cap.install()
    assert sys.stdout is not saved_out
    assert sys.stderr is not saved_err
    cap.uninstall()
    assert sys.stdout is saved_out
    assert sys.stderr is saved_err


def test_capture_uninstall_drains_trailing_partial():
    fp = _RecordingProgress()
    cap = StdoutCapture(fp)
    cap.install()
    try:
        print("complete")
        print("partial", end="")   # no newline
    finally:
        cap.uninstall()
    joined = "".join(fp.lines)
    assert "complete" in joined
    assert "partial" in joined     # would be lost without drain()


# ---- track() integration tests --------------------------------------------

def test_track_capture_output_restores_stdout_on_exhaust():
    saved = sys.stdout
    list(barflow.track(range(5), disable=True, capture_output=True))
    assert sys.stdout is saved


def test_track_capture_output_restores_stdout_on_break():
    saved = sys.stdout
    for _ in barflow.track(range(100), disable=True, capture_output=True):
        break
    # The generator guard's finally runs on close (GC of the for-loop iterator).
    assert sys.stdout is saved


def test_track_capture_output_restores_stdout_on_exception():
    saved = sys.stdout
    with pytest.raises(RuntimeError):
        for i in barflow.track(range(100), disable=True, capture_output=True):
            if i == 2:
                raise RuntimeError("boom")
    assert sys.stdout is saved


def test_track_capture_output_yields_all_values():
    saved = sys.stdout
    out = list(barflow.track(range(4), disable=True, capture_output=True))
    assert out == [0, 1, 2, 3]
    assert sys.stdout is saved

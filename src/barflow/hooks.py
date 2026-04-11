"""Stdout/stderr interception so user `print()` plays nicely with live bars.

When `Progress(capture_output=True)` is active, writes to `sys.stdout` /
`sys.stderr` are line-buffered in Python, then shipped to the C core's
`Progress.write_above()` primitive, which:

    1. Acquires the render mutex.
    2. Walks the cursor back to the top of the bar area.
    3. Clears to end-of-screen.
    4. Writes the user text (adds a trailing newline if missing).
    5. Releases the mutex and notifies the render thread to repaint.

This is the same trick alive-progress pulls with its `hook_manager` —
see `alive_progress/core/hook_manager.py` — ported to interop with our
C++ render loop.
"""

from __future__ import annotations

import sys
from typing import TextIO


class _ProgressStream:
    """A thin text stream that forwards writes to a Progress's write_above."""

    def __init__(self, progress, original: TextIO, name: str):
        self._progress = progress
        self._orig = original
        self._buf: list[str] = []
        self._name = name
        # Cache hot stream attrs as real instance attrs so user code that
        # reads `sys.stdout.encoding` / `.errors` / etc. doesn't fall through
        # our __getattr__. The wrapped stream is stable for the lifetime of
        # this proxy (install/uninstall replaces the whole object).
        for _attr in ("encoding", "errors", "mode", "fileno", "buffer",
                      "newlines", "line_buffering"):
            try:
                setattr(self, _attr, getattr(original, _attr))
            except AttributeError:
                pass

    # Pretend to be the original stream where possible.
    def __getattr__(self, attr):
        return getattr(self._orig, attr)

    def write(self, s):
        if not isinstance(s, str):
            s = str(s)
        if not s:
            return 0
        self._buf.append(s)
        if "\n" in s:
            self.flush()
        return len(s)

    def flush(self):
        if not self._buf:
            return
        text = "".join(self._buf)
        self._buf.clear()
        # Split into complete lines + trailing partial.
        if not text.endswith("\n"):
            nl = text.rfind("\n")
            if nl == -1:
                # No complete line yet — hold until newline seen.
                self._buf.append(text)
                return
            complete, trailing = text[: nl + 1], text[nl + 1 :]
            self._progress.write_above(complete)
            if trailing:
                self._buf.append(trailing)
        else:
            self._progress.write_above(text)

    def isatty(self):
        try:
            return self._orig.isatty()
        except Exception:
            return False

    def writable(self):
        return True


class StdoutCapture:
    """Context-manager helper installed by Progress when capture_output=True."""

    def __init__(self, progress, capture_stdout=True, capture_stderr=False):
        self._progress = progress
        self._cap_out = capture_stdout
        self._cap_err = capture_stderr
        self._saved_out = None
        self._saved_err = None

    def install(self):
        if self._cap_out:
            self._saved_out = sys.stdout
            sys.stdout = _ProgressStream(self._progress, self._saved_out, "stdout")
        if self._cap_err:
            self._saved_err = sys.stderr
            sys.stderr = _ProgressStream(self._progress, self._saved_err, "stderr")

    def uninstall(self):
        if self._cap_out and self._saved_out is not None:
            try:
                sys.stdout.flush()
            except Exception:
                pass
            sys.stdout = self._saved_out
            self._saved_out = None
        if self._cap_err and self._saved_err is not None:
            try:
                sys.stderr.flush()
            except Exception:
                pass
            sys.stderr = self._saved_err
            self._saved_err = None

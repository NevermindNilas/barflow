"""File-object progress wrapping — meter a binary stream's byte throughput.

`wrap_file` returns a transparent proxy whose `read`/`write` family advance a
barflow bar by the bytes actually transferred; every other attribute passes
straight through to the wrapped object. `wrapattr` is the tqdm-spelled alias.

The proxy owns only the *bar*: `__exit__` finalizes it but never closes the
underlying stream (the caller opened it, the caller closes it); `close()` is
the one path that also closes the stream, on the assumption the caller is
handing the object off entirely.
"""

from __future__ import annotations

import io
import os
import sys

from . import _progress


def wrap_file(fileobj, *, total=None, desc=None, disable=None, leave=True,
              unit="B", unit_scale=True, unit_divisor=1024, **progress_kwargs):
    """Wrap a binary file-like object so every read()/write() advances a
    barflow progress bar by the number of bytes transferred. Returns a
    transparent proxy: unknown attributes pass through to the wrapped object.

    total: bytes expected. When None, inferred from os.fstat(fileobj.fileno())
           minus the current position (fileobj.tell()) when the object is a
           real seekable file; falls back to an indeterminate bar (total 0)
           when the size can't be determined (no fileno, pipe, BytesIO w/o
           fileno, etc.). Never raise from inference — swallow OSError/
           AttributeError/io.UnsupportedOperation and treat as unknown.
    disable: None => auto (disable when sys.stderr is not a tty).
    """
    # Always hand the core a concrete int: advance() is a silent no-op unless
    # task 0 exists, and task 0 is only materialized when total is not None.
    # So an indeterminate stream must still pass total=0 (creates a bounded-by-
    # zero == unbounded task) rather than None, or nothing would ever count.
    if total is None:
        total = _infer_total(fileobj)
    if disable is None:
        disable = _auto_disable()

    progress = _progress.Progress(
        total=total,
        desc=desc,
        disable=disable,
        leave=leave,
        unit=unit,
        unit_scale=unit_scale,
        unit_divisor=unit_divisor,
        **progress_kwargs,
    )
    # Enter here so the render thread is live and the bar counts from the very
    # first read/write; the proxy's __exit__/close performs the matching exit.
    progress.__enter__()
    return _FileProxy(fileobj, progress)


def wrapattr(fileobj, name, *, total=None, desc=None, **kwargs):
    """tqdm-compatible spelling. `name` is "read" or "write" — the method
    whose byte throughput drives the bar. Implemented on top of wrap_file
    (which already intercepts both read and write; a read-only stream never
    calls write and vice-versa, so wrapping both is harmless). Kept as a
    thin, documented alias so tqdm users find the name they expect."""
    # `name` selects a *direction* in tqdm; our proxy meters both and a stream
    # only ever exercises one, so we accept the argument for source-level
    # compatibility and otherwise defer entirely to wrap_file.
    return wrap_file(fileobj, total=total, desc=desc, **kwargs)


def _infer_total(fileobj):
    """Best-effort byte count remaining in `fileobj`, or 0 (indeterminate).

    Only real, seekable files answer fileno()+fstat; pipes, sockets, and
    BytesIO don't. tell() gives the current offset so re-wrapping a partially
    read file meters just the tail. io.UnsupportedOperation subclasses both
    OSError and ValueError, so the tuple below already covers it.
    """
    try:
        pos = fileobj.tell()
        size = os.fstat(fileobj.fileno()).st_size
    except (AttributeError, OSError, ValueError):
        return 0
    remaining = size - pos
    # A negative/zero remainder (already at or past EOF, or an odd fstat) is
    # meaningless as a denominator — degrade to an indeterminate bar.
    return remaining if remaining > 0 else 0


def _auto_disable():
    """Quiet the bar when stderr isn't a terminal (piped/redirected/no
    console) — otherwise a bar would just spam a log file with control codes.
    A stderr that's been swapped for something without isatty() is treated as
    non-interactive."""
    try:
        return not sys.stderr.isatty()
    except (AttributeError, ValueError):
        return True


class _FileProxy:
    """Transparent proxy that advances `progress` by the bytes each read/write
    moves and forwards everything else to the wrapped file object."""

    def __init__(self, fileobj, progress):
        self._fileobj = fileobj
        self._progress = progress
        self._closed = False

    def __getattr__(self, name):
        # __getattr__ only fires when normal lookup misses, so it never
        # shadows our own methods/properties. Guard underscore names: were
        # _fileobj itself missing (e.g. lookup during a half-built instance),
        # delegating through self._fileobj would recurse here forever.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._fileobj, name)

    # ---- byte-metering intercepts -----------------------------------------
    # Each returns whatever the wrapped call returns; we only tap the count.
    # advance() is skipped on a zero-length move to keep EOF reads cheap.

    def read(self, *args, **kw):
        data = self._fileobj.read(*args, **kw)
        n = len(data)
        if n:
            self._progress.advance(n)
        return data

    def read1(self, *args, **kw):
        data = self._fileobj.read1(*args, **kw)
        n = len(data)
        if n:
            self._progress.advance(n)
        return data

    def readinto(self, b):
        # readinto reports bytes into the caller's buffer and yields None at
        # EOF, so guard the None/0 case before advancing.
        n = self._fileobj.readinto(b)
        if n:
            self._progress.advance(n)
        return n

    def readline(self, *a, **kw):
        data = self._fileobj.readline(*a, **kw)
        n = len(data)
        if n:
            self._progress.advance(n)
        return data

    def write(self, data, *a, **kw):
        n = self._fileobj.write(data, *a, **kw)
        # Most streams return the byte count; a few (rare) return None, in
        # which case we fall back to the length of what we handed them.
        amt = n if isinstance(n, int) else len(data)
        if amt:
            self._progress.advance(amt)
        return n

    # ---- lifecycle ---------------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        # Finalize the bar only. The caller owns the file object, so closing
        # it is left to them (close() is the explicit both-at-once path).
        self._progress.__exit__(*exc)
        return False

    def close(self):
        # Idempotent: the C core tolerates a double render-thread teardown,
        # but we still gate so a wrapped object that dislikes double close()
        # (and our own bookkeeping) is only touched once.
        if self._closed:
            return
        self._closed = True
        # Flush the bar's final frame before handing the stream back closed.
        self._progress.__exit__(None, None, None)
        self._fileobj.close()

    # ---- introspection -----------------------------------------------------

    @property
    def completed(self):
        """Bytes transferred so far, per the underlying Progress."""
        return self._progress.completed

    @property
    def progress(self):
        """The underlying Progress, for tests/introspection."""
        return self._progress

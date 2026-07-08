"""Tests for the file-object progress wrapper (barflow._wrap).

All bars run with disable=True so nothing renders; correctness is asserted
through the proxy's `.completed` byte counter and `.progress.total`.
"""

from __future__ import annotations

import io
import os
import tempfile

from barflow._wrap import wrap_file, wrapattr


def test_read_bytesio_advances_by_bytes_read():
    payload = b"abcd" * 500  # 2000 bytes
    f = wrap_file(io.BytesIO(payload), total=len(payload), disable=True)
    while chunk := f.read(64):
        pass
    assert f.completed == len(payload)


def test_real_file_infers_total_from_size():
    payload = b"x" * 4096 + b"tail"
    tmp = tempfile.NamedTemporaryFile(delete=False)
    try:
        tmp.write(payload)
        # Close the OS handle before reopening by path — required on Windows,
        # harmless elsewhere.
        tmp.close()
        size = os.path.getsize(tmp.name)

        with open(tmp.name, "rb") as raw:
            f = wrap_file(raw, total=None, disable=True)
            # Inferred from fstat(size) - tell(0) on a freshly opened file.
            assert f.progress.total == size
            assert f.mode == "rb"          # attribute passthrough (test 4)
            assert f.name == tmp.name
            data = f.read()
            assert len(data) == size
            assert f.completed == size
    finally:
        os.unlink(tmp.name)


def test_write_bytesio_advances_by_bytes_written():
    chunks = [b"one", b"two!!", b"three...."]
    total = sum(len(c) for c in chunks)
    f = wrap_file(io.BytesIO(), total=total, disable=True)
    for c in chunks:
        f.write(c)
    assert f.completed == total


def test_attribute_passthrough_bytesio():
    # getvalue() is a BytesIO-only method reachable only via delegation.
    payload = b"reach-through"
    f = wrap_file(io.BytesIO(payload), total=len(payload), disable=True)
    assert callable(f.getvalue)
    assert f.read() == payload
    assert f.getvalue() == payload


def test_indeterminate_total_still_advances():
    # BytesIO has no fileno(), so inference degrades to total=0 (indeterminate)
    # without raising, and reads must still advance the counter.
    payload = b"z" * 300
    f = wrap_file(io.BytesIO(payload), total=None, disable=True)
    assert f.progress.total is None      # unbounded => None
    while chunk := f.read(50):
        pass
    assert f.completed == len(payload)


def test_readinto_advances_by_returned_count():
    payload = b"q" * 250
    tmp = tempfile.NamedTemporaryFile(delete=False)
    try:
        tmp.write(payload)
        tmp.close()
        with open(tmp.name, "rb") as raw:
            f = wrap_file(raw, disable=True)
            buf = bytearray(100)
            n = f.readinto(buf)
            assert n == 100
            assert f.completed == n
    finally:
        os.unlink(tmp.name)


def test_context_manager_finalizes_without_raising():
    payload = b"ctx" * 40
    with wrap_file(io.BytesIO(payload), total=len(payload), disable=True) as f:
        f.read()
    # Exiting the block finalized the bar (no raise) and the count is intact.
    assert f.completed == len(payload)


def test_wrapattr_read_alias():
    payload = b"tqdm-name" * 10
    f = wrapattr(io.BytesIO(payload), "read", total=len(payload), disable=True)
    assert f.read() == payload
    assert f.completed == len(payload)


def test_close_is_idempotent_and_closes_underlying():
    payload = b"close-me"
    raw = io.BytesIO(payload)
    f = wrap_file(raw, total=len(payload), disable=True)
    f.read()
    f.close()
    f.close()                # double close must not raise
    assert raw.closed        # underlying stream was closed

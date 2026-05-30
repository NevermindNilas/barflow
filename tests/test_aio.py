"""Tests for the asyncio wrapper (barflow.aio.atrack)."""

from __future__ import annotations

import asyncio

import pytest

import barflow.aio as aio
from barflow import columns as C


async def _agen(n):
    for i in range(n):
        yield i


class _AsyncLenSeq:
    """Async-iterable that also exposes __len__, so atrack can infer total."""

    def __init__(self, n):
        self._n = n

    def __len__(self):
        return self._n

    def __aiter__(self):
        return _agen(self._n)


def test_atrack_yields_all_values():
    async def run():
        return [x async for x in aio.atrack(_agen(5), total=5, disable=True)]
    assert asyncio.run(run()) == list(range(5))


def test_atrack_empty():
    async def run():
        return [x async for x in aio.atrack(_agen(0), total=0, disable=True)]
    assert asyncio.run(run()) == []


def test_atrack_without_explicit_total():
    # Async generators have no __len__; atrack must fall back gracefully.
    async def run():
        return [x async for x in aio.atrack(_agen(3), disable=True)]
    assert asyncio.run(run()) == [0, 1, 2]


def test_atrack_infers_total_from_len():
    # An async iterable exposing __len__ lets atrack infer the total.
    async def run():
        return [x async for x in aio.atrack(_AsyncLenSeq(4), disable=True)]
    assert asyncio.run(run()) == [0, 1, 2, 3]


def test_atrack_partial_consumption_then_break():
    # Breaking early must yield only the consumed prefix and not raise;
    # teardown is left to GC of the dropped tracker.
    async def run():
        out = []
        async for x in aio.atrack(_agen(5), total=5, disable=True):
            out.append(x)
            if len(out) == 2:
                break
        return out
    assert asyncio.run(run()) == [0, 1]


def test_atrack_supports_theme_like_track():
    async def run():
        return [x async for x in aio.atrack(_agen(3), total=3,
                                            disable=True, theme="classic")]
    assert asyncio.run(run()) == [0, 1, 2]


def test_atrack_supports_string_shorthand_columns():
    async def run():
        return [x async for x in aio.atrack(
            _agen(3), total=3, disable=True,
            columns=["task: ", C.BarColumn()])]
    assert asyncio.run(run()) == [0, 1, 2]


def test_atrack_rejects_nonzero_task_id():
    async def run():
        async for _ in aio.atrack(_agen(3), total=3, disable=True, task_id=1):
            pass
    with pytest.raises(ValueError):
        asyncio.run(run())

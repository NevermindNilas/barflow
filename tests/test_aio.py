"""Tests for the asyncio wrapper (barflow.aio.atrack)."""

from __future__ import annotations

import asyncio

import barflow.aio as aio


async def _agen(n):
    for i in range(n):
        yield i


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

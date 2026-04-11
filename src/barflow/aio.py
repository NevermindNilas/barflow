"""asyncio integration: `atrack(aiter)` wraps an async iterable.

    async for x in barflow.aio.atrack(stream, total=n, desc="recv"):
        ...
"""

from __future__ import annotations

from ._core import Progress


class _AsyncTracker:
    def __init__(self, aiter, progress: Progress, task_id: int = 0):
        self._aiter = aiter
        self._progress = progress
        self._state = progress
        self._task_id = task_id
        self._closed = False
        # Pre-resolve the per-item step once so the hot path is a single
        # attribute-free call. For task 0 we can bind `progress.tick`
        # directly; for named tasks, capture the id in a closure.
        if task_id == 0:
            self._step = progress.tick
        else:
            _update = progress.update
            _tid = task_id
            def _step(_update=_update, _tid=_tid):
                _update(_tid, 1)
            self._step = _step

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            value = await self._aiter.__anext__()
        except StopAsyncIteration:
            if not self._closed:
                self._closed = True
                self._progress.close()
            raise
        # Single pre-bound call — no per-item attribute lookup or branch.
        self._step()
        return value


def atrack(aiterable, total=None, desc=None, **kwargs):
    if total is None and hasattr(aiterable, "__len__"):
        try:
            total = len(aiterable)
        except TypeError:
            total = 0
    p = Progress(total=total, desc=desc, **kwargs)
    p.__enter__()
    if hasattr(aiterable, "__aiter__"):
        ait = aiterable.__aiter__()
    else:
        ait = aiter(aiterable)
    return _AsyncTracker(ait, p)


__all__ = ["atrack"]

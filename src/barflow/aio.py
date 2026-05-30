"""asyncio integration: `atrack(aiter)` wraps an async iterable.

    async for x in barflow.aio.atrack(stream, total=n, desc="recv"):
        ...
"""

from __future__ import annotations

from ._core import Progress as _CoreProgress


class _AsyncTracker:
    def __init__(self, aiter, progress, task_id: int = 0):
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
                # __exit__ (not close): the Python Progress subclass uninstalls
                # stdout/stderr capture there, whereas close() only stops the
                # render thread. For the bare C Progress the two are equivalent.
                self._progress.__exit__(None, None, None)
            raise
        # Single pre-bound call — no per-item attribute lookup or branch.
        self._step()
        return value

    async def aclose(self):
        """Tear down the bar if the async iteration is abandoned before
        exhaustion (e.g. `break` out of the `async for`)."""
        if not self._closed:
            self._closed = True
            self._progress.__exit__(None, None, None)


def atrack(aiterable, total=None, desc=None, *, columns=None, theme=None,
           task_id=0, disable=False, min_interval=0.05, capture_output=False):
    """Wrap an async iterable in a live progress bar. Async mirror of
    `barflow.track` — same fast/slow dispatch, so `theme=`, column
    factories, bare-string columns, and `capture_output=` all behave
    identically here.

    Fast path: no columns/theme/capture_output → straight to the C core.
    Slow path: any decoration → the resolving `Progress` subclass.
    """
    if task_id != 0:
        # atrack() builds a single-task (task 0) bar; mirror track()'s guard
        # so a non-zero task_id fails clearly instead of raising IndexError
        # on the first step.
        raise ValueError(
            "atrack() creates a single-task bar, so task_id must be 0. "
            "For multiple bars use barflow.Progress + add_task()."
        )

    if total is None:
        try:
            total = len(aiterable)
        except TypeError:
            total = 0

    if columns or theme or capture_output:
        from . import _progress
        p = _progress.Progress(
            *(columns or ()),
            total=total,
            desc=desc,
            theme=theme,
            disable=disable,
            min_interval=min_interval,
            capture_output=capture_output,
        )
    else:
        p = _CoreProgress(
            total=total,
            desc=desc,
            min_interval=min_interval,
            disable=disable,
        )

    p.__enter__()
    if hasattr(aiterable, "__aiter__"):
        ait = aiterable.__aiter__()
    else:
        ait = aiter(aiterable)
    tracker = _AsyncTracker(ait, p, task_id=task_id)
    if capture_output:
        # `_AsyncTracker` only runs __exit__ on StopAsyncIteration, so an early
        # `break` out of the `async for` would never uninstall the stdout/stderr
        # capture (a plain async iterator gets no automatic aclose) — sys.stdout
        # would stay replaced until the tracker is GC'd. Wrap in an async-gen
        # guard whose finally fires on break/exception (and at loop shutdown via
        # shutdown_asyncgens), mirroring track()'s _capture_guard. Non-capture
        # bars keep the bare fast tracker (teardown left to GC, as in track()).
        return _acapture_guard(tracker)
    return tracker


async def _acapture_guard(tracker):
    """Drive `tracker`, guaranteeing its teardown runs on exhaustion, early
    break, or exception — async mirror of `track()`'s `_capture_guard`.

    Delegates to `tracker.aclose()`, which is idempotent (guarded by
    `_closed`), so the tracker's own StopAsyncIteration teardown is never
    double-run."""
    try:
        async for value in tracker:
            yield value
    finally:
        await tracker.aclose()


__all__ = ["atrack"]

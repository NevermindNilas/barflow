"""Shared test helpers.

barflow's C core writes rendered frames to the native console fd — there
is no `file=`/sink parameter to capture, so we can't assert on the bytes
a frame produces. Instead we read computed task state through the two
introspection hooks the core exposes:

  * `Progress.completed` / `Progress.n_tasks` — synchronous getters,
    safe to assert immediately after a counter mutation.
  * `CallbackColumn(func)` — `func(task)` runs on the render thread with
    a snapshot exposing `.completed .total .elapsed .rate .speed
    .percentage .fraction .description .frame_tick .task_id`.

The render thread is asynchronous and throttled, so `capture_snapshots`
forces a frame with `refresh()` and polls until the callback has fired
rather than sleeping a fixed amount (which would flake under load).
"""

from __future__ import annotations

import time

import barflow
from barflow import columns as C


def capture_snapshots(total, drive, *, timeout=2.0):
    """Run `drive(progress)` then return the last callback task snapshot.

    `drive` receives the live Progress and should advance it. Returns a
    dict copy of the final snapshot's fields, or raises if the render
    thread never fired a frame within `timeout` seconds.
    """
    snaps: list[dict] = []

    def _cb(task):
        snaps.append({
            "completed": task.completed,
            "total": task.total,
            "elapsed": task.elapsed,
            "rate": task.rate,
            "speed": task.speed,
            "percentage": task.percentage,
            "fraction": task.fraction,
            "description": task.description,
            "frame_tick": task.frame_tick,
            "task_id": task.task_id,
        })
        return ""

    p = barflow.Progress(C.CallbackColumn(_cb), total=total, disable=False)
    p.__enter__()
    try:
        drive(p)
        deadline = time.monotonic() + timeout
        while not snaps and time.monotonic() < deadline:
            p.refresh()
            time.sleep(0.01)
    finally:
        p.__exit__(None, None, None)

    if not snaps:
        raise AssertionError("CallbackColumn never fired a frame")
    return snaps[-1]

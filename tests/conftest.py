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
rather than sleeping a fixed amount (which would flake under load). It
runs with `disable=True`: that suppresses the render thread and any test
output while still firing the CallbackColumn on each explicit `refresh()`.
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

    p = barflow.Progress(C.CallbackColumn(_cb), total=total, disable=True)
    p.__enter__()
    try:
        drive(p)
        # Capture a snapshot taken *after* drive() completed. Record the
        # count first so a frame that may have fired during enter/drive
        # can't be mistaken for the post-drive frame we force below.
        baseline = len(snaps)
        deadline = time.monotonic() + timeout
        while len(snaps) == baseline and time.monotonic() < deadline:
            p.refresh()
            time.sleep(0.01)
    finally:
        p.__exit__(None, None, None)

    if len(snaps) == baseline:
        raise AssertionError("CallbackColumn never fired a post-drive frame")
    return snaps[-1]


def capture_task_snapshot(drive, want_id, *, timeout=2.0):
    """Like `capture_snapshots`, but for a specific task id.

    `capture_snapshots` returns the LAST task iterated each frame (highest
    id), which is ambiguous for multi-task bars. This variant filters the
    CallbackColumn to one `want_id` so per-task state (e.g. a renamed
    description on task 1 vs. task 0) can be asserted unambiguously. `drive`
    is responsible for creating the task(s) via `add_task`.
    """
    snaps: list[dict] = []

    def _cb(task):
        if task.task_id == want_id:
            snaps.append({
                "description": task.description,
                "task_id": task.task_id,
                "completed": task.completed,
                "total": task.total,
            })
        return ""

    p = barflow.Progress(C.CallbackColumn(_cb), disable=True)
    p.__enter__()
    try:
        drive(p)
        baseline = len(snaps)
        deadline = time.monotonic() + timeout
        while len(snaps) == baseline and time.monotonic() < deadline:
            p.refresh()
            time.sleep(0.01)
    finally:
        p.__exit__(None, None, None)

    if len(snaps) == baseline:
        raise AssertionError(f"CallbackColumn never fired for task {want_id}")
    return snaps[-1]

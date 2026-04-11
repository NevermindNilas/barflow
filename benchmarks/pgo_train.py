"""PGO training workload for barflow._core.

Run between the instrumented (BARFLOW_PGO=generate) and optimized
(BARFLOW_PGO=use) builds. Exercises the hot paths so the profile
data reflects real usage:

    - Tracker iter-next (barflow.track over a range)
    - Manual tick() loop
    - advance(n) with a non-unit step
    - Display-on path (render_frame, write_bytes, column formatters)
    - Multi-task add_task + update
    - Synchronous first-frame paint + set_description

Kept deliberately short (a few seconds) because instrumented binaries
run ~3-5x slower than release.
"""

from __future__ import annotations

import io
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import barflow  # noqa: E402

N_HOT = 2_000_000
N_DISP = 500_000
N_MULTI = 200_000


def train_track_nodisplay() -> None:
    for _ in barflow.track(range(N_HOT), total=N_HOT, disable=True):
        pass


def train_track_display() -> None:
    for _ in barflow.track(range(N_DISP), total=N_DISP):
        pass


def train_tick() -> None:
    p = barflow.Progress(total=N_HOT, disable=True)
    p.__enter__()
    tick = p.tick
    for _ in range(N_HOT):
        tick()
    p.__exit__(None, None, None)


def train_advance_n() -> None:
    p = barflow.Progress(total=N_HOT, disable=True)
    p.__enter__()
    advance = p.advance
    for _ in range(N_HOT // 64):
        advance(64)
    p.__exit__(None, None, None)


def train_multitask() -> None:
    with barflow.Progress() as p:
        ids = [p.add_task(total=N_MULTI, desc=f"task {i}") for i in range(4)]
        for _ in range(N_MULTI):
            for tid in ids:
                p.update(tid, 1)


def train_metadata_churn() -> None:
    with barflow.Progress(total=N_DISP, desc="init") as p:
        tick = p.tick
        set_description = p.set_description
        for i in range(N_DISP):
            tick()
            if i % 1000 == 0:
                set_description(f"phase {i:06d}")


def main() -> None:
    t0 = time.perf_counter()
    print("pgo_train: track (no display)...", flush=True)
    train_track_nodisplay()
    print("pgo_train: track (display on)...", flush=True)
    train_track_display()
    print("pgo_train: manual tick loop...", flush=True)
    train_tick()
    print("pgo_train: advance(64)...", flush=True)
    train_advance_n()
    print("pgo_train: multitask...", flush=True)
    train_multitask()
    print("pgo_train: metadata churn...", flush=True)
    train_metadata_churn()
    dt = time.perf_counter() - t0
    print(f"pgo_train: done in {dt:.1f}s", flush=True)


if __name__ == "__main__":
    main()

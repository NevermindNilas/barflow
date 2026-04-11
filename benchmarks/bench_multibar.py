"""Four concurrent 250k-iter tasks in a single Progress — exercises the multi-task hot path.

Single-task throughput is easy; multi-task is where a library's task
table, locking discipline, and render batching actually get tested.
Barflow's `update(task_id, n)` takes the render mutex for the vector
lookup on each call, while `tick()`/`advance()` on task 0 is lock-free.
tqdm and rich both support multi-bar via different idioms — we use the
most natural per lib rather than forcing a one-size-fits-all shape.

Usage:
    python benchmarks/bench_multibar.py
    python benchmarks/bench_multibar.py --per-task 500000 --runs 5
"""

from __future__ import annotations

import argparse
import gc
import io
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# The four tasks are driven round-robin from a single thread — we are
# measuring the library's multi-task dispatch, not Python threading.
# Total work per trial = 4 * per_task iterations.
#
# Each lib runs in a subprocess so import and render-thread state
# cannot leak across trials.

WORKER_TEMPLATE = r"""
import gc, io, json, statistics, sys, time
sys.path.insert(0, {src!r})

PER_TASK = {per_task}
RUNS = {runs}
TOTAL = PER_TASK * 4

def run_barflow():
    import barflow
    sink = io.StringIO()
    old = sys.stdout
    sys.stdout = sink
    try:
        gc.collect()
        p = barflow.Progress(total=PER_TASK, desc="t0")
        p.__enter__()
        t1 = p.add_task(total=PER_TASK, desc="t1")
        t2 = p.add_task(total=PER_TASK, desc="t2")
        t3 = p.add_task(total=PER_TASK, desc="t3")
        update = p.update
        t0_start = time.perf_counter()
        for _ in range(PER_TASK):
            update(0, 1)
            update(t1, 1)
            update(t2, 1)
            update(t3, 1)
        dt = time.perf_counter() - t0_start
        p.__exit__(None, None, None)
    finally:
        sys.stdout = old
    return dt

def run_tqdm():
    from tqdm import tqdm
    sink = io.StringIO()
    gc.collect()
    # tqdm's natural multi-bar idiom: one tqdm per task, stacked via
    # position=. Matched-cadence with barflow.
    bars = [
        tqdm(total=PER_TASK, file=sink, position=i,
             mininterval=0.05, desc=f"t{{i}}")
        for i in range(4)
    ]
    t0 = time.perf_counter()
    for _ in range(PER_TASK):
        for b in bars:
            b.update(1)
    dt = time.perf_counter() - t0
    for b in bars:
        b.close()
    return dt

def run_rich():
    from rich.console import Console
    from rich.progress import Progress
    sink = io.StringIO()
    gc.collect()
    console = Console(file=sink, force_terminal=True)
    with Progress(console=console, transient=False) as p:
        tasks = [p.add_task(f"t{{i}}", total=PER_TASK) for i in range(4)]
        advance = p.advance
        t0 = time.perf_counter()
        for _ in range(PER_TASK):
            for tid in tasks:
                advance(tid, 1)
        dt = time.perf_counter() - t0
    return dt

def run_alive():
    # alive_progress has no clean multi-bar idiom — its bars are
    # designed to be singletons. Nested `with alive_bar(...)` is
    # sequential, not concurrent. Skip.
    raise ImportError("alive_progress does not support multi-task cleanly")

LIB = {lib!r}
runner = {{
    "barflow": run_barflow,
    "tqdm": run_tqdm,
    "rich": run_rich,
    "alive-progress": run_alive,
}}[LIB]

try:
    samples = []
    for _ in range(RUNS):
        samples.append(runner())
except ImportError as exc:
    print(json.dumps({{"skipped": LIB, "reason": str(exc)}}))
    sys.exit(0)

best = min(samples)
print(json.dumps({{
    "lib": LIB,
    "per_task": PER_TASK,
    "total_iters": TOTAL,
    "best_sec": best,
    "median_sec": statistics.median(samples),
    "it_per_s": TOTAL / best,
}}))
"""


def run_worker(lib: str, per_task: int, runs: int) -> dict | None:
    snippet = WORKER_TEMPLATE.format(
        src=str(SRC), per_task=per_task, runs=runs, lib=lib
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-c", snippet],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    if proc.returncode != 0:
        print(f"  {lib:16s} worker exited {proc.returncode}")
        if proc.stderr.strip():
            print(textwrap.indent(proc.stderr.strip(), "    "))
        return None
    last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    try:
        return json.loads(last)
    except Exception:
        print(f"  {lib:16s} could not parse worker output: {last!r}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-task", type=int, default=250_000)
    ap.add_argument("--runs", type=int, default=5)
    args = ap.parse_args()

    libs = ["barflow", "tqdm", "rich", "alive-progress"]
    total = args.per_task * 4

    print(f"=== Multi-bar: 4 concurrent tasks x {args.per_task:,} = {total:,} total iters ===\n")
    header = (
        f"  {'lib':16s} "
        f"{'wall time':>12s} "
        f"{'aggregate':>14s}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))

    for lib in libs:
        gc.collect()
        r = run_worker(lib, args.per_task, args.runs)
        if r is None:
            continue
        if "skipped" in r:
            print(f"  {lib:16s} skipped: {r.get('reason', 'ImportError')}")
            continue
        print(
            f"  {lib:16s} "
            f"{r['best_sec']*1000:>9.1f} ms "
            f"{r['it_per_s']/1e6:>10.2f} M it/s"
        )

    print()
    print("Aggregate it/s = total_iters / best_wall_time across all four tasks.")


if __name__ == "__main__":
    main()

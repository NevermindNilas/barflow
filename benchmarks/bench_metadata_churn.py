"""Description/postfix update every 1000 iters over 1M total — tests set_description/set_postfix hot-path cost.

Real-world progress bars get their metadata mutated constantly: the
description rotates through file names, the postfix shows the current
loss / batch / hit-rate. A library that makes `set_description` cheap
wins on real workloads even if its pure-tick throughput is identical
to a competitor that makes it expensive.

Barflow exposes `Progress.set_description(str)` (task 0) and
`Progress.set_task_description(task_id, str)` for multi-task bars —
both update under the render mutex without touching the lock-free
tick hot path.

Usage:
    python benchmarks/bench_metadata_churn.py
    python benchmarks/bench_metadata_churn.py --n 500000 --churn-every 500
"""

from __future__ import annotations

import argparse
import gc
import io
import json
import os
import statistics
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# Description strings are pre-generated so the benchmark doesn't pay
# for string formatting on the hot path — we're measuring the cost of
# the set_description call itself, not f-string compilation.

WORKER_TEMPLATE = r"""
import gc, io, json, statistics, sys, time
sys.path.insert(0, {src!r})

N = {n}
CHURN_EVERY = {churn_every}
RUNS = {runs}
LIB = {lib!r}

# Pre-generate ~40-char description strings so the hot path only pays
# for the set_description call itself, not f-string formatting.
DESCS = [
    (f"phase {{i:04d}} processing batch {{i*7 % 99999:05d}}")[:40]
    for i in range(N // CHURN_EVERY + 2)
]

def run_barflow():
    import barflow
    gc.collect()
    with barflow.Progress(total=N, desc="init") as p:
        tick = p.tick
        set_description = p.set_description
        t0 = time.perf_counter()
        churn_idx = 0
        for i in range(N):
            tick()
            if i % CHURN_EVERY == 0:
                set_description(DESCS[churn_idx])
                churn_idx += 1
        dt = time.perf_counter() - t0
    return dt

def run_tqdm():
    from tqdm import tqdm
    sink = io.StringIO()
    gc.collect()
    bar = tqdm(total=N, file=sink, mininterval=0.05)
    update = bar.update
    set_description = bar.set_description_str
    set_postfix = bar.set_postfix_str
    t0 = time.perf_counter()
    churn_idx = 0
    for i in range(N):
        update(1)
        if i % CHURN_EVERY == 0:
            set_description(DESCS[churn_idx])
            set_postfix(DESCS[churn_idx])
            churn_idx += 1
    dt = time.perf_counter() - t0
    bar.close()
    return dt

def run_rich():
    from rich.console import Console
    from rich.progress import Progress
    sink = io.StringIO()
    gc.collect()
    console = Console(file=sink, force_terminal=True)
    with Progress(console=console, transient=False) as p:
        task = p.add_task("init", total=N)
        advance = p.advance
        update_task = p.update
        t0 = time.perf_counter()
        churn_idx = 0
        for i in range(N):
            advance(task, 1)
            if i % CHURN_EVERY == 0:
                update_task(task, description=DESCS[churn_idx])
                churn_idx += 1
        dt = time.perf_counter() - t0
    return dt

def run_alive():
    from alive_progress import alive_bar
    sink = io.StringIO()
    gc.collect()
    t0 = time.perf_counter()
    with alive_bar(N, file=sink, force_tty=True) as bar:
        churn_idx = 0
        for i in range(N):
            bar()
            if i % CHURN_EVERY == 0:
                bar.title = DESCS[churn_idx]
                churn_idx += 1
    dt = time.perf_counter() - t0
    return dt

runner = {{
    "barflow": run_barflow,
    "tqdm": run_tqdm,
    "rich": run_rich,
    "alive-progress": run_alive,
}}[LIB]

try:
    samples = [runner() for _ in range(RUNS)]
except ImportError as exc:
    print(json.dumps({{"skipped": LIB, "reason": str(exc)}}))
    sys.exit(0)

best = min(samples)
print(json.dumps({{
    "lib": LIB,
    "n": N,
    "churn_every": CHURN_EVERY,
    "best_sec": best,
    "median_sec": statistics.median(samples),
    "it_per_s": N / best,
}}))
"""


def run_worker(lib: str, n: int, churn_every: int, runs: int) -> dict | None:
    snippet = WORKER_TEMPLATE.format(
        src=str(SRC), n=n, churn_every=churn_every, runs=runs, lib=lib
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
    ap.add_argument("--n", type=int, default=1_000_000)
    ap.add_argument("--churn-every", type=int, default=1000)
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()

    libs = ["barflow", "tqdm", "rich", "alive-progress"]

    print(
        f"=== Metadata churn: N={args.n:,}, set_description every "
        f"{args.churn_every} iters ===\n"
    )
    header = f"  {'lib':16s} {'wall time':>12s} {'it/s':>14s}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for lib in libs:
        gc.collect()
        r = run_worker(lib, args.n, args.churn_every, args.runs)
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
    print("barflow exposes set_description via a brief render_mtx acquire;")
    print("the tick hot path remains lock-free. Only the 1/CHURN_EVERY")
    print("metadata updates touch the mutex.")


if __name__ == "__main__":
    main()

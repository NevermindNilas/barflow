"""Time from Progress.__enter__ to first byte in the sink — measures UI responsiveness for short jobs.

Throughput is irrelevant if the user sees a blank terminal for 80ms
before the bar appears. This axis matters most for short-lived jobs
(tests, CLI tools doing a few dozen steps) where the whole run might
finish before a slow library has even rendered its first frame.

BarFlow runs its renderer on a background thread, so its first frame
waits for an OS-level thread spin-up and a condvar wake. That's fast in
absolute terms (sub-ms on most boxes) but WILL lose to tqdm's synchronous
render path, which writes the first frame in the same call as the first
`update`. Report honestly.

Usage:
    python benchmarks/bench_first_frame.py
    python benchmarks/bench_first_frame.py --runs 100
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
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# Subprocess-isolated worker. For each of `runs` trials, it creates a
# fresh Progress, ticks once (forcing the renderer to do real work),
# and polls the sink in a tight loop until it contains at least one
# byte. We return perf_counter_ns() elapsed from the instant BEFORE
# __enter__() to the instant the first byte is observed.

WORKER_TEMPLATE = r"""
import gc, io, json, os, statistics, sys, time
sys.path.insert(0, {src!r})

RUNS = {runs}
POLL_BUDGET_NS = 500_000_000  # 500ms hard cap per trial

def wait_first_byte_sink(sink, t0, budget_ns):
    deadline = t0 + budget_ns
    while True:
        try:
            v = sink.getvalue()
        except Exception:
            v = ""
        if v:
            return time.perf_counter_ns() - t0
        if time.perf_counter_ns() > deadline:
            return -1

def wait_first_byte_fd(rfd, t0, budget_ns):
    # Non-blocking read on an OS pipe read-end. Used for barflow, which
    # writes directly to the stderr fd and bypasses sys.stdout entirely.
    deadline = t0 + budget_ns
    while True:
        try:
            chunk = os.read(rfd, 4096)
        except BlockingIOError:
            chunk = b""
        except OSError:
            chunk = b""
        if chunk:
            return time.perf_counter_ns() - t0
        if time.perf_counter_ns() > deadline:
            return -1

def trial_barflow():
    import barflow
    # barflow's C core writes via fwrite(stderr) / WriteConsoleW,
    # bypassing Python's sys.stdout entirely. Redirect the real fd 2
    # to a pipe and poll the read end.
    rfd, wfd = os.pipe()
    # Make the read end non-blocking so wait_first_byte_fd can spin
    # instead of stalling on read().
    if hasattr(os, "set_blocking"):
        os.set_blocking(rfd, False)
    saved_stderr = os.dup(2)
    os.dup2(wfd, 2)
    os.close(wfd)
    try:
        gc.collect()
        t0 = time.perf_counter_ns()
        p = barflow.Progress(total=1000)
        p.__enter__()
        p.tick()
        dt = wait_first_byte_fd(rfd, t0, POLL_BUDGET_NS)
        p.__exit__(None, None, None)
    finally:
        os.dup2(saved_stderr, 2)
        os.close(saved_stderr)
        try:
            os.close(rfd)
        except OSError:
            pass
    return dt

def trial_tqdm():
    from tqdm import tqdm
    sink = io.StringIO()
    gc.collect()
    t0 = time.perf_counter_ns()
    # tqdm renders the first frame synchronously on the first update
    # when mininterval=0 and miniters=1.
    bar = tqdm(total=1000, file=sink, mininterval=0.0, miniters=1)
    bar.update(1)
    bar.refresh()
    dt = wait_first_byte_sink(sink, t0, POLL_BUDGET_NS)
    bar.close()
    return dt

def trial_rich():
    from rich.console import Console
    from rich.progress import Progress
    sink = io.StringIO()
    gc.collect()
    console = Console(file=sink, force_terminal=True, width=80)
    t0 = time.perf_counter_ns()
    p = Progress(console=console, transient=False, refresh_per_second=1000)
    p.__enter__()
    task = p.add_task("bench", total=1000)
    p.advance(task, 1)
    p.refresh()
    dt = wait_first_byte_sink(sink, t0, POLL_BUDGET_NS)
    p.__exit__(None, None, None)
    return dt

LIB = {lib!r}
try:
    samples = []
    fn = {{"barflow": trial_barflow, "tqdm": trial_tqdm, "rich": trial_rich}}[LIB]
    for _ in range(RUNS):
        samples.append(fn())
except ImportError as exc:
    print(json.dumps({{"skipped": LIB, "reason": str(exc)}}))
    sys.exit(0)

samples = [s for s in samples if s >= 0]
if not samples:
    print(json.dumps({{"lib": LIB, "error": "no successful trials (budget exhausted)"}}))
    sys.exit(0)

samples.sort()
print(json.dumps({{
    "lib": LIB,
    "runs": len(samples),
    "median_ns": statistics.median(samples),
    "min_ns": samples[0],
    "max_ns": samples[-1],
    "p90_ns": samples[int(round(0.90 * (len(samples) - 1)))],
}}))
"""


def run_worker(lib: str, runs: int) -> dict | None:
    snippet = WORKER_TEMPLATE.format(src=str(SRC), runs=runs, lib=lib)
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
        print(f"  {lib:10s} worker exited {proc.returncode}")
        if proc.stderr.strip():
            print(textwrap.indent(proc.stderr.strip(), "    "))
        return None
    last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    try:
        return json.loads(last)
    except Exception:
        print(f"  {lib:10s} could not parse worker output: {last!r}")
        return None


def fmt_us(ns: float) -> str:
    if ns < 1_000:
        return f"{ns:7.0f} ns"
    if ns < 1_000_000:
        return f"{ns/1_000:7.1f} us"
    return f"{ns/1_000_000:7.2f} ms"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=50)
    args = ap.parse_args()

    libs = ["barflow", "tqdm", "rich"]
    print(f"=== First-frame latency (enter -> first byte in sink), runs={args.runs} ===\n")
    header = f"  {'lib':10s} {'median':>11s} {'min':>11s} {'p90':>11s} {'max':>11s}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for lib in libs:
        r = run_worker(lib, args.runs)
        if r is None:
            continue
        if "skipped" in r:
            print(f"  {lib:10s} skipped: {r.get('reason', 'ImportError')}")
            continue
        if "error" in r:
            print(f"  {lib:10s} error: {r['error']}")
            continue
        print(
            f"  {lib:10s} "
            f"{fmt_us(r['median_ns']):>11s} "
            f"{fmt_us(r['min_ns']):>11s} "
            f"{fmt_us(r['p90_ns']):>11s} "
            f"{fmt_us(r['max_ns']):>11s}"
        )

    print()
    print("Note: barflow uses a background render thread, so its first frame")
    print("pays a thread-wakeup cost that tqdm (synchronous render) does not.")
    print("This axis favors synchronous libraries for short-lived jobs.")


if __name__ == "__main__":
    main()

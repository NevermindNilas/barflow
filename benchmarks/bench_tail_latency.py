"""Per-iteration latency distribution (p50/p90/p99/p99.9/max) — exposes render-thread jitter that mean throughput hides.

Mean it/s tells you how fast a library is on average, but hides WHERE
the work happens. A library that spends 30ns per tick but stalls 10ms
every second on a render looks identical in mean throughput to one that
spends 40ns per tick with perfect smoothness — yet the first will jank
visibly in an interactive terminal and stall any downstream consumer
that was counting on steady progress. This benchmark records the gap
between successive ticks and reports the tail, so you can see the
stalls directly.

Usage:
    python benchmarks/bench_tail_latency.py
    python benchmarks/bench_tail_latency.py --n 200000
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
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# Each worker is run in a fresh subprocess so import state, GC heap, and
# render-thread history from earlier libs can't leak into later ones.
# The worker collects perf_counter_ns deltas between consecutive yields
# of `track(range(n))` (or the closest equivalent), writes them to a
# temp file, and prints a JSON summary on stdout.

WORKER_TEMPLATE = r"""
import gc, io, json, os, sys, time
sys.path.insert(0, {src!r})

N = {n}

def percentile(sorted_arr, q):
    if not sorted_arr:
        return 0
    # Nearest-rank, no interpolation — we have plenty of samples and
    # interpolation would lie about the true tail.
    k = int(round((q / 100.0) * (len(sorted_arr) - 1)))
    return sorted_arr[k]

def summarize(deltas):
    deltas.sort()
    return {{
        "count":  len(deltas),
        "p50":    percentile(deltas, 50),
        "p90":    percentile(deltas, 90),
        "p99":    percentile(deltas, 99),
        "p99_9":  percentile(deltas, 99.9),
        "max":    deltas[-1] if deltas else 0,
        "mean_ns": sum(deltas) / len(deltas) if deltas else 0.0,
    }}

def run_barflow():
    import barflow
    sink = io.StringIO()
    gc.collect()
    deltas = [0] * (N - 1)
    it = barflow.track(range(N), total=N)
    prev = time.perf_counter_ns()
    i = 0
    # First element consumed outside the loop so the "prev" anchor is
    # AFTER the first yield — we measure inter-iteration gap only.
    next(it)
    for _ in it:
        now = time.perf_counter_ns()
        deltas[i] = now - prev
        prev = now
        i += 1
    return summarize(deltas[:i])

def run_tqdm():
    from tqdm import tqdm
    sink = io.StringIO()
    gc.collect()
    deltas = [0] * (N - 1)
    # Matched-cadence with barflow (see bench.py for rationale).
    it = iter(tqdm(range(N), file=sink, mininterval=0.05, total=N))
    next(it)
    prev = time.perf_counter_ns()
    i = 0
    for _ in it:
        now = time.perf_counter_ns()
        deltas[i] = now - prev
        prev = now
        i += 1
    return summarize(deltas[:i])

def run_rich():
    from rich.console import Console
    from rich.progress import Progress
    sink = io.StringIO()
    gc.collect()
    console = Console(file=sink, force_terminal=True)
    deltas = [0] * (N - 1)
    with Progress(console=console, transient=False) as p:
        task = p.add_task("bench", total=N)
        advance = p.advance
        # Warm up one tick so the first rendered frame's cost doesn't
        # dominate the p99.9 sample.
        advance(task, 1)
        prev = time.perf_counter_ns()
        for i in range(N - 1):
            advance(task, 1)
            now = time.perf_counter_ns()
            deltas[i] = now - prev
            prev = now
    return summarize(deltas)

def run_alive():
    from alive_progress import alive_bar
    sink = io.StringIO()
    gc.collect()
    deltas = [0] * (N - 1)
    with alive_bar(N, file=sink, force_tty=True) as bar:
        bar()
        prev = time.perf_counter_ns()
        for i in range(N - 1):
            bar()
            now = time.perf_counter_ns()
            deltas[i] = now - prev
            prev = now
    return summarize(deltas)

LIB = {lib!r}
try:
    if LIB == "barflow":
        r = run_barflow()
    elif LIB == "tqdm":
        r = run_tqdm()
    elif LIB == "rich":
        r = run_rich()
    elif LIB == "alive-progress":
        r = run_alive()
    else:
        raise ValueError(LIB)
except ImportError as exc:
    print(json.dumps({{"skipped": LIB, "reason": str(exc)}}))
    sys.exit(0)
print(json.dumps({{"lib": LIB, "stats": r}}))
"""


def run_worker(lib: str, n: int) -> dict | None:
    snippet = WORKER_TEMPLATE.format(src=str(SRC), n=n, lib=lib)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        proc = subprocess.run(
            [sys.executable, "-c", snippet],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
    except Exception as exc:
        print(f"  {lib:16s} worker launch failed: {exc}")
        return None
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


def fmt_ns(ns: float) -> str:
    if ns < 1_000:
        return f"{ns:7.0f} ns"
    if ns < 1_000_000:
        return f"{ns/1_000:7.2f} us"
    if ns < 1_000_000_000:
        return f"{ns/1_000_000:7.2f} ms"
    return f"{ns/1_000_000_000:7.2f} s "


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100_000,
                    help="iterations per library (default 100k)")
    args = ap.parse_args()

    libs = ["barflow", "tqdm", "rich", "alive-progress"]
    results: dict[str, dict] = {}

    print(f"=== Per-iter tail latency, N={args.n:,} (display ON, sink=StringIO) ===\n")
    header = f"  {'lib':16s} {'p50':>11s} {'p90':>11s} {'p99':>11s} {'p99.9':>11s} {'max':>11s} {'mean':>11s}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for lib in libs:
        gc.collect()
        r = run_worker(lib, args.n)
        if r is None:
            continue
        if "skipped" in r:
            print(f"  {lib:16s} skipped: {r.get('reason', 'ImportError')}")
            continue
        s = r["stats"]
        results[lib] = s
        print(
            f"  {lib:16s} "
            f"{fmt_ns(s['p50']):>11s} "
            f"{fmt_ns(s['p90']):>11s} "
            f"{fmt_ns(s['p99']):>11s} "
            f"{fmt_ns(s['p99_9']):>11s} "
            f"{fmt_ns(s['max']):>11s} "
            f"{fmt_ns(s['mean_ns']):>11s}"
        )

    print()
    print("Tail spikes (p99.9 and max) above ~100us usually indicate render-thread")
    print("work happening on the hot path. p50 is the true per-tick cost.")


if __name__ == "__main__":
    main()

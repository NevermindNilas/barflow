"""Peak Python heap (tracemalloc) and post-import RSS (psutil, if available) — memory cost of a 1M-iter run.

Throughput benchmarks say nothing about whether a library quietly
accumulates a per-tick list, dict, or closure cell over the course of
a long run. tracemalloc snapshots before/after a 1M-iter run expose
that directly. RSS-at-import measures the fixed cost of having the
library loaded at all — relevant for short-lived CLI tools where the
import is most of the wall time.

psutil is optional: if it isn't installed, RSS is reported as "—"
and the tracemalloc numbers still work.

Usage:
    python benchmarks/bench_memory.py
    python benchmarks/bench_memory.py --n 500000
"""

from __future__ import annotations

import argparse
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


# Subprocess-isolated so each library gets its own fresh heap. We
# capture RSS at three points:
#   1. before importing anything library-specific (interpreter baseline)
#   2. right after the import (RSS delta = fixed import cost)
#   3. after the 1M-iter run (tracemalloc peak = hot-path allocations)

WORKER_TEMPLATE = r"""
import gc, io, json, os, sys, tracemalloc
sys.path.insert(0, {src!r})

N = {n}
LIB = {lib!r}

try:
    import psutil
    _proc = psutil.Process()
    def rss():
        return _proc.memory_info().rss
    HAS_PSUTIL = True
except ImportError:
    def rss():
        return 0
    HAS_PSUTIL = False

gc.collect()
rss_baseline = rss()

try:
    if LIB == "barflow":
        import barflow
    elif LIB == "tqdm":
        from tqdm import tqdm
    elif LIB == "rich":
        from rich.progress import Progress
        from rich.console import Console
    elif LIB == "alive-progress":
        from alive_progress import alive_bar
    else:
        raise ValueError(LIB)
except ImportError as exc:
    print(json.dumps({{"skipped": LIB, "reason": str(exc)}}))
    sys.exit(0)

gc.collect()
rss_after_import = rss()

sink = io.StringIO()

def run_barflow():
    for _ in barflow.track(range(N), total=N):
        pass

def run_tqdm():
    # Matched-cadence with barflow (see bench.py).
    for _ in tqdm(range(N), file=sink, mininterval=0.05, total=N):
        pass

def run_rich():
    console = Console(file=sink, force_terminal=True)
    with Progress(console=console, transient=False) as p:
        task = p.add_task("bench", total=N)
        advance = p.advance
        for _ in range(N):
            advance(task, 1)

def run_alive():
    with alive_bar(N, file=sink, force_tty=True) as bar:
        for _ in range(N):
            bar()

runner = {{
    "barflow": run_barflow,
    "tqdm": run_tqdm,
    "rich": run_rich,
    "alive-progress": run_alive,
}}[LIB]

gc.collect()
tracemalloc.start()
runner()
current, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()

gc.collect()
rss_after_run = rss()

print(json.dumps({{
    "lib": LIB,
    "n": N,
    "has_psutil": HAS_PSUTIL,
    "rss_baseline": rss_baseline,
    "rss_after_import": rss_after_import,
    "rss_after_run": rss_after_run,
    "tm_peak": peak,
    "tm_current_end": current,
}}))
"""


def run_worker(lib: str, n: int) -> dict | None:
    snippet = WORKER_TEMPLATE.format(src=str(SRC), n=n, lib=lib)
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


def fmt_bytes(b: float) -> str:
    if b < 1024:
        return f"{b:7.0f} B "
    if b < 1024 ** 2:
        return f"{b/1024:7.1f} KB"
    return f"{b/1024**2:7.2f} MB"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1_000_000)
    args = ap.parse_args()

    libs = ["barflow", "tqdm", "rich", "alive-progress"]

    print(f"=== Memory: tracemalloc peak + RSS deltas, N={args.n:,} ===\n")
    header = (
        f"  {'lib':16s} "
        f"{'tm peak':>11s} "
        f"{'rss import':>12s} "
        f"{'rss run':>11s}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))

    any_psutil = False
    for lib in libs:
        r = run_worker(lib, args.n)
        if r is None:
            continue
        if "skipped" in r:
            print(f"  {lib:16s} skipped: {r.get('reason', 'ImportError')}")
            continue
        if r.get("has_psutil"):
            any_psutil = True
            rss_import = r["rss_after_import"] - r["rss_baseline"]
            rss_run = r["rss_after_run"] - r["rss_after_import"]
            rss_import_s = fmt_bytes(rss_import)
            rss_run_s = fmt_bytes(rss_run)
        else:
            rss_import_s = "         —"
            rss_run_s = "        —"
        print(
            f"  {lib:16s} "
            f"{fmt_bytes(r['tm_peak']):>11s} "
            f"{rss_import_s:>12s} "
            f"{rss_run_s:>11s}"
        )

    print()
    if not any_psutil:
        print("psutil not installed in any worker: RSS columns are placeholders.")
        print("Install psutil to enable post-import / post-run RSS deltas.")
    print("tm peak = tracemalloc peak (Python heap only; does not include C buffers).")


if __name__ == "__main__":
    main()

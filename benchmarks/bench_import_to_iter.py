"""Benchmark: total ms from zero to first iteration body.

Measures the *end-to-end* cost a user actually pays:
    1. import the library
    2. construct a progress bar around a range
    3. enter the first iteration

All three phases run inside a subprocess so the import is genuinely cold.
The subprocess prints a single perf_counter_ns timestamp; the driver
subtracts the interpreter-startup baseline to isolate library cost.

Usage:
    python benchmarks/bench_import_to_iter.py
    python benchmarks/bench_import_to_iter.py --runs 21
"""

from __future__ import annotations

import argparse
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"

# ---------- snippets ----------------------------------------------------------
# Each snippet must print exactly ONE integer: perf_counter_ns elapsed from
# the top of the script to the moment the first iteration body executes.

SNIPPETS: dict[str, str] = {
    "rich": """\
import time, sys, os
_t0 = time.perf_counter_ns()
from rich.console import Console
from rich.progress import Progress
import io
_sink = io.StringIO()
_console = Console(file=_sink, force_terminal=True)
with Progress(console=_console, transient=True) as _p:
    _task = _p.add_task("work", total=100)
    for _i in range(100):
        # === first iteration body reached ===
        _elapsed = time.perf_counter_ns() - _t0
        break
# print outside the context manager so rich doesn't capture it
os.write(1, (str(_elapsed) + "\\n").encode())
""",
    "tqdm": """\
import time, os
_t0 = time.perf_counter_ns()
from tqdm import tqdm
import io
_sink = io.StringIO()
for _i in tqdm(range(100), file=_sink, total=100):
    _elapsed = time.perf_counter_ns() - _t0
    break
os.write(1, (str(_elapsed) + "\\n").encode())
""",
    "barflow": """\
import time, sys, os
sys.path.insert(0, {src!r})
_t0 = time.perf_counter_ns()
# redirect fd 2 so the C renderer doesn't write to console
_devnull = os.open(os.devnull, os.O_WRONLY)
_saved = os.dup(2)
os.dup2(_devnull, 2)
from barflow import track
for _i in track(range(100), total=100):
    _elapsed = time.perf_counter_ns() - _t0
    break
os.dup2(_saved, 2)
os.close(_saved)
os.close(_devnull)
os.write(1, (str(_elapsed) + "\\n").encode())
""",
    "alive-progress": """\
import time, os
_t0 = time.perf_counter_ns()
from alive_progress import alive_bar
import io
_sink = io.StringIO()
with alive_bar(100, file=_sink, force_tty=True) as _bar:
    for _i in range(100):
        _elapsed = time.perf_counter_ns() - _t0
        break
os.write(1, (str(_elapsed) + "\\n").encode())
""",
}


# ---------- driver ------------------------------------------------------------

def _run_snippet(label: str, snippet: str, runs: int) -> list[int]:
    """Return list of elapsed-ns values, one per successful run."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    results: list[int] = []
    for _ in range(runs):
        proc = subprocess.run(
            [sys.executable, "-c", snippet],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            continue
        line = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else ""
        try:
            results.append(int(line))
        except ValueError:
            pass
    return results


def _baseline(runs: int) -> float:
    """Median wall-ns of a bare `python -c pass` — interpreter startup only."""
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    times: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        subprocess.run(
            [sys.executable, "-c", "pass"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        times.append(time.perf_counter() - t0)
    return statistics.median(times) * 1e9  # -> ns


def main() -> None:
    ap = argparse.ArgumentParser(description="Import-to-first-iteration benchmark")
    ap.add_argument("--runs", type=int, default=11,
                    help="trials per library (default 11)")
    args = ap.parse_args()

    print(f"=== Import -> show bar -> first iteration (runs={args.runs}) ===")
    print(f"    Python {sys.version}")
    print()

    # The snippet already measures elapsed time internally (perf_counter_ns),
    # so it captures import + construction + first iter. No baseline subtraction
    # needed — the timer starts AFTER the interpreter is already running.

    header = f"  {'library':<18s} {'median':>10s} {'min':>10s} {'p90':>10s} {'max':>10s}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for label, snippet in SNIPPETS.items():
        if label == "barflow":
            snippet = snippet.format(src=str(SRC))
        samples = _run_snippet(label, snippet, args.runs)
        if not samples:
            print(f"  {label:<18s} {'SKIP (not installed or error)':>10s}")
            continue
        samples.sort()
        median = statistics.median(samples)
        mn = samples[0]
        p90 = samples[int(round(0.90 * (len(samples) - 1)))]
        mx = samples[-1]
        print(
            f"  {label:<18s} "
            f"{median / 1e6:>9.1f}ms "
            f"{mn / 1e6:>9.1f}ms "
            f"{p90 / 1e6:>9.1f}ms "
            f"{mx / 1e6:>9.1f}ms"
        )

    print()
    print("Timer starts AFTER interpreter boot (inside the subprocess).")
    print("Measures: import lib + construct progress bar + reach first iteration body.")
    print()
    print("Lower is better.")


if __name__ == "__main__":
    main()

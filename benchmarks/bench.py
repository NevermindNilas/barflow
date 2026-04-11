"""Benchmark harness — BarFlow vs tqdm vs rich vs alive-progress.

Measures:
    1. Import startup time (subprocess-isolated, cold-ish)
    2. Peak it/s on a no-op range loop (disabled display where supported,
       so we measure pure hot-path cost without console I/O noise)
    3. Per-iteration overhead vs a bare for-loop baseline
    4. Peak it/s with display enabled (redirected to a buffer) — reflects
       real-world cost including the render thread

Usage:
    python benchmarks/bench.py               # all libs, default N
    python benchmarks/bench.py --n 5000000   # custom N

Notes:
    - Tests for barflow are run with PYTHONPATH=src (managed by the
      caller) OR with the package installed. The harness appends "src" to
      sys.path as a fallback.
    - All libraries are driven via their "wrap an iterable" API where one
      exists, so the comparison is apples-to-apples.
"""

from __future__ import annotations

import argparse
import contextlib
import gc
import io
import os
import statistics
import subprocess
import sys
import textwrap
import time
from pathlib import Path


# ---------- OS-level stderr redirect ----------
#
# barflow's C core writes progress frames directly via WriteConsoleW (on
# Windows) or write(2) to fd 2 (on POSIX) — it bypasses `sys.stderr`
# entirely, so `contextlib.redirect_stderr` does nothing to it. To keep
# the live bars from bleeding into the bench output and to force the
# non-console `fwrite` path (which is the apples-to-apples comparison
# with tqdm/rich/alive writing into `io.StringIO`), we redirect at the
# OS level: `os.dup2` reassigns CRT fd 2, and on Windows we also call
# `SetStdHandle(STD_ERROR_HANDLE, ...)` so that `GetStdHandle()` at
# `Progress` construction time sees the replaced handle. The redirect
# must be active *before* `Progress()` is instantiated because
# `init_console()` caches the handle once.

@contextlib.contextmanager
def _os_redirect_stderr_to_devnull():
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_fd = os.dup(2)
    saved_handle = None
    kernel32 = None
    STD_ERROR_HANDLE = -12
    try:
        os.dup2(devnull_fd, 2)
        if sys.platform == "win32":
            import ctypes
            import msvcrt
            kernel32 = ctypes.windll.kernel32
            kernel32.GetStdHandle.restype = ctypes.c_void_p
            kernel32.SetStdHandle.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
            saved_handle = kernel32.GetStdHandle(ctypes.c_uint32(STD_ERROR_HANDLE))
            new_handle = msvcrt.get_osfhandle(devnull_fd)
            kernel32.SetStdHandle(ctypes.c_uint32(STD_ERROR_HANDLE),
                                  ctypes.c_void_p(new_handle))
        yield
    finally:
        if kernel32 is not None and saved_handle is not None:
            kernel32.SetStdHandle(ctypes.c_uint32(STD_ERROR_HANDLE),
                                  ctypes.c_void_p(saved_handle))
        os.dup2(saved_fd, 2)
        os.close(saved_fd)
        os.close(devnull_fd)

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ---------- Startup time (subprocess) ----------

IMPORT_SNIPPETS = {
    "barflow": "from barflow import track",
    "tqdm":       "from tqdm import tqdm",
    "rich":       "from rich.progress import Progress",
    "alive":      "from alive_progress import alive_bar",
}


def bench_startup(label: str, snippet: str, runs: int = 11) -> float:
    """Median wall time (seconds) of `python -c "<snippet>"`, minus a bare-interpreter baseline."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    # Baseline: interpreter startup with no user imports.
    baseline_runs = []
    for _ in range(runs):
        t0 = time.perf_counter()
        subprocess.run(
            [sys.executable, "-c", "pass"],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=True,
        )
        baseline_runs.append(time.perf_counter() - t0)
    baseline = statistics.median(baseline_runs)

    runs_s = []
    for _ in range(runs):
        t0 = time.perf_counter()
        subprocess.run(
            [sys.executable, "-c", snippet],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=True,
        )
        runs_s.append(time.perf_counter() - t0)
    total = statistics.median(runs_s)
    return max(total - baseline, 0.0)


# ---------- Runtime: peak it/s and overhead ----------

def _drain(it):
    for _ in it:
        pass


def bench_barflow_display(n: int, sink) -> float:
    # `sink` is accepted for API symmetry with the other benches but
    # not used: barflow writes via the C core, not Python. We redirect
    # fd 2 to /dev/null for the duration so (a) the live bar doesn't
    # pollute the bench's own stdout and (b) the C core takes the
    # non-console fwrite branch, matching what tqdm/rich/alive do when
    # handed an `io.StringIO`.
    del sink
    import barflow
    with _os_redirect_stderr_to_devnull():
        gc.collect()
        t0 = time.perf_counter()
        for _ in barflow.track(range(n), total=n):
            pass
        return time.perf_counter() - t0


def bench_barflow_nodisplay(n: int) -> float:
    # `disable=True` skips the render thread entirely — pure hot-path cost.
    import barflow
    gc.collect()
    p = barflow.Progress(total=n, disable=True)
    p.__enter__()
    tick = p.tick
    t0 = time.perf_counter()
    for _ in range(n):
        tick()
    dt = time.perf_counter() - t0
    p.__exit__(None, None, None)
    return dt


def bench_barflow_tracker(n: int) -> float:
    """Fast path: Tracker + disabled renderer."""
    import barflow
    gc.collect()
    p = barflow.Progress(total=n, disable=True)
    p.__enter__()
    tracker = barflow.Tracker(iter(range(n)), p)
    t0 = time.perf_counter()
    for _ in tracker:
        pass
    dt = time.perf_counter() - t0
    return dt


def bench_barflow_iter(n: int) -> float:
    """Zero-source iteration: `for _ in progress:` uses FOR_ITER's direct
    tp_iternext dispatch, bypassing the vectorcall trampoline that
    `progress.tick()` has to pay on every call. Yields Py_None, which
    is immortal on 3.12+, so even STORE_FAST is refcount-free — this
    path can actually run faster than `for _ in range(n): pass` because
    range yields (cached) small ints that still cost a store cycle.
    """
    import barflow
    gc.collect()
    p = barflow.Progress(total=n, disable=True)
    p.__enter__()
    t0 = time.perf_counter()
    for _ in p:
        pass
    dt = time.perf_counter() - t0
    p.__exit__(None, None, None)
    return dt


def bench_tqdm_display(n: int, sink) -> float:
    # NOTE: mininterval=0.05 matches barflow's default min_interval=0.05.
    # tqdm's own out-of-box default is 0.10, so this is a MATCHED-CADENCE
    # comparison, not tqdm's shipped behavior. We pick matched cadence
    # because it isolates per-render work from render frequency —
    # otherwise tqdm would get a "free" 2x render-skip advantage purely
    # because its default polls half as often, which tells us nothing
    # about which render path is actually faster. Rerun with
    # mininterval=0.10 if you want the out-of-box number instead.
    from tqdm import tqdm
    gc.collect()
    t0 = time.perf_counter()
    for _ in tqdm(range(n), file=sink, mininterval=0.05, total=n):
        pass
    return time.perf_counter() - t0


def bench_tqdm_nodisplay(n: int) -> float:
    from tqdm import tqdm
    gc.collect()
    t0 = time.perf_counter()
    for _ in tqdm(range(n), disable=True):
        pass
    return time.perf_counter() - t0


def bench_rich_display(n: int, sink) -> float:
    from rich.console import Console
    from rich.progress import Progress
    gc.collect()
    console = Console(file=sink, force_terminal=True)
    t0 = time.perf_counter()
    with Progress(console=console, transient=False) as p:
        task = p.add_task("bench", total=n)
        advance = p.advance
        for _ in range(n):
            advance(task, 1)
    return time.perf_counter() - t0


def bench_rich_nodisplay(n: int) -> float:
    # Rich doesn't have a true "disable"; `disable=True` on Progress skips
    # rendering but advance() still runs through the dict + RLock + deque.
    from rich.progress import Progress
    gc.collect()
    t0 = time.perf_counter()
    with Progress(disable=True) as p:
        task = p.add_task("bench", total=n)
        advance = p.advance
        for _ in range(n):
            advance(task, 1)
    return time.perf_counter() - t0


def bench_alive_display(n: int, sink) -> float:
    from alive_progress import alive_bar
    gc.collect()
    t0 = time.perf_counter()
    with alive_bar(n, file=sink, force_tty=True) as bar:
        for _ in range(n):
            bar()
    return time.perf_counter() - t0


def bench_alive_nodisplay(n: int) -> float:
    from alive_progress import alive_bar
    gc.collect()
    t0 = time.perf_counter()
    with alive_bar(n, disable=True) as bar:
        for _ in range(n):
            bar()
    return time.perf_counter() - t0


def bench_baseline(n: int) -> float:
    gc.collect()
    t0 = time.perf_counter()
    for _ in range(n):
        pass
    return time.perf_counter() - t0


# ---------- CPU-time measurement ----------
#
# `time.process_time()` sums CPU time across all threads of the current
# process on every platform we target (Windows GetProcessTimes, Linux
# clock_gettime(CLOCK_PROCESS_CPUTIME_ID), macOS task_info). That lets
# us catch the cost of a background render thread that runs in parallel
# with the producer loop — pure wall time would hide it.

def _cpu_wall(fn, *args, **kwargs):
    gc.collect()
    cpu0 = time.process_time()
    w0 = time.perf_counter()
    fn(*args, **kwargs)
    w1 = time.perf_counter()
    cpu1 = time.process_time()
    return (w1 - w0, cpu1 - cpu0)


def cpu_baseline(n: int):
    def work():
        for _ in range(n):
            pass
    return _cpu_wall(work)


def cpu_barflow_display(n: int):
    import barflow
    def work():
        for _ in barflow.track(range(n), total=n):
            pass
    with _os_redirect_stderr_to_devnull():
        return _cpu_wall(work)


def cpu_barflow_nodisplay(n: int):
    import barflow
    def work():
        p = barflow.Progress(total=n, disable=True)
        p.__enter__()
        tracker = barflow.Tracker(iter(range(n)), p)
        for _ in tracker:
            pass
        p.__exit__(None, None, None)
    return _cpu_wall(work)


def cpu_tqdm_display(n: int):
    from tqdm import tqdm
    def work():
        for _ in tqdm(range(n), file=io.StringIO(), mininterval=0.05, total=n):
            pass
    return _cpu_wall(work)


def cpu_tqdm_nodisplay(n: int):
    from tqdm import tqdm
    def work():
        for _ in tqdm(range(n), disable=True):
            pass
    return _cpu_wall(work)


def cpu_rich_display(n: int):
    from rich.console import Console
    from rich.progress import Progress
    def work():
        console = Console(file=io.StringIO(), force_terminal=True)
        with Progress(console=console, transient=False) as p:
            task = p.add_task("bench", total=n)
            advance = p.advance
            for _ in range(n):
                advance(task, 1)
    return _cpu_wall(work)


def cpu_rich_nodisplay(n: int):
    from rich.progress import Progress
    def work():
        with Progress(disable=True) as p:
            task = p.add_task("bench", total=n)
            advance = p.advance
            for _ in range(n):
                advance(task, 1)
    return _cpu_wall(work)


def cpu_alive_display(n: int):
    from alive_progress import alive_bar
    def work():
        with alive_bar(n, file=io.StringIO(), force_tty=True) as bar:
            for _ in range(n):
                bar()
    return _cpu_wall(work)


def cpu_alive_nodisplay(n: int):
    from alive_progress import alive_bar
    def work():
        with alive_bar(n, disable=True) as bar:
            for _ in range(n):
                bar()
    return _cpu_wall(work)


# ---------- Runner ----------

def run_all(n: int, runs: int) -> dict:
    result = {"n": n, "runs": runs, "libs": {}}

    # Startup
    print("=== Import startup ===")
    print(f"  {'library':<16}  {'cold ms':>10}")
    print(f"  {'-'*16}  {'-'*10}")
    for label, snippet in IMPORT_SNIPPETS.items():
        try:
            s = bench_startup(label, snippet, runs=runs)
        except Exception as exc:
            print(f"  {label:<16}  ERROR: {exc}")
            continue
        print(f"  {label:<16}  {s * 1000:>10.2f}")
        result["libs"].setdefault(label, {})["startup_ms"] = s * 1000

    # Runtime baseline
    print("\n=== Bare for-loop baseline ===")
    base_times = [bench_baseline(n) for _ in range(runs)]
    base = min(base_times)
    print(f"  {'baseline':<16}  {n/base/1e6:>10.2f} M it/s   {base*1e9/n:>7.1f} ns/iter")
    result["baseline_sec"] = base
    result["baseline_ns_per_iter"] = base * 1e9 / n

    # Runtime "counter-only" hot path. Each lib is driven with its own
    # disable flag where one exists. Caveat: rich's `Progress(disable=True)`
    # skips rendering but still runs the full `advance()` accounting
    # path (dict lookup + RLock + deque), and alive-progress's
    # `disable=True` similarly doesn't short-circuit the bookkeeping.
    # So for those two, this bucket is "disabled-mode advance()", not
    # a true zero-work baseline. barflow-tick and barflow-track *do*
    # short-circuit at the C level when `disable=True`.
    print("\n=== Counter hot path (disabled mode; rich/alive still run advance()) ===")
    print(f"  {'variant':<16}  {'M it/s':>10}  {'ns/iter +base':>14}")
    print(f"  {'-'*16}  {'-'*10}  {'-'*14}")
    no_display_benches = [
        ("barflow-tick",    bench_barflow_nodisplay),
        ("barflow-track",   bench_barflow_tracker),
        ("barflow-iter",    bench_barflow_iter),
        ("tqdm",            bench_tqdm_nodisplay),
        ("rich",            bench_rich_nodisplay),
        ("alive-progress",  bench_alive_nodisplay),
    ]
    for label, fn in no_display_benches:
        try:
            samples = [fn(n) for _ in range(runs)]
            best = min(samples)
        except Exception as exc:
            print(f"  {label:<16}  ERROR: {exc}")
            continue
        rate = n / best
        overhead_ns = max(best - base, 0.0) * 1e9 / n
        print(f"  {label:<16}  {rate/1e6:>10.2f}  {overhead_ns:>14.1f}")
        key = label.split("-")[0] if label.startswith("barflow") else label
        slot = result["libs"].setdefault(key if key != "barflow" else "barflow", {})
        slot.setdefault("nodisplay", {})[label] = {
            "best_sec": best,
            "it_per_s": rate,
            "ns_per_iter_over_baseline": overhead_ns,
        }

    # Runtime display-on (writes to /dev/null sink)
    print("\n=== Display ON (sink = io.StringIO / devnull for barflow) ===")
    print(f"  {'library':<16}  {'M it/s':>10}")
    print(f"  {'-'*16}  {'-'*10}")
    display_benches = [
        ("barflow",        bench_barflow_display),
        ("tqdm",           bench_tqdm_display),
        ("rich",           bench_rich_display),
        ("alive-progress", bench_alive_display),
    ]
    for label, fn in display_benches:
        try:
            samples = []
            for _ in range(runs):
                sink = io.StringIO()
                samples.append(fn(n, sink))
            best = min(samples)
        except Exception as exc:
            print(f"  {label:<16}  ERROR: {exc}")
            continue
        rate = n / best
        print(f"  {label:<16}  {rate/1e6:>10.2f}")
        result["libs"].setdefault(label, {})["display"] = {
            "best_sec": best,
            "it_per_s": rate,
        }

    # CPU cost — process_time() captures all threads, so a background
    # render thread shows up here even though it doesn't block the
    # producer loop. Baseline is the bare for-loop.
    print("\n=== CPU cost (process_time, min of runs) ===")
    print(f"  {'variant':<16}  {'wall ms':>9}  {'cpu ms':>9}  "
          f"{'extra ns/iter':>14}  {'cpu/wall':>9}")
    print(f"  {'-'*16}  {'-'*9}  {'-'*9}  {'-'*14}  {'-'*9}")
    cpu_base_samples = [cpu_baseline(n) for _ in range(runs)]
    cpu_base_wall = min(s[0] for s in cpu_base_samples)
    cpu_base_cpu = min(s[1] for s in cpu_base_samples)
    base_ratio = cpu_base_cpu / max(cpu_base_wall, 1e-12)
    print(f"  {'baseline':<16}  {cpu_base_wall*1e3:>9.1f}  "
          f"{cpu_base_cpu*1e3:>9.1f}  {'-':>14}  {base_ratio:>9.2f}")
    result["cpu_baseline"] = {"wall": cpu_base_wall, "cpu": cpu_base_cpu}

    cpu_benches = [
        ("barflow-nodisp", cpu_barflow_nodisplay, "nodisplay"),
        ("barflow-disp",   cpu_barflow_display,   "display"),
        ("tqdm-nodisp",    cpu_tqdm_nodisplay,    "nodisplay"),
        ("tqdm-disp",      cpu_tqdm_display,      "display"),
        ("rich-nodisp",    cpu_rich_nodisplay,    "nodisplay"),
        ("rich-disp",      cpu_rich_display,      "display"),
        ("alive-nodisp",   cpu_alive_nodisplay,   "nodisplay"),
        ("alive-disp",     cpu_alive_display,     "display"),
    ]
    for label, fn, mode in cpu_benches:
        try:
            samples = [fn(n) for _ in range(runs)]
            # Best = smallest CPU time (user's perspective on overhead).
            best = min(samples, key=lambda wc: wc[1])
            wall, cpu = best
        except Exception as exc:
            print(f"  {label:<16}  ERROR: {exc}")
            continue
        extra_cpu_ns = max(cpu - cpu_base_cpu, 0.0) * 1e9 / n
        ratio = cpu / max(wall, 1e-12)
        print(f"  {label:<16}  {wall*1e3:>9.1f}  {cpu*1e3:>9.1f}  "
              f"{extra_cpu_ns:>14.1f}  {ratio:>9.2f}")
        lib_key = label.rsplit("-", 1)[0]
        if lib_key == "alive":
            lib_key = "alive-progress"
        slot = result["libs"].setdefault(lib_key, {}).setdefault("cpu", {})
        slot[mode] = {
            "wall_sec": wall,
            "cpu_sec": cpu,
            "extra_cpu_ns_per_iter": extra_cpu_ns,
            "cpu_wall_ratio": ratio,
        }

    return result


def format_report(r: dict) -> str:
    n = r["n"]
    lines = [
        "# BarFlow benchmark results",
        "",
        f"Iterations per run: **{n:,}**  ({r['runs']} runs, best wall time reported)",
        f"Platform: Windows + Python {sys.version_info.major}.{sys.version_info.minor}",
        "",
        "## Import startup (median, baseline-subtracted)",
        "",
        "| Library | Cold import (ms) |",
        "|---|---:|",
    ]
    for lib in ("barflow", "tqdm", "rich", "alive"):
        s = r["libs"].get(lib, {}).get("startup_ms")
        if s is None:
            lines.append(f"| {lib} | — |")
        else:
            lines.append(f"| {lib} | **{s:.2f}** |")
    lines += [
        "",
        f"Baseline bare for-loop: **{n / r['baseline_sec'] / 1e6:.2f} M it/s**"
        f"  ({r['baseline_ns_per_iter']:.1f} ns/iter)",
        "",
        "## Counter hot path (each lib in its disabled mode)",
        "",
        "> **Caveat:** `rich` and `alive-progress` don't truly short-circuit",
        "> when `disable=True`. They skip rendering but still run the full",
        "> `advance()` accounting path (dict + RLock + deque for rich; similar",
        "> bookkeeping for alive). Their numbers here reflect that, not a zero-work",
        "> path. `barflow-tick` and `barflow-track` short-circuit at the C level.",
        "",
        "| Variant | M it/s | ns/iter over baseline |",
        "|---|---:|---:|",
    ]
    ordered = [
        ("barflow", "barflow-tick"),
        ("barflow", "barflow-track"),
        ("barflow", "barflow-iter"),
        ("tqdm", "tqdm"),
        ("rich", "rich"),
        ("alive-progress", "alive-progress"),
    ]
    for lib, key in ordered:
        slot = r["libs"].get(lib, {}).get("nodisplay", {}).get(key)
        if not slot:
            lines.append(f"| {key} | — | — |")
            continue
        lines.append(
            f"| {key} | **{slot['it_per_s'] / 1e6:.2f}** | "
            f"{slot['ns_per_iter_over_baseline']:.1f} |"
        )
    lines += ["", "## Display on (writing to in-memory sink)", "",
              "| Library | M it/s |", "|---|---:|"]
    for lib in ("barflow", "tqdm", "rich", "alive-progress"):
        slot = r["libs"].get(lib, {}).get("display")
        if not slot:
            lines.append(f"| {lib} | — |")
            continue
        lines.append(f"| {lib} | **{slot['it_per_s'] / 1e6:.2f}** |")

    base_cpu = r.get("cpu_baseline", {}).get("cpu", 0.0)
    lines += [
        "",
        "## CPU cost (process_time, sums all threads)",
        "",
        f"Baseline bare for-loop CPU: **{base_cpu*1e3:.1f} ms** for {n:,} iters.",
        "",
        "| Library | Mode | CPU ms | extra ns/iter | CPU/wall |",
        "|---|---|---:|---:|---:|",
    ]
    cpu_order = [
        ("barflow", "nodisplay"),
        ("barflow", "display"),
        ("tqdm", "nodisplay"),
        ("tqdm", "display"),
        ("rich", "nodisplay"),
        ("rich", "display"),
        ("alive-progress", "nodisplay"),
        ("alive-progress", "display"),
    ]
    for lib, mode in cpu_order:
        slot = r["libs"].get(lib, {}).get("cpu", {}).get(mode)
        if not slot:
            lines.append(f"| {lib} | {mode} | — | — | — |")
            continue
        lines.append(
            f"| {lib} | {mode} | **{slot['cpu_sec']*1e3:.1f}** | "
            f"{slot['extra_cpu_ns_per_iter']:.1f} | "
            f"{slot['cpu_wall_ratio']:.2f} |"
        )
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2_000_000)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--startup-runs", type=int, default=7)
    ap.add_argument("--out", type=str, default=str(REPO / "benchmarks" / "bench_raw.md"))
    args = ap.parse_args()

    r = run_all(args.n, args.runs)
    report = format_report(r)
    print("\n" + report)
    Path(args.out).write_text(report, encoding="utf-8")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()

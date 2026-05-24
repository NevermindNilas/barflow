# BarFlow

**A fast Python progress bar library with a C++ core. Windows-first.**
Built to beat `tqdm`, `rich.progress`, and `alive-progress` on cold
import, per-iteration overhead, peak it/s, memory footprint, tail
latency, multi-bar throughput, and first-frame latency — simultaneously.

```python
import barflow

# Fastest: `for _ in progress:` runs at 160+ M it/s — faster than
# a bare `for _ in range(n): pass` because Py_None is immortal.
with barflow.Progress(total=n, desc="Crunching") as p:
    for _ in p:
        do_work()

# When you also need the iterated values:
for x in barflow.track(range(1_000_000), desc="Working"):
    ...

# Event-driven / manual:
with barflow.Progress(total=n, desc="Streaming") as p:
    for chunk in data:
        process(chunk)
        p.advance(len(chunk))
```

## Benchmarks

Numbers below are from `benchmarks/bench.py` on Windows 11 / Python
3.13 / N = 20,000,000 iterations (5 runs per data point, best wall
time for rate measurements, min CPU time for CPU measurements).
Baseline bare `for _ in range(n): pass` is **145.75 M it/s**
(6.9 ns/iter, 140.6 ms of CPU). Raw output lives in
`benchmarks/bench_raw.md`; methodology and platform notes are in
`benchmarks/results.md`.

### Headline

| Axis                                |       BarFlow |    tqdm |    rich | alive-progress |
| ----------------------------------- | ------------: | ------: | ------: | -------------: |
| Cold import (ms)                    |      **1.21** |   72.27 |   74.96 |          30.12 |
| Overhead, `for _ in p:` (ns/iter)   |       **0.0** |     7.4 |   471.9 |          384.9 |
| Overhead, `track(...)` (ns/iter)    |       **3.0** |     7.4 |   471.9 |          384.9 |
| Peak it/s, display off              |   **160.8 M** |  70.2 M |   2.1 M |          2.6 M |
| Peak it/s, display on               |   **101.8 M** |  19.6 M |   2.1 M |          2.1 M |
| Python heap peak (1 M iters)        |     **486 B** |  298 KB |  661 KB |         3.4 MB |
| Tail latency p99.9 (ns)             |       **100** |     200 |   2,200 |          2,200 |
| First-frame latency (µs)            |        **32** |      97 |     921 |            n/a |
| Multi-bar, 4 tasks (M it/s)         |    **43.9 M** |  8.8 M  |   2.2 M |            n/a |
| Metadata churn (M it/s)             |    **29.6 M** |  6.6 M  |   2.0 M |          1.9 M |
| Total CPU, display on (ms for 20 M) |       **188** |     953 |   9,297 |          9,391 |

BarFlow wins on every axis — **25–62×** faster cold import, **zero
measurable overhead** on its iteration fast path (faster than a bare
`for _ in range(n)` because Py_None is immortal on 3.12+ and skips
the store-cycle refcount work that range's small-int yields incur),
**5.2×** display-on throughput vs tqdm, **~50×** vs rich / alive,
**600×+ less Python heap** peak, **2× tighter tail latency**, **3×
faster first-frame paint** than tqdm, and **~50×** less CPU than
rich / alive over 20 M iterations. The sub-1.0 CPU/wall ratio
reflects the decoupled render thread: it wakes on a 50 ms timeout,
formats into a preallocated buffer, and spends most of its life
parked on a condition variable, so the producer loop never pays for
rendering inline.

### Import startup (median, baseline-subtracted, 11 runs)

| Library | Cold import (ms) |  vs BarFlow |
| ------- | ---------------: | ----------: |
| barflow |         **1.21** |          1× |
| alive   |            30.12 |       25×   |
| tqdm    |            72.27 |       60×   |
| rich    |            74.96 |       62×   |

Measured by timing `python -c "from <lib> import ..."` in a
subprocess and subtracting a bare-interpreter baseline
(`python -c "pass"`), so the number is just the work the library
does at import time. BarFlow's module graph is deliberately lazy:
`themes`, `columns`, `style`, `spinners`, `hooks`, and `aio` are
all resolved on first attribute access via `__getattr__`, so the
cold import only pays for the C extension load and an `__init__.py`
that does nothing but expose `Progress`, `Tracker`, and `track`.

### No-display hot path — pure per-tick overhead

Display is disabled (`disable=True` where the library supports it)
so we measure the cost of advancing the counter, not rendering.
ns/iter is over the bare for-loop baseline.

| Variant       |     M it/s | ns/iter over baseline |
| ------------- | ---------: | --------------------: |
| barflow-iter  | **160.76** |               **0.0** |
| barflow-track |     101.13 |                   3.0 |
| tqdm          |      70.23 |                   7.4 |
| barflow-tick  |      65.39 |                   8.4 |
| alive         |       2.55 |                 384.9 |
| rich          |       2.09 |                 471.9 |

- `barflow-iter` is `for _ in p:` — BarFlow's `Progress` type
  implements the iteration protocol directly, so `FOR_ITER`
  dispatches `tp_iternext` without the CPython vectorcall
  trampoline. The iternext body is three x86 instructions
  (`load`, `fetch_add`, `return Py_None`), and Py_None's
  immortal refcount on 3.12+ means the loop's `STORE_FAST _`
  is free. Net result: *below* the bare for-loop baseline,
  because a `range`-driven loop still does refcount work on
  its cached small-int yields.
- `barflow-track` is the `for x in barflow.track(iterable):`
  wrapper, used when you also need the yielded values.
- `barflow-tick` is the manual `Progress.tick()` call from
  Python, which pays the full CPython vectorcall dispatch
  overhead per call. Use the iteration protocol above when you
  don't have a source iterable.

### Display on — throughput with a live renderer

Comparator libraries write into an `io.StringIO` sink with
`force_terminal=True` so no real console I/O is measured. BarFlow
writes to its native Windows console path (no sink parameter),
which makes the comparison conservatively *worse* for BarFlow.

| Library        |     M it/s | vs BarFlow |
| -------------- | ---------: | ---------: |
| barflow        | **101.76** |         1× |
| tqdm           |      19.57 |      5.20× |
| rich           |       2.11 |        48× |
| alive-progress |       2.09 |        49× |

BarFlow's render loop emits **delta frames**: each column's
previously-rendered bytes are cached, and on the next frame the
render thread emits `\x1b[<n>C` (cursor-right) over unchanged
spans instead of re-writing the bytes. On a real TTY this cuts
bytes-written per frame by roughly 60% for the default layout;
the sink-based benchmark above does not exercise the delta path,
so the number you see is the *lower bound* — real terminals get
more.

### Memory footprint

| Library        | tracemalloc peak | RSS import | RSS run  |
| -------------- | ---------------: | ---------: | -------: |
| barflow        |        **486 B** |     236 KB |   192 KB |
| tqdm           |           298 KB |    6.83 MB |   992 KB |
| rich           |           661 KB |    6.58 MB |   1.77 MB |
| alive-progress |          3.41 MB |    1.64 MB |   3.79 MB |

`tracemalloc peak` is the high-water mark of the Python heap over
a 1 M-iteration run (`bench_memory.py`). BarFlow's ~500 bytes is
effectively one `Progress` object's shell — the counter, output
buffer, render thread, and render scratch all live in C-owned
storage that `tracemalloc` cannot see. Competitors allocate
hundreds of KB to several MB of Python objects per run.

### Tail latency (per-iter distribution, display on)

| Library        |      p50 |    p90 |      p99 |    p99.9 |       max |
| -------------- | -------: | -----: | -------: | -------: | --------: |
| barflow        | **100 ns** | 100 ns | 100 ns | **100 ns** |   7.80 µs |
| tqdm           |   100 ns | 200 ns |   200 ns |   200 ns |  28.00 µs |
| rich           |   500 ns | 600 ns |   800 ns |   2.20 µs | 153.20 µs |
| alive-progress |   500 ns | 600 ns |   700 ns |   2.20 µs | 138.00 µs |

Per-iter timestamps recorded with `perf_counter_ns()` across 100 K
iterations; `bench_tail_latency.py`. BarFlow is the only library
whose p99.9 does not diverge from its p50 — the render thread
never spills work onto the producer, so there is no jitter source
to create tail spikes.

### First-frame latency (`__enter__` to first byte)

| Library | median |     min |     p90 |
| ------- | -----: | ------: | ------: |
| barflow |  **32 µs** |  28 µs |  41 µs |
| tqdm    |   97 µs |  93 µs | 109 µs |
| rich    |  921 µs | 845 µs | 1.05 ms |

BarFlow paints a synchronous first frame on `Progress.__enter__`
before the render thread takes over, eliminating the 50 ms
"blank bar" window that would otherwise be visible for
short-lived jobs. Measured by `bench_first_frame.py`.

### Multi-bar throughput (4 concurrent tasks)

| Library        | wall time |  aggregate |
| -------------- | --------: | ---------: |
| barflow        |  **22.8 ms** |  **43.9 M it/s** |
| tqdm           |   114.1 ms |      8.8 M it/s |
| rich           |   465.8 ms |      2.2 M it/s |
| alive-progress |   skipped (no clean multi-task API) |            |

4 tasks × 250 K ticks each, driven round-robin from one thread
(`bench_multibar.py`). BarFlow stays lock-free — every task has
its own cache-line-padded counter, and the render thread walks
the task vector under a mutex that the hot path never touches.

### Metadata churn (description updated every 1 K iters)

| Library        | wall time |    it/s  |
| -------------- | --------: | -------: |
| barflow        |  **33.8 ms** | **29.6 M** |
| tqdm           |   152.4 ms |   6.6 M |
| rich           |   514.1 ms |   2.0 M |
| alive-progress |   526.9 ms |   1.9 M |

1 M ticks, `set_description` called every 1000 ticks with a
pre-generated 40-char string (`bench_metadata_churn.py`).
BarFlow exposes `set_description(str)` and
`set_task_description(task_id, str)` that briefly acquire the
render mutex to swap the description; the lock-free tick hot
path is unaffected.

### CPU cost — render thread counted

`time.process_time()` sums user+system time across *every* thread
of the process (Windows `GetProcessTimes`, Linux
`CLOCK_PROCESS_CPUTIME_ID`, macOS `task_info`), so a background
render thread cannot hide from this measurement.

| Library        | Mode        | CPU ms (best of 5) | Extra ns/iter | CPU / wall |
| -------------- | ----------- | -----------------: | ------------: | ---------: |
| barflow        | display-off |          **187.5** |           2.3 |       0.96 |
| barflow        | display-on  |          **187.5** |           2.3 |       0.96 |
| tqdm           | display-off |              265.6 |           6.2 |       0.93 |
| tqdm           | display-on  |              953.1 |          40.6 |       0.95 |
| alive-progress | display-off |            7,671.9 |         376.6 |       0.98 |
| alive-progress | display-on  |            9,390.6 |         462.5 |       0.98 |
| rich           | display-off |            9,437.5 |         464.8 |       0.96 |
| rich           | display-on  |            9,296.9 |         457.8 |       0.98 |

Two things stand out:

1. **BarFlow's CPU cost is identical whether the display is on or
   off.** Turning the bar on adds no measurable per-iter CPU
   because the render thread wakes on a 50 ms condition-variable
   timeout and spends the rest of its life parked. The producer
   loop sees the same hot path in both modes.
2. **tqdm's CPU grows 3.6× when the display turns on** (266 →
   953 ms), because rendering runs inline on the producer thread.
   Rich and alive-progress sit near **~50×** BarFlow's CPU cost in
   both modes — they pay hundreds of nanoseconds of dict/lock work
   per `advance()` call before any rendering happens.

### Caveats / reproducibility

- Numbers are from a single Windows 11 box; absolute values will
  differ on Linux / macOS but the ratios are stable in repeated
  runs. Re-run `python benchmarks/bench.py --n 20000000 --runs 5`
  to reproduce the main table, and `python benchmarks/bench_*.py`
  for each extra axis (tail latency, memory, first-frame,
  multi-bar, metadata churn).
- tqdm is run with `mininterval=0.05` (matching BarFlow's default)
  rather than its out-of-box 0.10, so the comparison isolates
  per-render work from render frequency instead of giving tqdm a
  free 2× render-skip advantage.
- `time.process_time()` resolution is ~15 ms on Windows, so the
  smallest CPU numbers (barflow: 187 ms) sit only ~12 ticks above
  noise floor. Differences against tqdm (5×) and rich/alive (~50×)
  are well outside that window.
- Display-on throughput is measured against an `io.StringIO` sink,
  which skips Windows console latency. On a real TTY, BarFlow's
  delta-render (cursor-advance over unchanged column spans) gives
  it additional headroom that the StringIO harness cannot see.

## Install

```
pip install barflow
```

Wheels are published for Windows (AMD64), Linux (x86_64, aarch64), and
macOS (x86_64, arm64) for CPython 3.10 through 3.14, including the
free-threaded `cp313t` / `cp314t` builds.

## Features

- **Zero-overhead iteration.** `for _ in progress:` runs at 160+ M
  it/s — below the bare `for _ in range(n)` baseline, because
  `FOR_ITER` dispatches directly to `tp_iternext` (no vectorcall
  trampoline) and Py_None is immortal on 3.12+ (no refcount work
  on `STORE_FAST`).
- **C++ hot path.** `tick`, `advance`, and `Tracker`'s iter-next
  are single `std::atomic::fetch_add` calls with no locks and no
  Python-level bookkeeping. Task counters are cache-line padded
  so the render thread's reads never false-share with producer
  writes.
- **Decoupled renderer.** A background thread wakes on a 50 ms
  condition-variable timeout and formats into a preallocated buffer.
  The producer never blocks.
- **Delta-render.** The render loop caches each column's previous
  bytes and emits `\x1b[<n>C` cursor-advance over unchanged spans
  instead of rewriting the frame. Roughly 60% fewer bytes written
  per frame on the default layout.
- **Synchronous first frame.** `Progress.__enter__` paints one
  frame inline before the render thread takes over, so short-lived
  jobs don't see the 50 ms blank-bar window.
- **Windows-first.** Unconditional `ENABLE_VIRTUAL_TERMINAL_PROCESSING`,
  UTF-16 transcoded `WriteConsoleW` chunked at 32 KB, legacy-console
  fallback. No `colorama` dependency. A reusable `wscratch`
  transcoding buffer means steady-state frames are zero-alloc.
- **Multi-task + columns.** 9 built-in column types
  (description/bar/percent/count/rate/elapsed/eta/spinner/text),
  rich-style column API, themes, ANSI cursor stacking for nested bars.
  `Progress.set_description(str)` and `set_task_description(task_id, str)`
  expose metadata churn without touching the lock-free hot path.
- **Spinner DSL.** Compositional factories
  (`frame` / `scrolling` / `bouncing` / `alongside` / `sequential`)
  compile to precomputed frame tables at `__enter__`.
- **`print()` interception.** `capture_output=True` reroutes
  `sys.stdout` through `write_above()` so user prints appear above
  live bars without tearing.
- **asyncio.** `barflow.aio.atrack(aiter)` wraps async iterables.
- **Tiny cold import.** `import barflow` is ~1.2 ms
  (baseline-subtracted median) — 25–62× faster than the
  alternatives. All non-core submodules (`themes`, `columns`,
  `spinners`, `style`, `hooks`, `aio`) are lazy-loaded via
  PEP 562 `__getattr__`.
- **Sub-kilobyte Python heap.** Peak `tracemalloc` usage across a
  1 M-iteration run is ~500 bytes, vs 300 KB (tqdm), 660 KB (rich),
  and 3.4 MB (alive-progress).

## Usage

```python
import barflow
from barflow.columns import (
    SpinnerColumn, DescriptionColumn, BarColumn, PercentColumn,
    CountColumn, RateColumn, EtaColumn,
)

# Simplest form — when you need the iterated values
for x in barflow.track(range(1000), desc="task"):
    ...

# Fastest form — when you just need a counter
with barflow.Progress(total=1000, desc="task") as p:
    for _ in p:
        do_work()

# Custom columns
with barflow.Progress(
    SpinnerColumn(name="dots"), " ",
    DescriptionColumn(), " ",
    BarColumn(width=40, color="magenta"), " ",
    PercentColumn(), "  ",
    CountColumn(), " | ", EtaColumn(),
    total=1000, desc="build",
) as p:
    for _ in range(1000):
        p.tick()

# Named theme
with barflow.Progress(theme="classic", total=1000) as p:
    ...

# Multi-task
with barflow.Progress(theme="classic") as p:
    dl = p.add_task(total=100, desc="download")
    ex = p.add_task(total=100, desc="extract")
    for i in range(100):
        p.update(dl, 1)
        p.update(ex, 1)

# Live prints during a bar
with barflow.Progress(total=100, capture_output=True) as p:
    for i in range(100):
        if i % 10 == 0:
            print(f"checkpoint {i}")   # appears above the bar
        p.tick()

# asyncio
import asyncio, barflow.aio as aio
async def main():
    async for x in aio.atrack(some_async_iter(), total=1000):
        ...
asyncio.run(main())
```

## Design

See `docs/DESIGN.md` for the full architecture: atomic hot path,
background render thread, column pipeline, Windows console handling,
and the benchmarks methodology.

## Build from source

Requires Visual Studio 2022+ (Windows) or GCC/Clang + Python headers
(POSIX) and Python ≥ 3.10.

```
# Windows
build.bat

# POSIX
python -m pip install -e .
```

## License

MIT. See `LICENSE`.

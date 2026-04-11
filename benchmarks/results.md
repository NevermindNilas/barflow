# BarFlow benchmark results (v0.2.0, 2026-04-11)

**Machine:** Windows 11 Pro, Python 3.13.12, MSVC 14.50, `/O2`.
**Harness:** `benchmarks/bench.py --n 20_000_000 --runs 5`. Best wall
time per library reported; "ns/iter over baseline" subtracts the cost
of a bare `for _ in range(N): pass` loop on the same machine. Raw
auto-generated output lives in `benchmarks/bench_raw.md`.

Bare baseline: **145.63 M it/s**  (6.9 ns/iter).

## 1. Import startup (median over 7 runs, interpreter-baseline subtracted)

| Library       | Cold import (ms) | vs barflow |
| ------------- | ---------------: | ---------: |
| **barflow**   |         **1.97** |         1× |
| alive-progress|            33.55 |        17× |
| tqdm          |            69.73 |        35× |
| rich.progress |            84.83 |        43× |

`barflow/__init__.py` imports only `_core` and `Tracker` at module
load; everything else (`columns`, `themes`, `spinners`, `hooks`, `aio`,
`_progress`) is lazy-loaded via `__getattr__`. Competitors pay for
`colorama` (tqdm), `pygments`/`east_asian_width`/`emoji` tables
(rich), or the full animation config resolution (alive-progress) at
import time.

## 2. Per-iteration overhead (no-display hot path)

| Variant                   |  Peak it/s | ns/iter over baseline |
| ------------------------- | ---------: | --------------------: |
| **barflow — `track()`**   | **97.19 M**|              **3.4** |
| tqdm                      |   69.97 M  |                   7.4 |
| **barflow — `.tick()`**   |   64.75 M  |                   8.6 |
| alive-progress            |    2.42 M  |                 405.7 |
| rich.progress             |    2.05 M  |                 482.1 |

`barflow.track()` stays at **2.2× lower overhead than tqdm** (3.4 ns
vs 7.4 ns). The trick: `Tracker.tp_iternext` is a C function that
calls `PyIter_Next` and does a `std::atomic<uint64_t>::fetch_add`
without any Python bytecode dispatch. tqdm's hand-unrolled `__iter__`
is already excellent at reducing Python-level work, but it cannot
escape bytecode for the `yield` and the `n += 1`.

The `.tick()` method-call form (method dispatch from a Python for-loop)
is ~1 ns/iter slower than tqdm because the CPython `METH_NOARGS` call
protocol pays for the `CALL_METHOD` opcode + argument packaging. **Use
`track()` when you care about peak throughput.**

rich and alive-progress lose by two orders of magnitude on the hot
path because their "disabled" forms still acquire an RLock and/or
touch a deque of samples for speed estimation
(`rich/progress.py:1341-1364`,
`alive_progress/core/progress.py:460-490`). barflow's `disable=True`
skips the render thread entirely, so the hot path is just `fetch_add`.

## 3. Peak it/s with display ON (renderer writing to a sink)

| Library        |     Peak it/s | vs barflow |
| -------------- | ------------: | ---------: |
| **barflow**    |   **94.78 M** |         1× |
| tqdm           |       19.28 M |      0.20× |
| rich.progress  |        2.07 M |      0.02× |
| alive-progress |        1.99 M |      0.02× |

barflow's display-on throughput is **essentially equal to its
display-off throughput** (94.8 vs 97.2 M it/s). The render thread is
fully decoupled from the producer: the producer's hot path touches
one atomic counter; the render thread reads it on its own cadence
(20 Hz) and formats into a preallocated buffer. The producer never
waits.

- **4.9× faster than tqdm** — tqdm's synchronous `refresh()` model
  means the producer thread periodically runs `format_meter` and
  writes to stderr, stealing cycles from the user's loop.
- **46× faster than rich.progress** — Rich is bottlenecked by
  `Segment` namedtuple allocation on every refresh tick, ~1–3 ms of
  Python per 10 Hz frame.
- **48× faster than alive-progress** — alive already has the
  background-thread renderer (which is the right model, and where our
  architecture is inspired by it) but pays the Python per-iteration
  cost on the producer side: `bar()` is a Python method call with
  several attribute accesses before the counter bump.

## 4. Scorecard

| Axis                       | Winner                | Margin vs runner-up |
| -------------------------- | --------------------- | ------------------- |
| Import startup             | **barflow**           | 17× (alive)         |
| Per-iteration overhead     | **barflow** (`track`) | 2.2× (tqdm)         |
| Peak it/s, display on      | **barflow**           | 4.9× (tqdm)         |
| Peak it/s, display off     | **barflow** (`track`) | 1.4× (tqdm)         |

barflow wins on every axis.

## 5. Methodology notes

- **What "no-display" means per library.** barflow uses `disable=True`
  (render thread never starts). tqdm uses `tqdm(..., disable=True)`.
  rich uses `Progress(disable=True)`. alive-progress uses
  `alive_bar(..., disable=True)`.

- **What "display on" means per library.** Each library is pointed at
  an `io.StringIO` with `force_terminal`/equivalent so the render path
  executes fully. Output is buffered in memory so terminal I/O latency
  is not part of the measurement.

- **Warm-up.** 5 runs per config, minimum reported. First run warms
  the CPython inline cache. Subprocess-isolated startup uses 7 runs
  and the median; baseline interpreter launch is subtracted out.

- **Render thread active under load.** At N=20,000,000 and ~200 ms of
  producer time, the default 50 ms render interval means the
  background thread executes ~4 render cycles during the measurement.
  Producer throughput does not degrade — the two threads contend only
  on one atomic cache line.

- **Caveats.** (1) Display-on tests use in-memory sinks, not real
  terminals. (2) barflow's multi-task / column / spinner features are
  exercised in smoke tests; the benchmark numbers above use the
  default theme (description + bar + percent + count + elapsed/eta/
  rate) which is the realistic workload for the render thread.

## 6. Reproducing

```
pip install barflow tqdm rich alive-progress
python benchmarks/bench.py --n 20000000 --runs 5
```

Output goes to `benchmarks/bench_raw.md` (auto-overwritten per run).
Hand-curated commentary lives in this file (`results.md`) and is
updated per release.

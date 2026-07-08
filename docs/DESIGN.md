# BarFlow — Design Proposal

**Goal.** A Python progress-bar library with a C++ core, cross-platform, that
beats `tqdm`, `rich.progress`, and `alive-progress` on three axes
simultaneously: **import startup time**, **peak iterations/second**, and
**per-iteration overhead** — without giving up the customization surface those
libraries are loved for.

The design below is informed by a source-level read of all three libraries
(`tqdm/std.py`, `rich/progress.py` + `rich/live.py`, `alive_progress/core/*`
and `alive_progress/animations/*`). References to specific line numbers in
those libraries are cited inline.

---

## 1. Non-goals

- Not a TUI framework. We render progress bars. We do not render trees,
  tables, syntax-highlighted panels, or arbitrary Renderables. Rich already
  occupies that niche and the cost model (every frame rebuilds a segment
  tree) is the exact thing we are avoiding.
- Not a pure-Python library. The reference implementation is C++ with a thin
  Python shim. A pure-Python fallback is out of scope for the POC.
- Not cross-platform parity on day one. Windows is the priority target;
  POSIX support is a later milestone.

## 2. Competitive baselines (what we must beat)

From the research pass:

| Library         | Hot-path cost (no-op loop)      | Refresh model                  | `from X import Y` cost* |
| --------------- | ------------------------------- | ------------------------------ | ----------------------- |
| `tqdm`          | ~60 ns/iter (self-reported)     | Synchronous, gated by miniters | ~20-40 ms               |
| `alive-progress`| Counter++ (render off-thread)   | Adaptive-fps background thread | ~40-80 ms               |
| `rich.progress` | `advance()`: lock + dict + deque | Fixed 10 fps background thread | ~150-300 ms             |

*Cold-cache `from X import Y` on Windows + Python 3.13; measured in the
benchmark harness, not quoted.

`tqdm` wins the hot-path race today thanks to a hand-unrolled `__iter__`
(`tqdm/std.py:1264-1289`) that hoists all state into local variables and
reduces each yield to `n += 1; if n - last >= miniters: ...`. We can match
this from Python and **beat it** by pushing the gate and the counter into
C++, where neither is subject to bytecode dispatch.

`alive-progress` wins the architecture race: `bar()` is literally
`run.count += count` on the user thread; drawing happens on a daemon thread
that wakes on a `Condition` with a timeout of `1/fps` (see
`alive_progress/core/progress.py:85-97`). This is the right model and we will
keep it.

`rich.progress` wins the API race. Columns are composable `ProgressColumn`
subclasses (`rich/progress.py:625-957`) and the abstraction is beautiful. It
is also the reason Rich is slow: every 10 Hz tick rebuilds a `Table`, which
walks a tree of Renderables allocating `Segment` namedtuples
(`rich/segment.py:52-63`). We will copy the *shape* of Rich's column API but
return lightweight cell values, not Renderables.

## 3. Architecture

```
              ┌──────────────────────────────────────────┐
              │  User Python thread                      │
              │                                          │
              │   for x in barflow.track(iterable):   │
              │       ...                                │
              │         │                                │
              │         │ fast path: 1 C call per iter   │
              │         ▼                                │
              │   _core.advance(handle, 1)               │
              └───────────┬──────────────────────────────┘
                          │
                          │ releases GIL, does:
                          │   counter.fetch_add(n, relaxed)
                          │   if counter - last_render >= gate:
                          │       cond.notify_one()      (coarse, cheap)
                          │
              ┌───────────▼──────────────────────────────┐
              │  Render thread (C++, spawned on first    │
              │  progress open, lives until close)       │
              │                                          │
              │   while running:                         │
              │       cond.wait_for(1/fps)               │
              │       snapshot task atomics              │
              │       if dirty: format → buffer → write  │
              └───────────┬──────────────────────────────┘
                          │
                          │ WriteConsoleW (Win) or write(2) (POSIX)
                          ▼
                      Terminal
```

Key properties:

1. **The user-thread hot path is a single C function call** with a
   `METH_FASTCALL` entry point. Inside the function, we release the GIL
   (optional — see §7 for the tradeoff), do an atomic `fetch_add`, compare
   against a render-gate threshold, and if dirty bump a condvar. No Python
   allocation, no string work, no I/O, no formatting.
2. **The render thread owns all string formatting and I/O.** It sleeps on a
   `std::condition_variable` with a timeout equal to the adaptive frame
   interval. It never blocks the producer.
3. **Atomics, not locks, on the hot path.** `tqdm` acquires an RLock (plus
   optional multiprocessing RLock) on every `refresh()`
   (`tqdm/std.py:64-105`). Rich acquires an RLock on every `advance()`
   (`rich/progress.py:1341-1364`). We use `std::atomic<uint64_t>` with
   `memory_order_relaxed` for the counter and a `std::atomic<bool>` for the
   render-dirty flag.
4. **No per-frame allocation.** The renderer owns a preallocated
   `std::string` (`buffer`) that is `.clear()`-reset per frame and
   `push_back`/`append`-grown back to capacity. After the first few frames
   the buffer reaches steady-state size and stops growing.
5. **Columns are "cell emitters", not Renderables.** A column is a function
   object that writes into the renderer's output buffer given a task
   snapshot. Built-in columns are pure C++; user columns are Python
   callables that return `str`. See §5.

## 4. The hot path in detail

```cpp
// Pseudocode for barflow_core::advance
static PyObject* advance(PyObject* self, PyObject* const* args, Py_ssize_t nargs) {
    // args[0] = task handle (int), args[1] = n (int, default 1)
    auto* task = task_table[PyLong_AsLong(args[0])];
    uint64_t n = (nargs >= 2) ? PyLong_AsUnsignedLongLong(args[1]) : 1;

    uint64_t before = task->completed.fetch_add(n, std::memory_order_relaxed);
    uint64_t after = before + n;

    // dirty gate: only notify if we've crossed a render threshold
    // gate is auto-tuned like tqdm's dynamic_miniters
    if (after - task->last_rendered.load(std::memory_order_relaxed) >= task->gate) {
        task->dirty.store(true, std::memory_order_release);
        // notify_one is cheap when no waiter; we still gate it behind the
        // threshold because the mutex acquire inside notify isn't free
        task->owner->render_cv.notify_one();
    }

    Py_RETURN_NONE;
}
```

- `PyLong_AsLong` is ~5 ns on modern CPython.
- `fetch_add(relaxed)` is ~1 ns uncontended.
- The comparison + branch is ~1 ns, predicted taken rarely.
- `notify_one` is skipped unless the gate fires.

**Expected cost: 15–25 ns per call**, versus `tqdm`'s 60 ns/iter which
includes Python-level `yield`, `n += 1`, attribute loads, and a branch. We
are not doing the yield — our iterator wrapper (see §5) keeps `advance` out
of the per-element path when possible (see §9 for how `track()` handles
this).

## 5. Python API surface

```python
import barflow

# 1. One-liner iterable wrapper — 95% of usage
for x in barflow.track(range(1_000_000), desc="Working"):
    compute(x)

# 2. Context manager with explicit task(s)
with barflow.Progress() as p:
    t1 = p.add_task("Downloading", total=files)
    t2 = p.add_task("Extracting",  total=files)
    for f in files:
        p.advance(t1)
        extract(f)
        p.advance(t2)

# 3. Columns API — shape-compatible with Rich
from barflow.columns import (
    TextColumn, BarColumn, PercentColumn,
    RateColumn, EtaColumn, SpinnerColumn,
)

with barflow.Progress(
    TextColumn("{description}"),
    BarColumn(width=40),
    PercentColumn(),
    "•",
    RateColumn(),
    "•",
    EtaColumn(),
) as p:
    ...
```

### Columns

A column is anything callable as `column(task_snapshot, out: bytearray)`.
Built-in columns are C++ classes exposed via PyCapsule; custom Python columns
pay a GIL reacquire per render tick. Custom columns do not touch the hot
path — they only run on the render thread at `refresh_per_second` cadence,
so even a "slow" Python column costs a few microseconds every 50 ms.

`BarColumn` in particular gets a precomputed frame table: at `__enter__` we
materialize the 8 partial-block glyphs into their UTF-8 byte sequences and
store them in a `std::array<std::string_view, 9>`. Rendering the bar is
then a width loop writing prefetched bytes — no Unicode work per frame. This
mirrors `alive-progress`'s frame precompilation
(`alive_progress/animations/spinner_compiler.py`).

### Spinner DSL

We adopt `alive-progress`'s compositional factories (`frame`, `scrolling`,
`bouncing`, `sequential`, `alongside`, `delayed` — see
`alive_progress/animations/spinners.py:10-257`) because they are the single
best customization idea in the Python progress-bar ecosystem. The Python
builder compiles to a `std::vector<std::string>` of precomputed frame bytes
at `__enter__` time. The render loop then does
`frames[tick % frames.size()]` — branch-free, no allocation.

The POC ships four built-in spinners (`classic`, `dots`, `line`, `arrow`)
with the factory surface stubbed for later work.

## 6. Windows support

This is the priority target and the place we pick up the biggest UX wins.

### Console init (once, at first `Progress` construction)

```cpp
HANDLE h = GetStdHandle(STD_ERROR_HANDLE);
DWORD mode = 0;
if (GetConsoleMode(h, &mode)) {
    DWORD want = mode | ENABLE_VIRTUAL_TERMINAL_PROCESSING
                      | DISABLE_NEWLINE_AUTO_RETURN;
    if (SetConsoleMode(h, want)) {
        caps.vt = true;
    } else {
        caps.vt = false;   // legacy conhost on Win8.1 or earlier
    }
    caps.is_console = true;
} else {
    caps.is_console = false;  // redirected / piped
    caps.vt = false;
}
```

- `tqdm` defers to `colorama` to handle this, which monkey-patches
  `sys.stdout`/`sys.stderr` at `import colorama`. We skip colorama entirely.
- `rich` does the same VT probe (`rich/_windows.py`) but gates it behind a
  legacy-path with `SetConsoleTextAttribute`. We copy this structure.
- `alive-progress` has no explicit VT enable, which is why its smooth-block
  glyphs render as garbage in legacy cmd.exe (issues #220, #174, #161, #160,
  #88 on its tracker). We fix this.

### Write primitive

`WriteConsoleW` with UTF-16 transcoding, chunked to 32 KB to work around the
documented Windows pipe bug that Rich also guards against
(`rich/console.py:1996-2010`). If the destination is not a console
(redirected) we fall through to `_write` on the underlying fd with UTF-8.

### Width

`GetConsoleScreenBufferInfoEx` on every refresh is too expensive. We cache
width and invalidate on `WINDOW_BUFFER_SIZE_EVENT` from a
`ReadConsoleInput` listener running as part of the render thread's
`WaitForMultipleObjects`. On non-console fds width is 80 (fixed).

### Fallbacks

- **No VT:** disable colors, use ASCII bar (`[#####     ]`) with 1-col
  resolution, fall back to `SetConsoleTextAttribute` for the description if
  the user asked for styled text.
- **No UTF-8:** detect via the active code page (`GetConsoleOutputCP()`); if
  not 65001, use ASCII glyphs.

## 7. The GIL question

Releasing the GIL around the hot path is tempting: `advance()` becomes
re-entrant from a C thread and Python threads don't serialize on it. But the
GIL release/reacquire itself costs ~30 ns round trip — more than the
entire fast-path budget. So we **do not release the GIL in `advance`**.

We *do* release it inside `close()` when joining the render thread, and
inside the `track()` iterator wrapper's long-wait operations. The render
thread itself runs entirely without the GIL except when it calls back into
Python for custom columns (rare).

This is the same tradeoff `tqdm` makes implicitly by staying in Python for
the hot path.

## 8. Auto-tuning the render gate (miniters equivalent)

We inherit `tqdm`'s idea (`tqdm/std.py:1335-1343`): track the last few
intervals between renders and adjust `gate` so that renders occur roughly
every `min_interval` seconds. Our version lives in the renderer:

```
on each render:
    now = monotonic_ns
    dt = now - last_render_time
    progress = counter - last_render_count
    ideal_rate = min_interval / dt          # ratio, want ~1.0
    gate = gate * ideal_rate * ema_factor   # ema_factor = 0.3 like tqdm
    gate = clamp(gate, 1, 1 << 20)
```

`min_interval` defaults to 50 ms (20 fps target). Users can set it
per-Progress. The gate value is written back with `memory_order_relaxed` —
the hot path reads it with the same ordering. Races here are benign: an
iteration or two of stale gate is noise.

## 9. `track()` — the fast iterator wrapper

The 95% case is wrapping an iterable. We provide `barflow.track(iter)`
which returns a C-level iterator. Its `__next__` slot (`tp_iternext`) calls
the wrapped iterator's `__next__`, does the atomic `fetch_add` + gate check
in C, and returns the element. No Python bytecode in the loop.

`tqdm` achieves its 60 ns/iter by hoisting to Python locals; we eliminate
the Python-local loads entirely by making the whole loop body C. Expected
cost: **~20 ns/iter**, bounded below by the CPython `PyIter_Next` dispatch
itself.

For iterables without a known total (generators), we skip the percent/ETA
columns at render time and show a spinner + rate only. This mirrors
`alive-progress`'s unknown-total mode.

## 10. Memory layout

```cpp
struct Task {
    std::atomic<uint64_t> completed;   // hot, written by producer
    std::atomic<uint64_t> last_rendered; // hot, read by producer
    std::atomic<uint32_t> gate;        // hot, read by producer
    std::atomic<bool>     dirty;       // hot, written by producer
    // --- cold cacheline: below here is only touched by renderer ---
    uint64_t  total;
    uint64_t  start_time_ns;
    std::string description;
    uint32_t  id;
};
```

The four hot atomics are grouped into one cacheline (64 B). Producer and
consumer cores ping-pong on this line, but the line contains *only* the
hot fields, so we don't invalidate cold data (description, total, etc.) on
every advance.

Multi-task `Progress` instances hold `std::vector<std::unique_ptr<Task>>`
to keep tasks at stable addresses across resizes; 64 B alignment is
enforced.

## 11. Benchmarks to run (Phase 1)

The harness lives in `benchmarks/bench.py` and measures three things:

1. **Import startup.** Subprocess launch of `python -c "from X import Y"`
   for each library, median of 11 runs, discard warmup. Reports wall time
   including interpreter startup and the specific import.
2. **Peak it/s.** A tight no-op loop `for _ in lib.track(range(N)): pass`
   with N chosen so total time is ~5 s. Reports elements/second.
3. **Per-iteration overhead.** `(baseline_seconds - bare_range_seconds) / N`
   where baseline is the library wrapping `range(N)` and bare is the naked
   for-loop. Reports nanoseconds/iter.

Targets for BarFlow POC (all must hold):

| Metric            | tqdm          | rich          | alive        | **barflow** |
| ----------------- | ------------- | ------------- | ------------ | -------------- |
| Import time       | `< tqdm`      | `< rich`      | `< alive`    | **< 10 ms**    |
| Peak it/s (no-op) | `> tqdm`      | `> rich`      | `> alive`    | **> 30 M/s**   |
| Overhead / iter   | `< tqdm × 2`  | `< rich × 2`  | `< alive × 2`| **< 30 ns**    |

If the POC does not hit all three columns "best of the best" on the real
machine, we iterate: profile the hot path, inline further into CPython,
consider a `METH_O` entry for the common `n=1` case, consider a PEP 590
vectorcall adapter.

## 12. Out-of-scope for the POC, in-scope for V1

- Spinner DSL factories (frame/scrolling/bouncing/alongside/sequential).
- Dual-line / nested / multi-bar with position management.
- Enriched `print()` interception during live display
  (copy `alive-progress`'s `hook_manager`).
- Jupyter / IPython widget frontend.
- POSIX support (Linux + macOS) with `tcgetwinsize` / termios VT detection.
- `asyncio` integration (`async for` wrapper).
- Multiprocessing-safe shared lock (`tqdm.set_lock()` equivalent).

The POC aims to exercise the architecture end-to-end so the three
benchmark numbers are real, not projected. Phase 2 fills in the columns and
customization surface that make the library actually pleasant to use.

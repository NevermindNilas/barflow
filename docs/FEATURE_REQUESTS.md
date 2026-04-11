# BarFlow feature backlog — gaps from tqdm / rich / alive-progress

Sourced from open issues across `tqdm/tqdm`, `Textualize/rich`, and
`rsalmei/alive-progress`. Each entry is a feature users have asked for
in those libraries that BarFlow does **not** yet have. Ordered by
impact + ROI, not by upstream popularity alone.

## Priority order

1. PEP 561 type stubs
2. `logging` integration
3. Non-TTY / file-redirect mode
4. True indeterminate / pulsing bar
5. Multiprocessing / worker-pool bars
6. `update_to(n)` absolute-value API
7. Smoothed / EWMA ETA
8. Multicolor segmented bars

---

## 1. PEP 561 type stubs

- **Sources.** tqdm #260 (R40, C34 — #1 tqdm request, years old).
- **What.** Ship `py.typed` marker + complete `.pyi` stubs for `track`,
  `Progress`, every column factory, `aio.atrack`, spinner DSL, themes.
- **Why.** Trivial, zero runtime cost, massive DX. mypy / Pyright /
  PyCharm all light up. Tqdm still doesn't have it.
- **Effort.** ~1 day. Add `py.typed` to package, write stubs alongside
  the C extension, wire through `pyproject.toml`.

## 2. `logging` module integration

- **Sources.** tqdm #313 (R22, C28), tqdm #1272 (R16, C13),
  alive-progress #272.
- **What.** `barflow.logging.BarFlowHandler` that routes stdlib
  `logging` records through `write_above()` so log lines render above
  live bars without tearing. `with barflow.redirect_logging(): ...`
  context manager swaps existing handlers for the duration of a bar.
- **Why.** Single biggest cross-repo pain. Tqdm's
  `logging_redirect_tqdm` is half-broken. BarFlow already has the
  primitive (`capture_output` reroutes stdout) — extending it to a
  logging Handler is mostly plumbing.
- **Effort.** ~2 days. Subclass `logging.StreamHandler`, point its
  `emit()` at `write_above()`, document the ctx mgr.

## 3. Non-TTY / file-redirect mode

- **Sources.** tqdm #750 (R19), tqdm #1514 (R10), tqdm #565 (R8).
- **What.** Auto-detect non-TTY (CI logs, file redirect, `nohup`,
  Docker logs). Switch to newline-per-update at throttled cadence
  instead of `\r`-spam. Add `BARFLOW_DISABLE=1` /
  `NO_PROGRESS=1` env kill-switch and `barflow.disable()` global mute.
- **Why.** Tqdm is infamous for filling CI logs with thousands of
  carriage-return frames. Library authors switch progress libs over
  this alone.
- **Effort.** ~1–2 days. `isatty()` check at `__enter__`, alternate
  render path that emits `\n`-terminated lines on a slower (e.g. 1 s)
  cadence, env-var probe in `Progress.__init__`.

## 4. True indeterminate / pulsing bar

- **Sources.** tqdm #427 (R27), tqdm #458.
- **What.** When `total=None`, render a pulsing / bouncing bar that
  represents "unknown work in progress" — distinct from a spinner and
  distinct from a fake percent. `BarColumn(fill_style="pulse")` for
  explicit opt-in.
- **Why.** Both tqdm and rich fake this (either a spinner or a static
  `?it`). BarFlow's spinner DSL already has `bouncing` / `scrolling`
  factories — reuse the precomputed frame table at render time. Pairs
  with Iter 9 in `ITERATIONS.md`.
- **Effort.** ~2 days. Frame-table generator for the bar width,
  switch in render loop on `total is None`.

## 5. Multiprocessing / worker-pool bars

- **Sources.** tqdm #1228 (R18), tqdm #485 (R10), rich #3529.
- **What.** Shared-memory or pipe IPC so child processes update the
  parent's render. Fix tqdm's notorious `process_map` 0%-stuck bug.
  API: `Progress.add_task(..., shared=True)` returns a handle that
  pickles into workers; workers call `task.advance(n)` and the parent
  render thread sees the updates.
- **Why.** BarFlow's atomic counter + decoupled background renderer is
  exactly the right architecture — the hot path is already
  `fetch_add` on a shared word. Move that word into
  `multiprocessing.shared_memory` and worker processes can hammer it
  losslessly. Big differentiator vs tqdm.
- **Effort.** ~1 week. Shared-memory backing for `ProgressState`
  counters, pickle protocol for task handles, Windows
  `CreateFileMapping` path, POSIX `shm_open` path.

## 6. `update_to(n)` absolute-value API

- **Sources.** tqdm #1264 (R13, C10), alive-progress #59.
- **What.** `bar.update_to(n)` / `task.set_completed(n)` — set the
  current count to an absolute value instead of the delta-only
  `advance(n)`.
- **Why.** Trivial in C++ (`completed.store(n)` vs `fetch_add`).
  Matches `urllib.urlretrieve(reporthook=...)` / download-progress
  idioms exactly. No reason not to ship.
- **Effort.** ~half a day. Add method to `Task` and `Progress`,
  expose on the C-iterator object.

## 7. Smoothed / EWMA ETA

- **Sources.** tqdm #967 (R12, C11), alive-progress #247.
- **What.** Default ETA uses a sliding-window or EWMA rate, not the
  cumulative average. Opt-in `skip_first_n=` ignores warmup iters.
  Configurable `window=` on `EtaColumn` and `RateColumn`. Already
  planned as Iter 8 in `ITERATIONS.md` for `RateColumn` — extend the
  same ring buffer to drive `EtaColumn`.
- **Why.** Cumulative ETA is wrong on variable-rate jobs (downloads,
  ML training, anything bursty). Ring buffer of `(timestamp,
  completed)` samples on `Task`, sampled by the render thread, kept
  entirely off the hot path.
- **Effort.** ~2 days, or zero marginal effort if folded into Iter 8.

## 8. Multicolor segmented bars

- **Sources.** tqdm #1188 (R10), tqdm #49.
- **What.** `BarColumn` accepts a list of `(fraction, style)`
  segments — one bar shows sub-progress, multi-phase work, or
  per-category breakdown. E.g. `[████░░▒▒    ]` = done / running /
  pending.
- **Why.** Fits the column pipeline naturally. Pairs with state-based
  styles (Iter 7 in `ITERATIONS.md`) and gradient bars (Iter 2).
  Visually distinctive — no other Python progress lib does this
  cleanly.
- **Effort.** ~3 days. Extend `BarColumn` render to walk the segment
  list, emit per-segment SGR runs into the preallocated buffer.

---

## Source issue index

- **tqdm:** #49, #260, #313, #427, #458, #485, #565, #750, #967,
  #1188, #1228, #1264, #1272, #1342, #1514
- **rich:** #2872, #3383, #3466, #3483, #3529, #3543, #3868
- **alive-progress:** #20, #49, #59, #184, #188, #247, #272, #306

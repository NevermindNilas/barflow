# Changelog

All notable changes to **barflow** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Removed

- **Free-threaded CPython 3.13 (`cp313t`) wheels.** Dropped from the build
  matrix across all platforms; `cp314t` remains the supported free-threaded
  target. Non-free-threaded CPython 3.13 (`cp313`) is unaffected and still
  ships on every platform. Users on free-threaded 3.13 can still install from
  the source distribution.

## [0.5.1] — 2026-07-26

### Fixed

- **`from barflow.themes import *` raised `AttributeError`.** `themes.__all__`
  listed six `THEMES` registry *keys* (`rich`, `arrows`, `shade`, `line`,
  `double`, `round`) rather than the functions they alias, and those names are
  not module attributes — so a star-import failed outright. `__all__` now names
  the real functions (`rich_like`, `arrows_march`, `shade_cool`, `line_clean`,
  `double_frame`, `round_retro`). The registry keys are untouched:
  `themes.get("shade")` and `Progress(theme="rich")` behave exactly as before.

### Changed

- **Internal cleanup — no public API change.** Duplicated logic in the C++ core
  collapsed to a single implementation each: the cursor-up escape (six copies),
  the physical-row count that drives the multi-row walk-back (four copies), the
  ANSI/UTF-8 display-cell scan shared by width counting and truncation (two
  copies that had to be kept in sync by hand), and the drop-GIL → lock →
  bounds-check prologue shared by five per-task setters. Dead locals and a
  write-only field removed; `track()` and `atrack()` now share one Progress
  construction path. Net ~290 lines deleted.

## [0.5.0] — 2026-07-08

### Added

- **`reset(task_id=0, total=None)`.** Restart a task in place — counter back to
  0, elapsed/rate/eta re-based to now, completion freeze and rate history
  cleared, optionally a new total installed — so a `Progress` can be reused
  across phases without reconstructing it (tqdm-parity).
- **Postfix annotations (`set_postfix` / `set_postfix_str` / `PostfixColumn`).**
  A tqdm-style trailing `key=value` field: `p.set_postfix(loss=0.031, acc=0.98)`
  renders `… loss=0.031, acc=0.98` after the bar (floats shown to 3 significant
  figures). The default column set carries an invisible postfix column, so it
  works with no custom layout; `PostfixColumn()` places it explicitly.
- **Unit humanization (`unit` / `unit_scale` / `unit_divisor`).** Byte-transfer
  bars: `unit="B", unit_scale=True` renders counts as `1.50M/4.10M` and the
  rate as `3.21M B/s`; `unit_divisor=1024` switches to binary scaling. `unit`
  alone sets the rate noun (`… N B/s`).
- **Smoothed rate (`smoothing=`).** `0` keeps the whole-run average (default,
  unchanged); `(0,1]` reports an exponential moving average of the most recent
  interval's it/s, so a bursty or stalled producer shows a responsive rate and
  ETA. Applies to `Progress`, `track`, and `atrack`.
- **`leave=False`.** Clears the bar area on close instead of leaving the final
  frame + newline — ephemeral bars.
- **`Progress.total` / `Progress.elapsed` getters** (task 0). `total` is `None`
  when unbounded; `elapsed` freezes at completion.
- **`Tracker.__length_hint__`.** `list(track(range(n)))` and other consumers can
  preallocate; reports remaining items (`0` when unbounded).
- **File-object wrapping (`barflow.wrap_file` / `wrapattr`).** Wrap a binary
  stream so every `read`/`write` (also `read1`/`readline`/`readinto`) advances a
  byte-scaled bar; `total` is inferred from `os.fstat` when omitted. Transparent
  proxy — unknown attributes pass through. Mirrors `tqdm.wrapattr` /
  `rich.Progress.wrap_file`.
- **`initial=`.** Resume a partially-done job: the count starts seeded and is
  shown, but rate/eta measure only the work done in this run (tqdm-parity).
- **`set_visible(task_id, visible)`.** Hide or show a task's row while it keeps
  counting — rich's `update(visible=)`.
- **`delay=`.** Suppress the bar until N seconds have elapsed since `__enter__`,
  so a job that finishes quickly never flashes one (tqdm/rich `delay=`). A bar
  that never crosses the window emits nothing on close.
- **`disable=None`.** Auto-disables when stderr is not a TTY (tqdm's
  `disable=None`), so redirected/piped runs don't spray ANSI frames into the
  sink. Default stays `False` (always show).
- **`align=True`.** Right-pads every task's description to the widest one so
  the bar (and everything after it) starts at the same column on every row —
  rich's `Table.grid` alignment, without a table.
- **Finished-task freeze.** A completed task's `elapsed`/rate/eta freeze at the
  moment it reached `total` instead of decaying every frame while other tasks
  keep the render thread alive; re-extending the total past `completed`
  (`set_total`) un-freezes it.

### Fixed

- **Render-thread busy-spin.** A non-positive `min_interval` made
  `render_cv.wait_for(0s)` return immediately every wakeup, pinning a core at
  100%. It is now floored at 1 ms.
- **Clock-period assumption.** `now_ns()` used `steady_clock::…count()` directly,
  which is only nanoseconds by convention on the shipped toolchains; it now
  `duration_cast`s to nanoseconds so the timing is correct on any conforming
  clock period (no measurable cost).

## [0.4.1] — 2026-06-12

### Added

- **Completion receipt (✔).** `SpinnerColumn` now renders a `✔` check mark
  once its task finishes (`completed >= total`), alive-progress style.
  Indeterminate tasks (no total) keep spinning until close. Applies to the
  final frame on `close()` and to every finished row in a multibar.
- **`alive` theme.** Ports alive-progress's classic layout:
  `desc |█████▊▒⠀⠀⠀| ▂▄▆ 42/100 [42%] in 0:03 (...)` — comet-tip bar,
  trailing wave spinner (→ `✔` on completion), count + percent + elapsed +
  rate.

### Changed

- **Default columns got the alive treatment.** A bare `Progress(total=...)` /
  `track(...)` now renders a leading bold-cyan braille spinner (`⠋⠙⠹…`,
  swapping to `✔` when done) and an animated comet tail (`░▒▓█▓▒`) at the
  bar's leading edge while incomplete. Layout is otherwise unchanged
  (`desc: 42% |████▊░ …| 4/10 [el<eta, rate]`); explicit columns and themes
  are unaffected.

## [0.4.0] — 2026-05-30

### Added

- **`pacman` theme reworked + `pacman` bar glyphs.** The `pacman` theme is now a
  Pac-Man munching a row of pellets — eaten path blank behind, `•` pellets
  ahead, and a `ᗧ`→`●` chomping mouth (open wedge snapping shut) animated at the
  leading edge via the bar-tip pipeline. (Replaces the former emoji-ball
  `pacman`.)

- **`Progress.render_line(task_id=0) -> str`.** Renders a task's configured
  columns into a string using the exact live-frame pipeline, but writes
  nothing to the console and has no frame-state side effects. Useful for
  logging a one-shot bar line — and it makes the C render pipeline directly
  testable.
- **`Progress` `__repr__`.** `repr(p)` now reports task-0 state, e.g.
  `Progress(completed=12, total=100, desc='download', tasks=1)`, instead of the
  opaque default object repr.
- **`barflow._core._display_width(s) -> int`.** The renderer's own cell
  accounting, exposed for measuring `render_line()` output and testing glyph
  widths (skips ANSI CSI escapes; counts wide CJK/emoji as 2, combining marks
  and variation selectors as 0).
- **Test suite.** Grew the `pytest` suite to 144 tests. Beyond the pure-Python
  surface (`style` SGR parsing, the `spinners` DSL, `bar_styles`/`columns`
  factories, every `themes` preset, seed-reproducible `random_theme`) and the
  `completed`/`n_tasks`/`CallbackColumn`-snapshot state checks, it now covers
  the render pipeline via `render_line` (bar fill, percent alignment, count
  clamp, every theme), `_display_width` across glyph classes, `capture_output`
  install/uninstall round-trips, out-of-range `task_id` errors, the
  Progress-as-iterator stop-at-total contract, and `atrack` theme/column/early-
  break behaviour. Added a `test` optional-dependency extra and pytest config
  to `pyproject.toml`.

### Fixed

- **Deadlock when a bare `Progress` with a `CallbackColumn` was dropped without
  `close()`.** `Progress.__del__` joined the render thread while holding the
  GIL, but the render thread's final frame re-enters Python (for the callback)
  via the GIL → hard hang. Dealloc now releases the GIL across teardown, like
  `close()`/`__exit__` already did. This also fixes the async early-`break`
  path (`barflow.aio.atrack`), which relies on dealloc-time teardown.
- **`capture_output=True` permanently hijacked `sys.stdout`.** Exhausting a
  `track(..., capture_output=True)` tore the progress down via the C
  `Tracker`'s `close()`, which bypassed the Python `__exit__` that uninstalls
  the stdout/stderr proxy — so `sys.stdout` stayed replaced for the rest of the
  process. `track()` now guards the capture path so `__exit__` always runs (on
  exhaustion, early break, or exception), and `atrack` tears down via `__exit__`.
- **A final newline-less `print(..., end="")` was lost under `capture_output`.**
  `StdoutCapture.uninstall()` now drains the buffered partial line.
- **`close()` after `pause()` repainted the bar over external output.** The
  render thread's final frame ignored the `paused` flag, redrawing the bar on
  top of whatever the external writer had emitted into the cleared area. The
  final frame is now suppressed while paused.
- **Wide glyphs (emoji / CJK) were measured as one cell.** `count_display_cells`
  counted every code point as a single cell, so the shipped emoji themes and
  CJK/fullwidth text mis-sized the multi-row cursor walk-back and the flex-bar
  budget — leaving zombie rows or wrapping the line on narrow/stacked bars.
  Cell counting is now width-aware (East-Asian Wide + emoji = 2, combining
  marks / variation selectors = 0, with VS16 promoting its base), kept
  conservative so 1-cell symbol glyphs (★ ♥ ✦ ◆ braille …) are unaffected.
- **`atrack` ignored `theme=` and bare-string columns** that `track()` accepts
  (it forwarded straight to the C core). It now mirrors `track()`'s fast/slow
  dispatch, so themes, column factories, string shorthand, and `capture_output`
  all work.
- **A flex bar clipped under a pinned width with VT disabled emitted a stray
  `\x1b[0m`** into otherwise escape-free output (e.g. a redirected log). The
  hard-clip reset is now gated on VT being enabled.
- **`track(task_id=N)` / `atrack(task_id=N)` for `N != 0`** raised an opaque
  `IndexError`. Both build a single-task bar, so a non-zero `task_id` now raises
  a clear `ValueError` pointing at `Progress` + `add_task()`.
- **`spinners` factory annotations** referenced undefined `List`/`Sequence`
  names, so `typing.get_type_hints()` raised `NameError`. Switched to runtime-
  resolvable `list[str]` and `collections.abc.Sequence`.
- **Overshoot count display.** The count column now shows `N/N` instead of
  `12/3` when the counter is advanced past the total, matching the already-
  clamped bar/percent (the raw `completed` counter is still reported unclamped).

### Changed

- **Multi-bar `update()` is ~2.5× faster.** `update(task_id, n)` resolves the
  task pointer under `render_mtx`. It now drops the GIL before the lock *only
  when a `CallbackColumn` is present* — that is the sole case where the render
  thread re-enters Python under `render_mtx` (via `PyGILState_Ensure`) and a
  GIL-holding waiter could deadlock. With no callback column it takes the lock
  with the GIL held, skipping the per-call `Py_BEGIN/END_ALLOW_THREADS`
  thread-state save/restore. `has_callback_col` is fixed during single-threaded
  init (before the render thread starts) and columns are immutable after, so the
  read needs no synchronization. Measured **67.4 → 26.4 ms per 1 M `update()`s
  (14.8 → 37.7 M it/s)** on Windows / CPython 3.14, same-harness before/after
  (`bench_multibar.py`); the win is larger on 3.14 because its GIL save/restore
  is costlier. The cold setters (`set_total` / `set_description` /
  `set_task_description` / `add_task`) keep the unconditional GIL drop — they are
  not hot. Guarded by the new `tests/test_update_concurrency.py`, which hammers
  `update()` + `add_task()` under a 1 ms render interval (watchdog-killed on
  hang) for both the callback and no-callback paths and checks counter exactness.
- **Themed / columned `Progress` construction is ~25% cheaper.**
  `_progress.Progress.__init__`, `columns.BarColumn`, and `columns.SpinnerColumn`
  now cache their lazy `from . import …` submodule lookups on first use instead
  of re-running the import machinery (`_handle_fromlist` / `parent`) on every
  call, and the `style.style()` SGR parser is memoized (`functools.lru_cache`,
  bounded). Memoization wraps only the str-parsing core, so the exception
  behaviour for empty / raw-escape / non-str / invalid specs is byte-for-byte
  unchanged. Themed construction **6453 → 4768 ns**, columned (fresh factories)
  **4783 → 3520 ns** (new `benchmarks/bench_construct.py`). Cold `import barflow`
  is unaffected — the submodules are still loaded lazily on first use, never at
  import, and `style` / `functools` stay off the `from barflow import track`
  fast path.
- Render loop is allocation-free per frame again: the per-task `visible_cols`
  and `this_cells` scratch vectors are hoisted into `ProgressState` (reused
  like the other frame buffers), and the delta-cache prime now swaps rather
  than copies each column's rendered bytes.
- Docs: corrected the `disable=True` note in `llms.txt` (it suppresses
  rendering/I-O but does **not** short-circuit the per-iteration atomic), and
  the README feature list (10 column types including the callback column).

## [0.3.1] — 2026-05-24

### Added

- **`random` theme.** `themes.get("random")` (or `random_theme()`) picks a
  distinct real theme on each call. Aliases are collapsed and the pick is
  reproducible under a seeded RNG (insertion-order de-dup, not hash order).

### Changed

- Bumped CI actions (`checkout` v6, `setup-python` v6, `cache` v5,
  `upload-artifact` v7, `download-artifact` v8) and lifted the macOS
  deployment-target floor to 10.15 (cibuildwheel now enforces it; still
  satisfies the aligned-new requirement).

### Fixed

- **Gallery rendering glitches.** `examples/gallery.py` now disables autowrap
  (DECAWM) so double-width emoji bars are clipped at the right margin instead
  of folding onto a second physical row and scrolling the top row off; caps
  each bar to the terminal width using per-glyph cell-width measurement; trims
  the preset block to the rows actually free below the header; and subtracts
  render cost from the frame delay so the real frame rate tracks the target.
- **Deadlock when a render-thread method is called under a `CallbackColumn`.**
  `render_frame` holds `render_mtx` while a `CallbackColumn` re-enters Python
  via `PyGILState_Ensure`. Every Python-facing path that takes `render_mtx`
  *while holding the GIL* — `pause`, `resume`, `set_total`, `set_description`,
  `set_task_description`, `write_above`, plus `update`, `add_task`, the
  `n_tasks` getter, and `Tracker.__init__` — could block on the lock while the
  render thread blocked on the GIL, a lock-order inversion that froze any
  multithreaded use with a callback column. They now release the GIL
  (`Py_BEGIN_ALLOW_THREADS`) around the lock, matching `refresh()`.
  Out-of-range errors are reported after the GIL is reacquired.
- **Stale trailing characters when a column shrinks.** The delta render path
  re-emitted changed columns but never erased to end of line, so a
  variable-width trailing column (e.g. a `CallbackColumn` postfix going from
  `subprocess` to `sqlite3`) left leftover characters (`sqlite3sses`). Each
  delta-rendered row now ends with `\x1b[K` (erase to end of line); the cursor
  is at the true end of content, so already-emitted columns are untouched.
  When a non-flex line that wrapped across multiple physical rows shrinks to
  fewer rows, the surplus old wrapped row(s) — which `\x1b[K` cannot reach —
  are now explicitly erased so they don't persist on screen.

## [0.3.0] — 2026-05-24

### Added

- **`Progress.pause()` / `Progress.resume()`.** Suspend the background
  render thread and clear the bar area so an external writer (an output
  redirector, a threaded tool interleaving prints) can emit lines without
  the autonomous render thread repainting on top of them, then repaint
  the bar below. Without this, host applications that wrap their own
  output in a "pause the bar" block — e.g. tqdm's `external_write_mode`
  equivalent — could not stop barflow's timer-driven render thread and
  saw torn output under concurrency. `pause()` only emits the erase when
  `vt_enabled`; both are no-ops when the bar is disabled or closed.

## [0.2.3] — 2026-05-24

### Changed

- **Lowered the minimum Python to 3.10** (was 3.13). The C core already
  version-gated its only 3.12+ fast-path API (`_PyLong_IsCompact` /
  `_PyLong_CompactValue`) behind `PY_VERSION_HEX` with a public-API
  fallback, and the free-threaded `PyUnstable_Module_SetGIL` call is
  guarded by `Py_GIL_DISABLED`, so nothing blocked older interpreters.
  `requires-python`, the PyPI classifiers, the README, and the
  cibuildwheel matrix now cover CPython 3.10–3.14. Verified by building
  and smoke-testing the extension on 3.10, 3.11, and 3.12.

## [0.2.2] — 2026-04-27

### Added

- **Performance tips and hot-path invariants in `llms.txt`.** New
  "Performance tips & best practices" section captures the producer
  cacheline contract, `memory_order_relaxed` rationale, render-thread
  GIL discipline, and contributor rules for `_core.cpp` so future
  changes don't accidentally regress the hot path.
- **Greatly expanded preset libraries.** ~43 new theme factories in
  `themes.py` (`vaporwave`, `synthwave`, `lightning`, `plasma`,
  `acid`, `midnight`, `ember`, `amber_crt`, `miami`, `gold_rush`,
  `alien`, `deep_sea`, `magma`, `void`, `chevron`, …); ~17 new
  spinner frame sets in `spinners.py` (`pulse`, `spark`, `thunder`,
  `diamond`, `wedges`, `hex`, `moon`, `weather`, `rocket`,
  `heartbeat`, `glitch`, `loading`, `slash`, `caret`, …); additional
  glyph dictionaries in `bar_styles.py`.

### Changed

- **Render thread does fewer per-frame UTF-8 walks.** Per-column cell
  widths (`count_display_cells`) are now filled inline as each column
  is rendered and reused by the delta-emit and flex-collapse paths,
  eliminating a redundant measure pass that ran every frame
  (`_core.cpp`).
- **Column-pipeline flags cached on `ProgressState`.**
  `has_spinner_col`, `has_callback_col`, and `flex_bar_idx` are
  computed once at column setup. `render_frame` and `render_loop` no
  longer re-scan `st->columns` on every frame and every condition-
  variable wakeup (`_core.cpp`).
- **`types.SimpleNamespace` import is now lazy.** The C extension
  loads `types` on first `CallbackColumn` render rather than at
  module-init, so users who never construct a callback column don't
  pay the `import types` cost on `import barflow` (`_core.cpp`).
- **Iter 3 (auto-width bars) marked done in `ITERATIONS.md`** —
  retroactively checked off after verifying the flex-bar path was
  already implemented across earlier column work.
- **`__version__` bump** + `llms.txt` drift fixes.

### Removed

- **Profile-Guided Optimization (PGO) infrastructure.** PGO did not
  produce a measurable speedup vs. the plain `/O2 /Ob3 /GL /LTCG`
  release build, and the maintenance overhead (instrumented build
  step, training workload, separate Windows/POSIX driver scripts,
  cibuildwheel orchestration) was not justified. Removed:
  `build_pgo.bat`, `build_pgo.sh`, `benchmarks/pgo_train.py`,
  `.github/scripts/cibw_pgo_train.sh`, `BARFLOW_PGO`/`BARFLOW_PGO_DIR`
  env-var handling in `setup.py`, the `CIBW_BEFORE_BUILD_LINUX` +
  `CIBW_ENVIRONMENT_LINUX` PGO entries in `wheels.yml`, and all PGO
  references from `llms.txt`. Wheels now ship as plain release
  builds.
- **Dead `kBlockChars[9]` array** in `_core.cpp` — vestige from the
  pre-glyph design, never referenced after the move to per-column
  glyph tables.

## [0.2.1] — 2026-04-11

### Added

- **Free-threaded CPython wheels** (`cp313t`, `cp314t`) for Windows
  (AMD64), macOS (x86_64 + arm64), and Linux (manylinux + musllinux,
  x86_64 + aarch64). `pip install barflow` on a no-GIL build now
  resolves a pre-compiled wheel instead of falling back to sdist.
- **Native ARM Linux runners.** Linux aarch64 wheels build on
  `ubuntu-24.04-arm` instead of running the manylinux container
  under QEMU on an x86 host. Per-wheel build time drops from
  ~10 minutes to ~2 minutes.
- **Changelog-driven release notes.** The `Build wheels` workflow
  extracts the matching section from `CHANGELOG.md` and uses it as
  the body of the GitHub release, and attaches every built wheel
  plus the sdist to the release assets.

### Changed

- Merged `wheels-freethreaded.yml` into `wheels.yml` as a single
  matrix so both regular and free-threaded wheels go through one
  `build → publish → release` pipeline.
- PyPI publish step now uses `skip-existing: true`, so re-running
  the workflow on an already-published tag is a no-op instead of a
  hard failure.
- Cleaned up `[tool.cibuildwheel]` in `pyproject.toml`: per-arch
  settings come from the matrix via `CIBW_ARCHS`, and the `pp*`
  skip rule is gone (PyPy is disabled by default in
  cibuildwheel 3.x).

## [0.2.0] — 2026-04-11

Initial public release.

### Added

- **C++ core (`_core.cpp`).** Hot path for `tick` / `advance` /
  `Tracker.tp_iternext` is a single `std::atomic::fetch_add` with
  no locks. A background render thread wakes on a condition
  variable timeout, snapshots the atomic, runs the column pipeline,
  and writes to the terminal via `WriteConsoleW` on Windows
  (UTF-16 transcoded) or `write(2)` on POSIX.
- **`barflow.track(iterable)`.** Zero-overhead iterator wrapper —
  `for _ in track(range(n))` runs at ~160 M it/s, below the bare
  `for _ in range(n)` baseline because `FOR_ITER` dispatches
  directly to `tp_iternext` (no vectorcall trampoline) and
  `Py_None` is immortal on 3.12+.
- **Multi-task progress stacks.** `add_task(total, desc)` returns a
  task id; bars render as a stack with ANSI cursor-up between
  frames.
- **Column pipeline.** Nine built-in column types handled entirely
  in C++, configured from Python via a list of column tuples.
- **`write_above(text)` primitive.** Acquires the render mutex,
  walks to the top of the bar area, clears to end-of-screen, emits
  user text, and notifies the render thread to repaint. Lets
  Python `print()` calls interleave cleanly with live bars.
- **Async iteration.** `barflow.aio` for awaitable progress over
  async iterables.
- **Theme and spinner libraries** plus a small style module.
- **Wheels.** CPython 3.13 and 3.14 on Windows (AMD64), macOS
  (x86_64 + arm64), and Linux (manylinux_2_28 + musllinux_1_2,
  x86_64 + aarch64). Source distribution published alongside.

[Unreleased]: https://github.com/NevermindNilas/barflow/compare/v0.5.1...HEAD
[0.5.1]: https://github.com/NevermindNilas/barflow/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/NevermindNilas/barflow/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/NevermindNilas/barflow/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/NevermindNilas/barflow/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/NevermindNilas/barflow/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/NevermindNilas/barflow/compare/v0.2.3...v0.3.0
[0.2.3]: https://github.com/NevermindNilas/barflow/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/NevermindNilas/barflow/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/NevermindNilas/barflow/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/NevermindNilas/barflow/releases/tag/v0.2.0

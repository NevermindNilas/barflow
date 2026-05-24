# Changelog

All notable changes to **barflow** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Test suite.** First `pytest` suite (89 tests) covering the pure-Python
  surface — `style` SGR parsing, the `spinners` DSL, `bar_styles`/`columns`
  factories, every `themes` preset resolving, seed-reproducible `random_theme`
  — plus core behavior reachable from Python: counter/multi-task state via the
  `completed`/`n_tasks` getters, and computed `percentage`/`fraction` (zero-total
  sentinel, overshoot clamp) read through a `CallbackColumn` snapshot. Added a
  `test` optional-dependency extra and pytest config to `pyproject.toml`.

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

[Unreleased]: https://github.com/NevermindNilas/barflow/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/NevermindNilas/barflow/compare/v0.2.3...v0.3.0
[0.2.3]: https://github.com/NevermindNilas/barflow/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/NevermindNilas/barflow/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/NevermindNilas/barflow/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/NevermindNilas/barflow/releases/tag/v0.2.0

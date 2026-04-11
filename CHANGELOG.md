# Changelog

All notable changes to **barflow** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/NevermindNilas/barflow/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/NevermindNilas/barflow/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/NevermindNilas/barflow/releases/tag/v0.2.0

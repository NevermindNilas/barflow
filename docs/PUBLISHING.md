# Publishing BarFlow to PyPI

This document describes the one-time setup and the per-release checklist
for publishing a new version of `barflow` to PyPI.

We use **PyPI Trusted Publishers** (OIDC), so releases do **not** need
long-lived API tokens stored as secrets. The GitHub Actions workflow
authenticates to PyPI using a short-lived OIDC token issued by GitHub.

## One-time setup

### 1. Reserve the name on PyPI

1. Create an account on https://pypi.org if you don't have one.
2. Go to https://pypi.org/manage/account/publishing/.
3. Scroll to **Add a pending publisher**.
4. Fill in:
   - **PyPI Project Name:** `barflow`
   - **Owner:** `NevermindNilas`
   - **Repository name:** `barflow`
   - **Workflow name:** `wheels.yml`
   - **Environment name:** `pypi`
5. Click **Add**.

PyPI will remember this "pending" publisher. When the first release is
pushed from the matching workflow, PyPI registers the project under
your account.

### 2. Create the `pypi` GitHub Environment

1. Go to your repo settings → **Environments** → **New environment**.
2. Name it exactly `pypi` (matches `environment: name: pypi` in
   `.github/workflows/wheels.yml`).
3. Optionally add protection rules (required reviewers, deployment
   branch restriction to tags matching `v*`).

### 3. Test on TestPyPI first (recommended)

Repeat step 1 on https://test.pypi.org/manage/account/publishing/ with
the same project name but a different environment (e.g. `testpypi`),
then add a second `publish` job in the workflow that points at
`https://test.pypi.org/legacy/` before flipping the real one on. Skip
this if you trust the local `twine check` pass.

## Per-release checklist

1. **Bump the version.** Edit `pyproject.toml`:

   ```toml
   [project]
   version = "0.2.1"
   ```

   Use semver. Match the tag name.

2. **Update `benchmarks/results.md`** if you've touched the hot path,
   and re-run the benchmark harness locally:

   ```
   set PYTHONPATH=src
   python benchmarks/bench.py --n 20000000 --runs 5
   ```

3. **Local dry run.** Build the sdist + wheel and run twine check:

   ```
   python -m pip install --upgrade build twine
   python -m build
   python -m twine check dist/*
   ```

   Inspect `dist/barflow-0.2.1.tar.gz` to confirm it contains
   `src/barflow/_core.cpp` and all `.py` files. An sdist missing the
   C++ source is unbuildable by downstream users and is the single most
   common cause of failed Linux installs.

4. **Commit and tag.**

   ```
   git add pyproject.toml benchmarks/results.md
   git commit -m "Release v0.2.1"
   git tag v0.2.1
   git push origin main v0.2.1
   ```

5. **Watch the workflow.** The `build_wheels` and `build_sdist` jobs
   run on every tag push. When they succeed, the `publish` job runs
   (gated by the `pypi` environment). Approve if protection rules
   require it.

6. **Verify.** After publish:

   ```
   pip install barflow==0.2.1
   python -c "import barflow; list(barflow.track(range(1000)))"
   ```

   Confirm the version and benchmarks on a clean venv.

## Troubleshooting

- **"Trusted publisher not configured"** — the PyPI pending publisher
  entry doesn't exactly match the workflow. Check owner, repo,
  workflow filename, and environment name. All four must match
  character-for-character.
- **"Project name conflict"** — someone took `barflow` after we
  verified. Rerun the name availability check and pick again.
- **sdist missing `_core.cpp`** — `MANIFEST.in` wasn't read.
  `setuptools>=61` uses `MANIFEST.in` automatically when
  `include-package-data = true` or no `package-data` is set; verify
  `python -m build` logs show MANIFEST.in being picked up.
- **Wheel build fails on Linux aarch64** — cibuildwheel uses QEMU
  emulation for non-native archs; this is slow (~15 min per wheel) but
  works. If it fails with a linker error, add the arch to
  `[tool.cibuildwheel.linux] before-build` to install `g++` explicitly.
- **Pre-commit hook failures** — not applicable (no hooks). Keep it
  that way.

## Rollback

You **cannot** delete a released version from PyPI (only yank it,
which hides it from `pip install barflow` without `==` but leaves
wheels downloadable). If you publish a bad version:

1. `pip yank` via `twine upload --yank` is not supported. Use the PyPI
   web UI: project page → Manage → Releases → Yank.
2. Bump the version and publish a fix. Never reuse a version number.

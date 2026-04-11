# BarFlow customizability iterations

Running task: *"Improve the customizability of the progress bar with
customizable coloring, length, data and so forth."* — `ralph-loop`,
max 17 iterations. Each iteration below is a self-contained, tested,
benchmark-verified increment. **Future iterations should read this
file first**, pick the next unchecked item, and avoid redoing done
work.

Iters 1–10 are the original customizability roadmap. Iters 11–16 are
feature-gap additions sourced from open issues across `tqdm`, `rich`,
and `alive-progress` — see `docs/FEATURE_REQUESTS.md` for full
rationale, source issues, and effort estimates. Iter 17 is a second
final-pass that audits 11–16 the same way Iter 10 audits 1–9. Two of
the 8 entries in `FEATURE_REQUESTS.md` (`indeterminate / pulsing bar`,
`smoothed ETA`) are already absorbed into Iter 9 and Iter 8
respectively.

## Roadmap (17 iterations)

- [x] **Iter 1.** Rich styling — style spec parser (hex, 256-color,
      named, bg, bold/dim/italic/underline/blink/reverse/strike),
      universal per-column style wrapping in C++, `style=` kwarg on
      every factory, backward-compat `color=` alias.
- [ ] **Iter 2.** Gradient bars — `BarColumn(style_start=..., style_end=...)`
      that interpolates RGB along the bar length; per-glyph SGR on the
      render path.
- [ ] **Iter 3.** Auto-width — `BarColumn(width="auto")` or `width=-1`
      that fills remaining terminal width; query
      `GetConsoleScreenBufferInfoEx` / `TIOCGWINSZ` cached in
      `ProgressState`, re-query on window resize.
- [x] **Iter 4.** Custom bar glyphs — done out of order ahead of
      iters 2–3 in response to an explicit user request for
      "looks + presets". `BarColumn(glyphs=…)` accepts a name or dict
      of `{fill, empty, partials, left, right}`; the C++ Column struct
      now carries those fields and `render_column` emits them
      verbatim. 16 built-in glyph sets in `barflow/bar_styles.py`
      (smooth, blocks, shade, ascii, equals, line, double, round,
      dots, braille, arrows, sharp, stars, hearts, pipes, pipe). The
      themes registry grew from 5 → **27 named presets** covering
      utilitarian, ASCII-safe, colorful, and playful categories. New
      demo `examples/themes_showcase.py` with `--list` / `--only`
      flags.
- [ ] **Iter 5.** Task fields + format strings — per-task
      `fields: dict` bag, `TextColumn("{speed} files/s")` substitution
      evaluated on render thread. Columns get a `format:` argument for
      printf-style control.
- [ ] **Iter 6.** DataSizeColumn + TransferSpeedColumn — IEC/SI byte
      scaling (kB / KiB / MB / MiB / …) for download bars, plus
      `unit=` argument on CountColumn/RateColumn for generic unit
      labels.
- [ ] **Iter 7.** State-based styles — `BarColumn(styles={"pending":
      "dim", "running": "cyan", "done": "green", "error": "red"})`
      switching on task state; tracks a `state` field on Task.
- [ ] **Iter 8.** Smoothed rate (EMA) — ring buffer of
      (timestamp, completed) samples on Task; `RateColumn(window=5)`
      renders a smoothed it/s instead of cumulative. Keep hot path
      free of the ring.
- [ ] **Iter 9.** Bar fill styles — `BarColumn(fill_style="solid" |
      "gradient" | "striped" | "pulse" | "blocks")` + animated pulse
      frame for indeterminate total.
- [ ] **Iter 10.** Final pass — tests, demo script showing every
      customization, update docs/DESIGN.md §5 with the new API,
      update README example gallery, rerun full benchmarks, verify
      nothing in iter 1–9 regressed hot path below 3.5 ns/iter on
      `track()`.
- [ ] **Iter 11.** PEP 561 type stubs — ship `py.typed` marker plus
      complete `.pyi` for `track`, `Progress`, every column factory,
      spinner DSL, themes, `aio.atrack`. Wire into `pyproject.toml`
      and `MANIFEST.in`. Verify with mypy + Pyright on the example
      gallery. Source: tqdm #260 (R40, C34 — #1 tqdm request).
- [ ] **Iter 12.** `update_to(n)` absolute-value API — add
      `Progress.update_to(task, n)` and `Tracker.update_to(n)` that
      `store()` instead of `fetch_add()`. Matches
      `urllib.urlretrieve(reporthook=...)` idiom. Source: tqdm #1264,
      alive-progress #59. Trivial; ~half a day.
- [ ] **Iter 13.** Non-TTY / file-redirect mode — `isatty()` probe at
      `Progress.__enter__`; alternate render path emits
      newline-terminated lines on a slower (~1 s) cadence instead of
      `\r`-spam when stdout is a file/pipe/CI log. Add
      `BARFLOW_DISABLE=1` and `NO_PROGRESS=1` env kill-switches plus
      a `barflow.disable()` global mute. Source: tqdm #750 (R19),
      #1514, #565, #1342.
- [ ] **Iter 14.** `logging` module integration —
      `barflow.logging.BarFlowHandler` (subclass of
      `logging.StreamHandler`) routes records through
      `write_above()` so log lines render above live bars without
      tearing. `with barflow.redirect_logging(): ...` context manager
      swaps existing root-logger handlers for the duration of a bar
      and restores on exit. Source: tqdm #313 (R22, C28), tqdm #1272
      (R16, C13), alive-progress #272 — biggest cross-repo pain
      point.
- [ ] **Iter 15.** Multicolor segmented bars — `BarColumn` accepts a
      list of `(fraction, style)` segments so a single bar can show
      sub-progress, multi-phase work, or per-category breakdown
      (`[████░░▒▒    ]` = done / running / pending). Render walks
      the segment list and emits per-segment SGR runs into the
      preallocated buffer. Pairs with Iter 7 (state styles) and Iter
      2 (gradient). Source: tqdm #1188, #49.
- [ ] **Iter 16.** Multiprocessing / worker-pool bars — back the
      atomic `completed` counter with `multiprocessing.shared_memory`
      so child processes can `fetch_add()` losslessly into a parent's
      live render. `Progress.add_task(..., shared=True)` returns a
      picklable handle. Windows `CreateFileMapping` path, POSIX
      `shm_open` path. Fixes tqdm's notorious `process_map` 0%-stuck
      bug — BarFlow's decoupled-renderer architecture is uniquely
      suited. Source: tqdm #1228 (R18), #485, rich #3529. Largest
      iteration; budget ~1 week.
- [ ] **Iter 17.** Final pass v2 — re-run the iter 10 final pass
      across iters 11–16 as well: tests for stubs/logging/non-TTY/
      multiprocessing/segmented/`update_to`, demo script extension,
      `docs/DESIGN.md` updates, README gallery additions, full
      `--n 20000000 --runs 5` benchmarks, hot-path regression check.

## Iter 1 — done

**What changed**

- New file `src/barflow/style.py` — a ~170-line SGR parser. Grammar:
  whitespace-separated tokens, named fg/bg colors (17 + bright
  variants), `#rgb` / `#rrggbb` hex → truecolor SGR, `color(N)` → 8-bit
  indexed, text styles (`bold`/`dim`/`italic`/`underline`/`blink`/
  `reverse`/`strike`), backgrounds via `on <color>` or `on_<color>`.
  Raw `\x1b` escapes pass through unchanged.
- `src/barflow/columns.py` — every factory now accepts `style=` (and
  `color=` as a backward-compat alias). Both names route through
  `style.style()` which returns the SGR prefix. `BarColumn`'s default
  is `"cyan"`, everything else defaults to no style.
- `src/barflow/_core.cpp` — `render_column` now universally wraps
  every column's output with `col.color` (the SGR prefix) and a
  trailing `\x1b[0m` reset. Previously only `COL_BAR` did that; other
  columns ignored their style field entirely. The inline color
  handling inside `COL_BAR` was removed to avoid double-emitting.

**What works**

14/14 style parser unit tests pass. Integration-tested with a mix of:
`SpinnerColumn(style='bold yellow')`, `DescriptionColumn(style='bold
#88ccff')`, `BarColumn(style='bold #ff8800')`, `PercentColumn(style=
'bright_green')`, `RateColumn(style='dim italic')` — all render
correctly in Windows Terminal.

**Benchmarks** (N=5M, 3 runs, best)

| Variant         | Before iter 1 | After iter 1 | Δ |
| --------------- | ------------: | -----------: | ---: |
| `track()`       |       99.02 M |      99.28 M | +0.3% |
| `.tick()`       |       64.06 M |      67.05 M | noise |
| display ON      |       94.78 M |      90.47 M | −4.5% |

The display-on dip is the cost of the universal style wrap: at ~14
columns × 20 fps × ~8 bytes each (SGR prefix + reset), the render
thread appends ~2.2 KB more per frame. Still 5.6× tqdm's display-on
rate. Hot path (`track()` / `.tick()`) is unchanged — style is
applied on the render thread only, never on the producer.

**How to try it**

```python
import barflow
from barflow.columns import (
    SpinnerColumn, DescriptionColumn, BarColumn,
    PercentColumn, CountColumn, RateColumn,
)

with barflow.Progress(
    SpinnerColumn(style="bold yellow"), " ",
    DescriptionColumn(style="bold #88ccff"), ": ",
    BarColumn(width=30, style="bold #ff8800"), " ",
    PercentColumn(style="bright_green"), "  ",
    CountColumn(style="dim"), " ",
    RateColumn(style="italic"),
    total=1000, desc="colorful",
) as p:
    for _ in range(1000):
        p.tick()
```

## Iter 4 — done (out of order, ahead of iters 2 and 3)

**What changed**

- **`src/barflow/_core.cpp`**
  - `Column` struct gained five fields:
    `fill`, `empty_ch`, `partials[]`, `left_border`, `right_border`.
    (`empty` would collide with STL members on some headers, hence
    `empty_ch`.)
  - `default_glyphs::apply()` helper populates the 8-level smooth
    block defaults for BAR columns that don't specify glyphs.
  - `parse_columns` accepts 5- **or** 6-tuple shapes. The 6th slot,
    when present, is `None` or `(fill, empty, partials, left, right)`.
    Non-bar columns ignore the slot; bar columns without an explicit
    spec get `default_glyphs::apply()`.
  - `render_column` case `COL_BAR` now uses the column's own
    `fill`/`empty_ch`/`partials`/`left_border`/`right_border` instead
    of hardcoded `kBlockChars`. Partial mapping scales the 0–7
    eighth-step onto an N-element partials list (falls back to
    round-up/round-down when partials is empty).
  - Unrelated but shipped in the same commit: `render_frame` now
    emits `\r\n` between task lines (previously `\n`) so multi-task
    stacks render correctly even with `DISABLE_NEWLINE_AUTO_RETURN`
    re-enabled by some other code path, and `write_above` normalises
    its trailer to `\r\n`. Same fix we shipped earlier for the
    multi-task bug — now robust to the console mode flag.
  - `install_default_columns` applies glyph defaults to the built-in
    BAR column so the fallback path still renders.

- **`src/barflow/bar_styles.py`** (new) — 16 glyph presets. Each is
  a dict with `fill`, `empty`, `partials`, `left`, `right`. Helper
  `to_tuple()` serializes to the 5-tuple the C core expects and
  merges user dicts against the smooth defaults.

- **`src/barflow/columns.py`** — `BarColumn(glyphs=…)` parameter. The
  factory now returns a 6-tuple `(type, text, width, frames, style,
  glyphs_tuple)`. `resolve_columns()` accepts both 5- and 6-tuple
  shapes so legacy user code still works.

- **`src/barflow/themes.py`** — rewritten. 27 named presets grouped
  by category:
  - **Utilitarian**: classic, minimal, rich/rich_like, spinner, mono,
    ghost
  - **ASCII / legacy**: ascii, equals, brackets
  - **Colorful**: neon, pastel, retro, matrix, fire, ocean, ice,
    sunset, forest, cyberpunk
  - **Playful / themed**: hearts, stars, arrows, pipes, shade, line,
    double, round
  - Module-level `names()` returns deduped names (aliases collapsed),
    `get(name)` raises `ValueError` with available list on miss.

- **`examples/themes_showcase.py`** (new) — theme gallery with
  `--list`, `--only <names...>`, `--n`, `--delay`. Each theme shows a
  bright-white header label so users can match visuals to names.

**Smoke test result**: all **27 themes** instantiate + run their
render pipeline without error (`disable=True` path confirms
structure; `themes_showcase.py` runs the live path).

**Benchmarks** (N=5M, 3 runs, best)

| Variant     | Before iter 4 | After iter 4 | Δ |
| ----------- | ------------: | -----------: | ---: |
| `track()`   |      99.28 M  |     96.83 M  | −2.5% (noise) |
| `.tick()`   |      67.05 M  |     65.15 M  | noise |
| display ON  |      90.47 M  |     96.14 M  | +6.3% |

Display-on *improved* slightly — the custom-glyph render loop uses
one `buf.append(string)` per cell (same as before) but the hot
allocator is now exercising one-character glyphs mostly, which is
cache-friendly. Hot path unchanged.

**How to try it**

```
# List all 27 themes
python examples/themes_showcase.py --list

# Show the whole gallery
python examples/themes_showcase.py

# Pick a favourite
python examples/themes_showcase.py --only cyberpunk fire neon matrix

# Use a theme in your own code
import barflow
for x in barflow.track(range(1000), desc="build", theme="cyberpunk"):
    ...

# Custom glyphs without a theme
from barflow.columns import BarColumn, DescriptionColumn, PercentColumn
with barflow.Progress(
    DescriptionColumn(style="bold #ff69b4"), " ",
    BarColumn(width=25, style="bold #ff1493", glyphs="hearts"), " ",
    PercentColumn(style="bold #ff69b4"),
    total=100, desc="affection",
) as p:
    for _ in range(100): p.tick()
```

## Notes for future iterations

- **Don't touch the hot path.** `Progress.tick`, `Progress.advance`,
  `Tracker.tp_iternext`. Everything styling-related lives on the
  render thread which fires at 20 Hz.
- **Keep the `color=` alias.** Users may have written code against
  it. Deleting it is a breaking change and not worth the noise.
- **Benchmark after every iteration** with `--n 5000000 --runs 3`
  quick-check. If `track()` drops below ~95 M it/s, investigate
  before continuing. Full `--n 20000000 --runs 5` on iter 10.
- **When adding column fields** (iter 5, 6, 7), extend the 5-tuple
  carefully — any shape change breaks existing user code. Prefer
  adding fields to `Column` in C++ and packing them into a new tuple
  slot whose absence means default.

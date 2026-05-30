"""Gallery — every preset rendering at once, side-by-side.

Inspired by alive-progress's `showtime`. Every selected preset gets
its own row; all rows redraw in the same animation frame so the
terminal looks like a wall of bars all racing simultaneously.

Each row pulls the preset's bar glyphs, color style, spinner frames,
and description style straight from `barflow.themes` so what you see
matches `barflow.Progress(theme=name)` exactly.

Run from any cwd:
    python examples/gallery.py
    python examples/gallery.py --section neon
    python examples/gallery.py --section emoji --fps 30
    python examples/gallery.py --only vaporwave hacker rocket_emoji
    python examples/gallery.py --list
    python examples/gallery.py --duration 8 --fps 24

Record as a GIF (requires `vhs` from charm.sh):
    vhs examples/gallery.tape   # → examples/gallery.gif

Tips:
    - Resize your terminal tall enough to fit every row.
    - 24-bit truecolor terminal recommended for the neon palette.
    - Emoji presets need an emoji-capable font (Win Terminal, iTerm2,
      modern gnome-terminal, kitty, alacritty + Noto Emoji, etc.).
"""

from __future__ import annotations

import argparse
import random
import shutil
import sys
import time
import unicodedata
from pathlib import Path

_REPO_SRC = Path(__file__).resolve().parent.parent / "src"
if _REPO_SRC.is_dir() and str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

# Force UTF-8 on Windows so emoji + box-drawing glyphs don't crash cp1252.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from barflow import themes  # noqa: E402
from barflow._core import (  # noqa: E402
    COL_BAR, COL_SPINNER, COL_DESCRIPTION, COL_PERCENT, COL_TEXT,
)


RESET = "\x1b[0m"


# Curated lineups per section. Skip themes that need rate/eta columns to
# look right (classic, downloading, etc.) — gallery is bar-focused.
SECTIONS: dict[str, list[str]] = {
    "neon": [
        "vaporwave", "synthwave", "lightning", "plasma", "acid",
        "midnight", "ember", "amber_crt", "miami", "gold_rush",
        "alien", "deep_sea", "magma", "void", "chevron",
        "rail_neon", "slash", "neon", "cyberpunk",
    ],
    "ascii": [
        "hacker", "binary", "curly", "march", "wave", "rail_ascii",
        "ascii", "equals", "brackets",
    ],
    "emoji": [
        "fire_emoji", "rocket", "sakura", "storm",
        "sparkle", "heart_emoji", "moon", "weather",
    ],
    "brand": [
        "github_dark", "discord", "dracula", "solarized", "nord", "gruvbox",
    ],
    "playful": [
        "hearts", "stars", "arrows", "pacman", "pipes", "shade",
        "line", "double", "round", "matrix",
        "fire", "ocean", "ice", "sunset", "forest",
    ],
    "all": [],  # filled below
}
SECTIONS["all"] = (
    SECTIONS["neon"] + SECTIONS["ascii"] + SECTIONS["emoji"]
    + SECTIONS["brand"] + SECTIONS["playful"]
)


# ----- Column extraction --------------------------------------------------

def extract(cols):
    """Pull bar glyphs, bar style, spinner frames + style, desc style.

    Returns dict with keys: bar_width, bar_ansi, bar_glyphs (5-tuple),
    spinner_frames (list[str]|None), spinner_ansi (str), desc_ansi (str),
    prefix_text (str), prefix_ansi (str).
    """
    out = {
        "bar_width": 30,
        "bar_ansi": "",
        "bar_glyphs": ("█", " ", [], "", ""),
        "bar_tip": [],
        "spinner_frames": None,
        "spinner_ansi": "",
        "desc_ansi": "",
        "prefix_text": "",
        "prefix_ansi": "",
    }
    for col in cols:
        kind = col[0]
        if kind == COL_BAR:
            w = col[2]
            out["bar_width"] = 30 if w is None or w < 0 else w
            out["bar_ansi"] = col[4] or ""
            out["bar_glyphs"] = col[5]
            # 7th element (when present) is the animated leading-edge tip.
            out["bar_tip"] = list(col[6]) if len(col) >= 7 else []
        elif kind == COL_SPINNER:
            out["spinner_frames"] = col[3]
            out["spinner_ansi"] = col[4] or ""
        elif kind == COL_DESCRIPTION:
            out["desc_ansi"] = col[4] or ""
        elif kind == COL_TEXT and not out["prefix_text"]:
            out["prefix_text"] = col[1] or ""
            out["prefix_ansi"] = col[4] or ""
    return out


# ----- Layout planning ----------------------------------------------------

def plan_layout(all_parts, name_width, term_cols):
    """Pick one bar display width for every row and size each theme's body so
    its bar never overflows. Returns `bar_display`.

    `bar_display` is the bar width (body + borders, in terminal columns) shared
    by every row, capped to the terminal. Per-theme bar widths made the right
    edge ragged, and a wide-glyph bar at its full theme width (lightning's
    ⚡ × 30 = 60 cols) overflowed the margin entirely.

    Each theme's body-cell count is sized against the WIDEST body glyph
    (fill/empty/partials — some themes mix widths, e.g. lightning ⚡=2, ·=1),
    so body + borders never exceeds `bar_display` at any fill; render_row
    right-pads the rendered bar so right edges + the percent column line up.
    """
    all_parts = list(all_parts)

    # row = name " " bar " " "100%" + 1-col right margin.
    overhead = name_width + 1 + 1 + 4 + 1
    bar_display = max(8, min(40, term_cols - overhead))

    for p in all_parts:
        fill, empty, partials, left, right = p["bar_glyphs"]
        # The tip occupies the boundary cell, so its glyphs count toward the
        # widest body glyph when sizing the body so a wide tip can't overflow.
        glyph_w = max([cell_width(fill) or 1, cell_width(empty) or 1]
                      + [cell_width(x) for x in partials]
                      + [cell_width(x) for x in p.get("bar_tip", [])])
        border_w = cell_width(left) + cell_width(right)
        p["bar_width"] = max(1, (bar_display - border_w) // glyph_w)

    return bar_display


# ----- Per-row renderer ---------------------------------------------------

def cell_width(s):
    """Display columns a glyph string occupies in a terminal.

    Emoji and CJK render two columns wide; combining marks and ZWJ add none.
    Over-counting is safe here (the bar just ends a hair short); under-counting
    is not (the row overflows and the percent clips), so anything in the emoji
    planes is treated as width 2.

    Variation-selector-16 (U+FE0F) is the tricky case: some terminals compose
    `base + VS16` into a single 2-wide emoji, others paint the base glyph and
    then a separate placeholder cell for the selector (so `⚡️` becomes ⚡ + a
    blank, ~3 columns). We can't detect which, so we count VS16 as an extra
    cell — the over-counting direction. That guarantees no overflow on the
    placeholder terminals (where the storm bar's ⚡️/☁️ were running off the
    right edge); on composing terminals the bar just ends a touch short.
    """
    w = 0
    for ch in s:
        cp = ord(ch)
        if cp == 0xFE0F:            # VS16 — count a placeholder cell (worst case)
            w += 1
            continue
        if unicodedata.combining(ch) or cp in (0x200D, 0xFE0E):  # ZWJ, text VS
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") or cp >= 0x1F000 else 1
    return w


def build_bar(glyphs, width, fraction, tip=(), tick=0):
    """Build one bar string from a 5-tuple glyphs spec at given fill fraction.

    When `tip` is non-empty and the bar is incomplete, the boundary cell
    cycles through the tip frames by `tick` instead of showing a static
    partial — mirroring the C core's animated leading edge so the wall looks
    like a live `barflow.Progress(theme=...)`.
    """
    fill, empty, partials, left, right = glyphs
    cells = max(1, width)
    levels = len(partials) + 1
    total = cells * levels
    filled = int(fraction * total + 0.5)
    full_cells = min(cells, filled // levels)

    body = fill * full_cells
    remaining = cells - full_cells
    if tip and fraction < 1.0 and remaining > 0:
        body += tip[tick % len(tip)]
        remaining -= 1
    else:
        partial_idx = filled % levels
        if partial_idx > 0 and remaining > 0:
            body += partials[partial_idx - 1]
            remaining -= 1
    body += empty * remaining
    return f"{left}{body}{right}"


def render_row(name, parts, fraction, name_width, bar_display, tick=0):
    """Render a single preset row in a fixed grid that stacks vertically:
        [name (name_width)] [bar (bar_display)] [pct]
    Every row starts with the name (no per-theme spinner prefix, which made
    the left edge ragged and flickered for animated spinners like thunder),
    and the rendered bar is right-padded to `bar_display` display columns so
    bar right edges and the percent column line up regardless of glyph width.
    """
    name_label = f"\x1b[1;97m{name:<{name_width}}{RESET}"

    bar_str = build_bar(parts["bar_glyphs"], parts["bar_width"], fraction,
                        parts.get("bar_tip", ()), tick)
    bar_pad = " " * max(0, bar_display - cell_width(bar_str))
    bar_core = f"{parts['bar_ansi']}{bar_str}{RESET}" if parts["bar_ansi"] else bar_str
    bar_part = f"{bar_core}{bar_pad}"

    pct = f"{int(fraction * 100):3d}%"
    pct_color = "\x1b[1m" if fraction < 1.0 else "\x1b[1;92m"
    pct_part = f"{pct_color}{pct}{RESET}"

    return f"{name_label} {bar_part} {pct_part}"


# ----- Showtime loop ------------------------------------------------------

def run_gallery(presets, *, duration=6.0, fps=24, seed=None):
    if not presets:
        print("nothing to show.", file=sys.stderr)
        return

    # Each preset is one terminal row; the redraw moves the cursor up
    # exactly len(presets) rows every frame. If the block is taller than the
    # rows actually free below the header, the cursor-up clamps at the top of
    # the screen and the overflow scrolls into scrollback every frame — a wall
    # of the duplicated top row(s). Reserve the header the caller already
    # printed (title + blank = 2 lines), the trailing footer (1), plus a
    # one-line safety margin, then trim to what's left.
    HEADER_LINES, FOOTER_LINES, SAFETY = 2, 1, 1
    term_lines = shutil.get_terminal_size().lines
    avail = max(1, term_lines - HEADER_LINES - FOOTER_LINES - SAFETY)
    if len(presets) > avail:
        sys.stderr.write(
            f"\x1b[1;93mTerminal is {term_lines} rows; showing first "
            f"{avail} of {len(presets)} presets. Resize taller or use "
            f"--section / --only to pick fewer.\x1b[0m\n\n"
        )
        presets = presets[:avail]

    rng = random.Random(seed)
    parts = {n: extract(themes.get(n)) for n in presets}
    # Per-preset fill rate, normalized below against the slowest pick so the
    # SLOWEST bar reaches 100% right at `total_frames` and faster ones finish
    # earlier and hold. Without the normalization a bar's cumulative fill is
    # speed*(frames/total_frames), so any speed < 1 ran out of frame budget
    # and froze below 100% (a 0.6 bar topped out at ~70%) — the bars that
    # "never complete".
    rates = {n: rng.uniform(0.6, 1.6) for n in presets}
    slowest = min(rates.values())
    fractions = {n: 0.0 for n in presets}
    name_width = max(len(n) for n in presets)
    n_rows = len(presets)

    term_cols = shutil.get_terminal_size().columns
    bar_display = plan_layout(parts.values(), name_width, term_cols)
    frame_delay = 1.0 / fps
    total_frames = max(1, int(duration * fps))

    out = sys.stdout
    # Hide cursor and turn OFF autowrap (DECAWM). Double-width glyphs (emoji
    # bars like lightning's ⚡, fire 🔥) can push a row past the right margin;
    # with autowrap on the terminal folds the overflow onto a second physical
    # line, so the row occupies 2 lines while the redraw only climbs n_rows
    # lines — a 1-line drift per frame that scrolls the top row off as a wall.
    # With autowrap off the overflow is clipped at the margin instead, keeping
    # every row exactly one physical line so the cursor-up math stays exact.
    out.write("\x1b[?25l\x1b[?7l")
    out.flush()

    drew_once = False
    t_start = time.perf_counter()
    try:
        # Slowest bar finishes at total_frames; a little slack absorbs fp
        # rounding. The all-complete check below ends the loop early once the
        # last bar lands, so this is just an upper bound.
        for frame in range(total_frames + max(2, fps // 2)):
            frame_start = time.perf_counter()
            for n in presets:
                step = rates[n] / (slowest * total_frames)
                fractions[n] = min(1.0, fractions[n] + step)

            # Cycle the animated tip at ~12 Hz regardless of the frame rate, so
            # the leading edge reads as motion instead of strobing at full fps
            # (which on a slow bar looked like the fill jittering back/forth).
            tip_tick = int(frame * 12 / fps)
            lines = [
                render_row(n, parts[n], fractions[n], name_width, bar_display,
                           tip_tick)
                for n in presets
            ]

            if drew_once:
                out.write(f"\x1b[{n_rows}A")  # cursor up N rows
            out.write("\r")
            out.write("\n".join(f"\x1b[2K{l}" for l in lines))
            out.write("\n")
            out.flush()
            drew_once = True

            if all(f >= 1.0 for f in fractions.values()):
                break
            # Subtract render+write+flush cost so the real frame rate tracks
            # the target instead of (target_period + work) per frame.
            slack = frame_delay - (time.perf_counter() - frame_start)
            if slack > 0:
                time.sleep(slack)
    finally:
        out.write("\x1b[?7h\x1b[?25h")  # restore autowrap, show cursor
        out.flush()

    elapsed = time.perf_counter() - t_start
    sys.stderr.write(
        f"\n\x1b[1;92m{len(presets)} presets, {elapsed:.2f}s, "
        f"{fps} fps target.\x1b[0m\n"
    )


# ----- CLI ----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--section", choices=sorted(SECTIONS), default="all",
                    help="which lineup to show (default: all)")
    ap.add_argument("--only", nargs="+", default=None,
                    help="explicit preset list (overrides --section)")
    ap.add_argument("--duration", type=float, default=6.0,
                    help="approximate seconds for the LAST bar to finish (default 6)")
    ap.add_argument("--fps", type=int, default=30,
                    help="target frames per second (default 30)")
    ap.add_argument("--seed", type=int, default=None,
                    help="seed for per-preset speed randomness")
    ap.add_argument("--list", action="store_true",
                    help="list section lineups and exit")
    args = ap.parse_args()

    if args.list:
        for sec, names in SECTIONS.items():
            valid = [n for n in names if n in themes.THEMES]
            print(f"\n[{sec}]  ({len(valid)} presets)")
            for n in valid:
                print(f"  {n}")
        return

    if args.only:
        unknown = [n for n in args.only if n not in themes.THEMES]
        if unknown:
            print(f"unknown preset(s): {', '.join(unknown)}", file=sys.stderr)
            sys.exit(2)
        picks = args.only
    else:
        picks = [n for n in SECTIONS[args.section] if n in themes.THEMES]

    sys.stderr.write(
        f"\x1b[1;97mBarFlow gallery\x1b[0m — "
        f"{len(picks)} presets, ~{args.duration:.1f}s, {args.fps} fps\n\n"
    )

    run_gallery(picks, duration=args.duration, fps=args.fps, seed=args.seed)


if __name__ == "__main__":
    main()

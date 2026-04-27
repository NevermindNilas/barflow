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
import sys
import time
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
        "sparkle", "pacman", "heart_emoji", "moon", "weather",
    ],
    "brand": [
        "github_dark", "discord", "dracula", "solarized", "nord", "gruvbox",
    ],
    "playful": [
        "hearts", "stars", "arrows", "pipes", "shade",
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
        elif kind == COL_SPINNER:
            out["spinner_frames"] = col[3]
            out["spinner_ansi"] = col[4] or ""
        elif kind == COL_DESCRIPTION:
            out["desc_ansi"] = col[4] or ""
        elif kind == COL_TEXT and not out["prefix_text"]:
            out["prefix_text"] = col[1] or ""
            out["prefix_ansi"] = col[4] or ""
    return out


# ----- Per-row renderer ---------------------------------------------------

def build_bar(glyphs, width, fraction):
    """Build one bar string from a 5-tuple glyphs spec at given fill fraction."""
    fill, empty, partials, left, right = glyphs
    cells = max(1, width)
    levels = len(partials) + 1
    total = cells * levels
    filled = int(fraction * total + 0.5)
    full_cells = filled // levels
    partial_idx = filled % levels

    body = fill * full_cells
    remaining = cells - full_cells
    if partial_idx > 0 and remaining > 0:
        body += partials[partial_idx - 1]
        remaining -= 1
    body += empty * remaining
    return f"{left}{body}{right}"


def render_row(name, parts, fraction, frame_tick, name_width):
    """Render a single preset row at this frame."""
    name_label = f"\x1b[1;97m{name:<{name_width}}{RESET}"

    spinner = ""
    frames = parts["spinner_frames"]
    if frames:
        glyph = frames[frame_tick % len(frames)]
        ansi = parts["spinner_ansi"]
        spinner = f"{ansi}{glyph}{RESET} " if ansi else f"{glyph} "

    bar_str = build_bar(parts["bar_glyphs"], parts["bar_width"], fraction)
    bar_part = f"{parts['bar_ansi']}{bar_str}{RESET}" if parts["bar_ansi"] else bar_str

    pct = f"{int(fraction * 100):3d}%"
    pct_color = "\x1b[1m" if fraction < 1.0 else "\x1b[1;92m"
    pct_part = f"{pct_color}{pct}{RESET}"

    return f"{spinner}{name_label} {bar_part} {pct_part}"


# ----- Showtime loop ------------------------------------------------------

def run_gallery(presets, *, duration=6.0, fps=24, seed=None):
    if not presets:
        print("nothing to show.", file=sys.stderr)
        return

    rng = random.Random(seed)
    parts = {n: extract(themes.get(n)) for n in presets}
    speeds = {n: rng.uniform(0.6, 1.6) for n in presets}  # finish-time multiplier
    fractions = {n: 0.0 for n in presets}
    name_width = max(len(n) for n in presets)
    n_rows = len(presets)
    frame_delay = 1.0 / fps
    total_frames = max(1, int(duration * fps))

    out = sys.stdout
    out.write("\x1b[?25l")  # hide cursor
    out.flush()

    drew_once = False
    t_start = time.perf_counter()
    try:
        for frame in range(total_frames + fps):  # extra slack so all bars hit 100%
            for n in presets:
                step = speeds[n] / total_frames
                fractions[n] = min(1.0, fractions[n] + step)

            lines = [
                render_row(n, parts[n], fractions[n], frame, name_width)
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
            time.sleep(frame_delay)
    finally:
        out.write("\x1b[?25h")  # show cursor
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
                    help="approximate seconds for fastest bar to finish (default 6)")
    ap.add_argument("--fps", type=int, default=24,
                    help="target frames per second (default 24)")
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

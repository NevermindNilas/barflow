"""Preset & template gallery — neon, ASCII art, emoji, brand palettes.

Run from anywhere:
    python examples/presets_gallery.py
    python examples/presets_gallery.py --section neon
    python examples/presets_gallery.py --only vaporwave hacker rocket_emoji
    python examples/presets_gallery.py --list

Each preset runs a short animated demo. The header above each bar
prints the preset name in bright white so you can match what you like.

Sections:
    neon       — vaporwave, synthwave, lightning, plasma, acid, midnight, ...
    ascii      — hacker, binary, curly, march, wave, rail_ascii
    emoji      — rocket, sakura, storm, sparkle, heart, moon, ...
    brand      — github_dark, discord, dracula, solarized, nord, gruvbox
    specialized — tiny, detailed, downloading, building, training
    classic    — original 27 themes (utilitarian, colorful, playful)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_REPO_SRC = Path(__file__).resolve().parent.parent / "src"
if _REPO_SRC.is_dir() and str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

import barflow
from barflow import themes


SECTIONS: dict[str, list[str]] = {
    "neon": [
        "vaporwave", "synthwave", "lightning", "plasma", "acid",
        "midnight", "ember", "amber_crt", "miami", "gold_rush",
        "alien", "deep_sea", "magma", "void", "chevron",
        "rail_neon", "slash_neon",
    ],
    "ascii": [
        "hacker", "binary", "curly", "march", "wave_ascii", "rail_ascii",
    ],
    "emoji": [
        "fire_emoji", "rocket_emoji", "sakura_emoji", "storm_emoji",
        "sparkle_emoji", "heart_emoji", "moon_emoji",
        "weather_emoji",
    ],
    "brand": [
        "github_dark", "discord", "dracula", "solarized", "nord", "gruvbox",
    ],
    "specialized": [
        "tiny", "detailed", "downloading", "building", "training",
    ],
    "classic": [
        "classic", "minimal", "rich_like", "spinner", "mono", "ghost",
        "ascii", "equals", "brackets",
        "neon", "pastel", "retro", "matrix", "fire", "ocean", "ice",
        "sunset", "forest", "cyberpunk",
        "hearts", "stars", "arrows_march", "pipes", "shade_cool",
        "line_clean", "double_frame", "round_retro",
    ],
}


def hdr(name: str):
    sys.stderr.write(
        f"\n\x1b[1;97m{name}\x1b[0m  "
        f"\x1b[90m{'─' * max(2, 40 - len(name))}\x1b[0m\n"
    )
    sys.stderr.flush()


def section_hdr(name: str):
    sys.stderr.write(
        f"\n\x1b[1;95m━━━ {name.upper()} ━━━\x1b[0m\n"
    )
    sys.stderr.flush()


def run_preset(name: str, *, n: int = 100, delay: float = 0.012,
               desc: str | None = None):
    hdr(name)
    cols = themes.get(name)
    with barflow.Progress(*cols, total=n, desc=desc or "demo") as p:
        for _ in range(n):
            p.tick()
            time.sleep(delay)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--section", choices=sorted(SECTIONS), default=None,
                    help="show only one section")
    ap.add_argument("--only", nargs="+", default=None,
                    help="subset of preset names to show")
    ap.add_argument("--list", action="store_true",
                    help="print every preset name (grouped by section) and exit")
    ap.add_argument("--n", type=int, default=100,
                    help="iterations per preset (default 100)")
    ap.add_argument("--delay", type=float, default=0.012,
                    help="sleep per iter in seconds (default 0.012)")
    args = ap.parse_args()

    if args.list:
        for sec, names in SECTIONS.items():
            print(f"\n[{sec}]")
            for n in names:
                if n in themes.THEMES:
                    print(f"  {n}")
        return

    if args.only:
        unknown = [n for n in args.only if n not in themes.THEMES]
        if unknown:
            print(f"Unknown preset(s): {', '.join(unknown)}", file=sys.stderr)
            print(f"Run with --list to see all names.", file=sys.stderr)
            sys.exit(2)
        for name in args.only:
            run_preset(name, n=args.n, delay=args.delay)
        return

    sections = [args.section] if args.section else list(SECTIONS)
    total = sum(len(SECTIONS[s]) for s in sections)
    sys.stderr.write(
        f"\x1b[1;97mBarFlow preset gallery\x1b[0m — "
        f"{total} presets across {len(sections)} sections, "
        f"~{args.n * args.delay:.1f}s each\n"
    )

    for sec in sections:
        section_hdr(sec)
        for name in SECTIONS[sec]:
            if name not in themes.THEMES:
                continue
            run_preset(name, n=args.n, delay=args.delay, desc=name)

    sys.stderr.write("\n\x1b[1;92mdone.\x1b[0m\n")


if __name__ == "__main__":
    main()

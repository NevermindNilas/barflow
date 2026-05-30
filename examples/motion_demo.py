"""Motion demo — animated bar tips + the procedural spinners, live.

Shows the two motion features added on top of the static gallery:

  1. Animated bar *tips* — the bar's leading edge cycles glyphs every frame
     even while progress is stalled. Each tipped theme deliberately PAUSES at
     ~50% for a beat so you can watch the edge keep breathing with the
     percentage frozen (the alive-progress signature).
  2. Procedural *spinners* — wave / wave_wide / dots_wave / bounce / scan /
     flow, generated from the `barflow.spinners` DSL.

Run from any cwd (needs a VT/truecolor terminal — Windows Terminal, iTerm2,
kitty, modern gnome-terminal, etc.):

    python examples/motion_demo.py
    python examples/motion_demo.py --section tips
    python examples/motion_demo.py --section spinners
    python examples/motion_demo.py --only neon matrix acid
    python examples/motion_demo.py --no-stall --speed 0.01
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_REPO_SRC = Path(__file__).resolve().parent.parent / "src"
if _REPO_SRC.is_dir() and str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

# Force UTF-8 on Windows so block/braille/emoji glyphs don't crash cp1252.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import barflow  # noqa: E402
from barflow import columns as C  # noqa: E402
from barflow import spinners  # noqa: E402
from barflow import themes  # noqa: E402


# Themes whose bars carry an animated tip — smooth flagships (explicit tip)
# plus coarse-glyph themes that inherit one straight from `bar_styles`.
TIPPED = [
    "neon", "fire", "ocean", "downloading",   # smooth + explicit fade tip
    "building", "matrix", "acid", "midnight",  # blocks / braille / bricks / bubble
    "deep_sea", "plasma", "sunset", "retro",   # glow / plasma / shade / blocks
]

# Spinners added in the motion pass — none are bound to a theme, so demo them
# directly via SpinnerColumn(name=...).
NEW_SPINNERS = ["wave", "wave_wide", "dots_wave", "bounce", "scan", "flow"]


def hdr(label: str):
    sys.stderr.write(
        f"\n\x1b[1;97m{label}\x1b[0m  "
        f"\x1b[90m{'─' * max(2, 44 - len(label))}\x1b[0m\n"
    )
    sys.stderr.flush()


def demo_tips(names, *, speed=0.022, stall=1.4, total=100):
    for name in names:
        hdr(f"tip · {name}")
        cols = themes.get(name)
        with barflow.Progress(*cols, total=total, desc=name) as p:
            for i in range(total):
                p.tick()
                # Freeze progress at the halfway mark: the render thread keeps
                # animating the tip while the percentage sits still.
                if stall and i == total // 2:
                    time.sleep(stall)
                time.sleep(speed)


def demo_spinners(names, *, seconds=2.2, tick_delay=0.05):
    for name in names:
        hdr(f"spinner · {name}")
        # total=0 → indeterminate: no bar, the spinner just runs.
        cols = [C.SpinnerColumn(name=name, style="bold #00e5ff"), "  ",
                C.DescriptionColumn(style="bold")]
        with barflow.Progress(*cols, total=0, desc=f"running {name}") as p:
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < seconds:
                p.tick()
                time.sleep(tick_delay)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--section", choices=("tips", "spinners", "all"),
                    default="all", help="which demo to run (default: all)")
    ap.add_argument("--only", nargs="+", default=None,
                    help="explicit theme/spinner names (overrides --section)")
    ap.add_argument("--speed", type=float, default=0.022,
                    help="seconds per tick for the bar demos (default 0.022)")
    ap.add_argument("--stall", type=float, default=1.4,
                    help="seconds to freeze progress at 50%% (default 1.4)")
    ap.add_argument("--no-stall", action="store_true",
                    help="don't pause at 50%% (smooth run to 100%%)")
    ap.add_argument("--spinner-seconds", type=float, default=2.2,
                    help="seconds to run each spinner (default 2.2)")
    args = ap.parse_args()

    stall = 0.0 if args.no_stall else args.stall

    sys.stderr.write(
        "\x1b[1;97mBarFlow motion demo\x1b[0m — animated tips + procedural "
        "spinners\n"
    )

    if args.only:
        tips = [n for n in args.only if n in themes.THEMES]
        spins = [n for n in args.only if n in spinners.SPINNERS]
        if tips:
            demo_tips(tips, speed=args.speed, stall=stall)
        if spins:
            demo_spinners(spins, seconds=args.spinner_seconds)
        unknown = [n for n in args.only
                   if n not in themes.THEMES
                   and n not in spinners.SPINNERS]
        if unknown:
            sys.stderr.write(f"\x1b[1;93mskipped unknown: "
                             f"{', '.join(unknown)}\x1b[0m\n")
    else:
        if args.section in ("tips", "all"):
            demo_tips(TIPPED, speed=args.speed, stall=stall)
        if args.section in ("spinners", "all"):
            demo_spinners(NEW_SPINNERS, seconds=args.spinner_seconds)

    sys.stderr.write("\n\x1b[1;92mdone.\x1b[0m\n")


if __name__ == "__main__":
    main()

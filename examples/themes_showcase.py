"""Theme gallery — runs every named theme in sequence so you can pick one.

Run from anywhere:
    python examples/themes_showcase.py
    python examples/themes_showcase.py --only fire neon cyberpunk
    python examples/themes_showcase.py --list

Each theme runs a short animated demo. The header above each bar
prints the theme name in bright white so you can match what you like.
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


def hdr(name: str):
    # Bright white label, dim right rule, one blank line above.
    sys.stderr.write(
        f"\n\x1b[1;97m{name}\x1b[0m  "
        f"\x1b[90m{'─' * max(2, 40 - len(name))}\x1b[0m\n"
    )
    sys.stderr.flush()


def run_theme(name: str, *, n: int = 100, delay: float = 0.012):
    hdr(name)
    cols = themes.get(name)
    with barflow.Progress(*cols, total=n, desc="demo") as p:
        for _ in range(n):
            p.tick()
            time.sleep(delay)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", nargs="+", default=None,
                    help="subset of themes to show (default: all)")
    ap.add_argument("--list", action="store_true",
                    help="print available theme names and exit")
    ap.add_argument("--n", type=int, default=100,
                    help="iterations per theme (default 100)")
    ap.add_argument("--delay", type=float, default=0.012,
                    help="sleep per iter in seconds (default 0.012)")
    args = ap.parse_args()

    all_names = themes.names()

    if args.list:
        print("Available themes:")
        for n in all_names:
            print(f"  {n}")
        return

    picks = args.only if args.only else all_names
    unknown = [n for n in picks if n not in themes.THEMES]
    if unknown:
        print(f"Unknown theme(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Available: {', '.join(all_names)}", file=sys.stderr)
        sys.exit(2)

    sys.stderr.write(
        f"\x1b[1;97mBarFlow theme gallery\x1b[0m — "
        f"{len(picks)} themes, ~{args.n * args.delay:.1f}s each\n"
    )

    for name in picks:
        run_theme(name, n=args.n, delay=args.delay)

    sys.stderr.write("\n\x1b[1;92mdone.\x1b[0m\n")


if __name__ == "__main__":
    main()

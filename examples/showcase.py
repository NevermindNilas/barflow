"""Showcase — runs 7 scenarios in sequence. Works from any cwd:

    python examples\\showcase.py
    python D:\\Progressor\\examples\\showcase.py
    cd examples && python showcase.py
"""

import sys
import time
from pathlib import Path

# Bootstrap: add the in-tree src/ to sys.path so we import the local
# barflow build, not a stray site-packages copy.
_REPO_SRC = Path(__file__).resolve().parent.parent / "src"
if _REPO_SRC.is_dir() and str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

import barflow
from barflow.columns import (
    SpinnerColumn, DescriptionColumn, BarColumn, PercentColumn,
    CountColumn, RateColumn, ElapsedColumn, EtaColumn, TextColumn,
)


def hdr(s):
    sys.stderr.write(f"\n\x1b[1;97m── {s} \x1b[90m{'─' * max(2, 60 - len(s))}\x1b[0m\n")


def demo_1_track():
    hdr("1. barflow.track() one-liner")
    for _ in barflow.track(range(100), desc="downloading"):
        time.sleep(0.01)


def demo_2_hex_truecolor():
    hdr("2. hex truecolor + styles")
    with barflow.Progress(
        SpinnerColumn(style="bold yellow"), " ",
        DescriptionColumn(style="bold #88ccff"), " ",
        BarColumn(width=30, style="bold #ff8800"), " ",
        PercentColumn(style="#88ff88"), "  ",
        RateColumn(style="dim italic"),
        total=100, desc="hex colors",
    ) as p:
        for _ in range(100):
            p.tick()
            time.sleep(0.01)


def demo_3_theme():
    hdr("3. named theme = classic")
    for _ in barflow.track(range(100), desc="themed", theme="classic"):
        time.sleep(0.01)


def demo_4_multi_task():
    hdr("4. multi-task stacked bars")
    with barflow.Progress(theme="classic") as p:
        dl = p.add_task(total=80, desc="download")
        ex = p.add_task(total=80, desc="extract ")
        vf = p.add_task(total=80, desc="verify  ")
        for i in range(80):
            p.update(dl, 1)
            if i >= 10:
                p.update(ex, 1)
            if i >= 25:
                p.update(vf, 1)
            time.sleep(0.015)
        for _ in range(10):
            p.update(ex, 1)
            time.sleep(0.01)
        for _ in range(25):
            p.update(vf, 1)
            time.sleep(0.01)


def demo_5_capture_print():
    hdr("5. print() captured above live bar")
    with barflow.Progress(total=40, desc="with prints", capture_output=True) as p:
        for i in range(40):
            if i in (5, 15, 25, 35):
                print(f">>> milestone {i} reached")
            p.tick()
            time.sleep(0.04)


def demo_6_backgrounds():
    hdr("6. 256-color + backgrounds")
    with barflow.Progress(
        DescriptionColumn(style="bold white on_blue"), " ",
        BarColumn(width=30, style="black on #ffcc00"), " ",
        PercentColumn(style="bold white on red"), " ",
        CountColumn(style="color(214)"),
        total=100, desc="painted",
    ) as p:
        for _ in range(100):
            p.tick()
            time.sleep(0.01)


def demo_7_indeterminate():
    hdr("7. unknown total — pulsing bar")
    with barflow.Progress(
        SpinnerColumn(name="dots2", style="bold magenta"), " ",
        DescriptionColumn(style="bold"), " ",
        BarColumn(width=30, style="bright_cyan"), " ",
        CountColumn(), " ",
        RateColumn(style="dim"),
        total=0, desc="streaming",
    ) as p:
        for _ in range(80):
            p.tick()
            time.sleep(0.02)


if __name__ == "__main__":
    demo_1_track()
    demo_2_hex_truecolor()
    demo_3_theme()
    demo_4_multi_task()
    demo_5_capture_print()
    demo_6_backgrounds()
    demo_7_indeterminate()
    sys.stderr.write("\n\x1b[1;92mAll demos complete.\x1b[0m\n")

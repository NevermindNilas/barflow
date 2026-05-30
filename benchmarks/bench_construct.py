"""Progress construction cost — themed and columned bar setup, ns per build.

The hot iteration path is C-level and effectively at the floor, but every
themed/columned `Progress(...)` pays a one-time Python setup cost: theme
factory -> column tuples -> style parsing -> resolve_columns -> C init. This
bench isolates that setup cost. It is the workload behind the construction
optimizations (cached lazy imports + a memoized style() parser); single-bar
programs pay it once, so the win is invisible there and only shows when many
bars are built.

Usage:
    python benchmarks/bench_construct.py
    python benchmarks/bench_construct.py --inner 20000 --batches 9
"""

from __future__ import annotations

import argparse
import gc
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _bench(fn, batches: int, inner: int) -> list[float]:
    """Return per-call ns for each batch (min reported), warmed up first."""
    for _ in range(inner):
        fn()
    out: list[float] = []
    for _ in range(batches):
        gc.collect()
        t0 = time.perf_counter()
        for _ in range(inner):
            fn()
        out.append((time.perf_counter() - t0) / inner * 1e9)
    out.sort()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inner", type=int, default=20_000)
    ap.add_argument("--batches", type=int, default=7)
    ap.add_argument("--theme", type=str, default="classic")
    args = ap.parse_args()

    import barflow
    from barflow.columns import (
        DescriptionColumn, BarColumn, PercentColumn, CountColumn, RateColumn,
    )
    P = barflow.Progress

    def themed():
        return P(total=100, theme=args.theme, disable=True)

    prebuilt = [DescriptionColumn(), BarColumn(), PercentColumn(),
                CountColumn(), RateColumn()]

    def columned_prebuilt():
        return P(*prebuilt, total=100, disable=True)

    def columned_fresh():
        # Rebuilds the column factories each call too (exercises BarColumn's
        # bar_styles lookup and per-column style parsing).
        return P(DescriptionColumn(), BarColumn(), PercentColumn(),
                 CountColumn(), RateColumn(), total=100, disable=True)

    cases = [
        (f"themed ({args.theme})", themed),
        ("columned (prebuilt)", columned_prebuilt),
        ("columned (fresh factories)", columned_fresh),
    ]

    print(f"=== Progress construction cost  (inner={args.inner:,}, "
          f"batches={args.batches}) ===\n")
    print(f"  {'variant':28s} {'min ns':>9s} {'median ns':>11s} {'max ns':>9s}")
    print("  " + "-" * 60)
    for name, fn in cases:
        r = _bench(fn, args.batches, args.inner)
        print(f"  {name:28s} {r[0]:>9.1f} {statistics.median(r):>11.1f} "
              f"{r[-1]:>9.1f}")
    print("\nLower is better. min is the cleanest steady-state estimate "
          "(noise only adds time).")


if __name__ == "__main__":
    main()

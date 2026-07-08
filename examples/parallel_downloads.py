"""Simulate N concurrent 'downloads' on one barflow.Progress, one thread per
file, all bars advancing in parallel — the multibar stress scenario.

    python examples/parallel_downloads.py            # 6 files, flex bars
    python examples/parallel_downloads.py --fixed    # fixed-width bars
    python examples/parallel_downloads.py --long      # long names (clip test)
    python examples/parallel_downloads.py -n 10       # 10 files

Each worker owns one task and hammers p.update(task_id, chunk) at its own
jittered rate, so the bars fill unevenly like real transfers. Every task has
its own lock-free counter; the background render thread walks them all.

Use --long in a NARROW terminal to see how fixed-width vs flex bars handle a
description wider than the screen (flex clips to the terminal; fixed overflows).
"""

import argparse
import random
import sys
import threading
import time
from pathlib import Path

_REPO_SRC = Path(__file__).resolve().parent.parent / "src"
if _REPO_SRC.is_dir() and str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

import barflow
from barflow import columns as C

FILES = [
    ("ubuntu-24.04-desktop-amd64.iso", 4_100),
    ("node_modules.tar.gz",             820),
    ("model-weights-q4.gguf",         7_300),
    ("dataset-shard-0007.parquet",    1_450),
    ("firmware-update.bin",             240),
    ("backup-2026-07-08.zip",         3_050),
    ("clip-vit-large.safetensors",    1_710),
    ("logs-archive.tar.zst",            560),
    ("game-assets-pack.pak",          6_200),
    ("db-snapshot.dump",              2_480),
]

LONG = "-with-an-absurdly-long-descriptive-filename-that-will-overflow-a-narrow-terminal"


def build_progress(fixed: bool, align: bool):
    bar = C.BarColumn(width=30) if fixed else C.BarColumn(width=None)
    return barflow.Progress(
        C.SpinnerColumn(), " ",
        C.DescriptionColumn(style="bold"), " ",
        bar, " ",
        C.PercentColumn(), " ",
        C.CountColumn(), " ",     # "downloaded / total" (KB, simulated)
        C.RateColumn(), " ",      # KB/s (simulated)
        C.EtaColumn(),
        align=align,              # pad names to the longest so bars line up
        min_interval=0.05,
    )


def worker(p, task_id, size_kb, seed):
    rng = random.Random(seed)
    done = 0
    # Each file gets its own base speed + burstiness, so bars desync.
    base_chunk = rng.randint(6, 30)
    while done < size_kb:
        chunk = min(size_kb - done, max(1, int(rng.gauss(base_chunk, base_chunk * 0.5))))
        p.update(task_id, chunk)
        done += chunk
        # Occasional stall, like a slow mirror.
        delay = 0.004 if rng.random() > 0.05 else rng.uniform(0.05, 0.15)
        time.sleep(delay)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=6, help="number of parallel files")
    ap.add_argument("--fixed", action="store_true", help="fixed-width bars (overflow-prone)")
    ap.add_argument("--long", action="store_true", help="long filenames (clipping test)")
    ap.add_argument("--no-align", dest="align", action="store_false",
                    help="don't pad names to equal width (bars won't line up)")
    args = ap.parse_args()

    files = FILES[: max(1, min(args.n, len(FILES)))]

    t0 = time.perf_counter()
    with build_progress(args.fixed, args.align) as p:
        ids = []
        for name, size in files:
            desc = name + (LONG if args.long else "")
            ids.append(p.add_task(total=size, desc=desc))
        threads = [
            threading.Thread(target=worker, args=(p, tid, size, i),
                             name=f"dl-{i}")
            for i, (tid, (_, size)) in enumerate(zip(ids, files))
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    elapsed = time.perf_counter() - t0
    sys.stderr.write(f"\n{len(files)} downloads finished in {elapsed:.1f}s\n")


if __name__ == "__main__":
    main()

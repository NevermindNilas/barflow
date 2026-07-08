"""Byte-transfer + training-loop demo for the humanization / postfix / reset
/ smoothing additions.

    python examples/bytes_and_postfix.py            # all demos
    python examples/bytes_and_postfix.py download   # just the download bar
    python examples/bytes_and_postfix.py train      # just the training bar
    python examples/bytes_and_postfix.py copy       # wrap_file byte metering

Download demo: `unit="B", unit_scale=True, unit_divisor=1024` turns the raw
byte counter into `1.50M/4.10M` and the rate into `… B/s`, `smoothing=0.3`
keeps the rate/ETA tracking the current transfer speed rather than the whole-
run average, and `set_postfix` shows the live mirror.

Training demo: one bar reused across epochs via `reset()`, with
`set_postfix(loss=…, acc=…)` — the tqdm pattern, no bar reconstruction.
"""

import random
import sys
import time
from pathlib import Path

_REPO_SRC = Path(__file__).resolve().parent.parent / "src"
if _REPO_SRC.is_dir() and str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

import barflow
from barflow import columns as C


def download_demo():
    total = 4_100 * 1024  # 4.1 MiB, counted in bytes
    rng = random.Random(7)
    with barflow.Progress(
        C.DescriptionColumn(style="bold"), " ",
        C.BarColumn(width=None), " ",
        C.PercentColumn(), " ",
        C.CountColumn(), " ",
        C.RateColumn(), " ",
        C.EtaColumn(), C.PostfixColumn(),
        total=total, desc="ubuntu.iso",
        unit="B", unit_scale=True, unit_divisor=1024,
        smoothing=0.3,
    ) as p:
        p.set_postfix(mirror="de")
        done = 0
        while done < total:
            chunk = min(total - done, rng.randint(20_000, 90_000))
            p.advance(chunk)
            done += chunk
            if done > total // 2:
                p.set_postfix(mirror="us")   # "switched mirror mid-transfer"
            time.sleep(0.01 if rng.random() > 0.06 else 0.06)


def train_demo(epochs=3, steps=40):
    rng = random.Random(1)
    with barflow.Progress(total=steps, desc="epoch 1", smoothing=0.4) as p:
        for epoch in range(1, epochs + 1):
            p.reset(total=steps)
            p.set_description(f"epoch {epoch}")
            loss, acc = 2.5 / epoch, 0.0
            for step in range(steps):
                p.advance(1)
                loss *= 0.97 + rng.uniform(-0.01, 0.01)
                acc = min(0.999, acc + rng.uniform(0.0, 0.03))
                p.set_postfix(loss=loss, acc=acc)
                time.sleep(0.01)


def copy_demo():
    """Copy a temp file through barflow.wrap_file — the bar meters the read
    stream's byte throughput with zero manual advance() calls."""
    import os
    import tempfile

    src = tempfile.NamedTemporaryFile(delete=False)
    try:
        src.write(os.urandom(3_000_000))   # 3 MB of noise
        src.close()
        with open(src.name, "rb") as raw, open(os.devnull, "wb") as sink:
            f = barflow.wrap_file(raw, desc="copy", smoothing=0.3)
            try:
                while chunk := f.read(64 * 1024):
                    sink.write(chunk)
            finally:
                f.__exit__(None, None, None)
    finally:
        os.unlink(src.name)


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("all", "download"):
        download_demo()
    if which in ("all", "train"):
        train_demo()
    if which in ("all", "copy"):
        copy_demo()


if __name__ == "__main__":
    main()

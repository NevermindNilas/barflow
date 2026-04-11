"""Run every named preset in parallel, one thread per preset.

Each preset gets its own worker thread and its own `barflow.Progress`
instance. Because the terminal cursor is a shared resource — every
Progress moves the cursor up by its own `last_rendered_lines` count to
repaint — we serialize the *live* region with a single `render_lock`.
All threads are started up-front and race for the lock, so wall-clock
startup/teardown happens in parallel even though only one bar is
drawing at a time.

Run from any cwd:
    python examples/parallel_presets.py
"""

import sys
import threading
import time
from pathlib import Path

_REPO_SRC = Path(__file__).resolve().parent.parent / "src"
if _REPO_SRC.is_dir() and str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

import barflow
from barflow import themes


render_lock = threading.Lock()


def hdr(s):
    sys.stderr.write(f"\n\x1b[1;97m── {s} \x1b[90m{'─' * max(2, 60 - len(s))}\x1b[0m\n")


def worker(name, steps=60, delay=0.008):
    # Simulate parallel "pre-work" that happens while other threads hold
    # the render lock — e.g. fetching data, warming caches, etc.
    scratch = [i * i for i in range(steps)]

    total = 0 if name == "spinner" else steps
    with render_lock:
        hdr(f"preset: {name}  (thread={threading.current_thread().name})")
        with barflow.Progress(total=total, desc=name, theme=name) as p:
            for _ in scratch:
                p.tick()
                time.sleep(delay)


def main():
    preset_names = themes.names()

    threads = [
        threading.Thread(target=worker, args=(name,), name=f"preset-{name}")
        for name in preset_names
    ]

    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t0

    sys.stderr.write(
        f"\n\x1b[1;92mAll {len(preset_names)} presets finished "
        f"in {elapsed:.2f}s across {len(threads)} threads.\x1b[0m\n"
    )


if __name__ == "__main__":
    main()

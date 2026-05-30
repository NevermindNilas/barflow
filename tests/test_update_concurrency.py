"""Concurrency guard for Progress.update() and the render-mutex/GIL invariant.

update() takes render_mtx to resolve the task pointer. It drops the GIL
before the lock ONLY when a CallbackColumn is present (then render_frame
re-enters Python under render_mtx and a GIL-holding waiter would deadlock);
with no callback column it takes the lock with the GIL held to skip the
per-call thread-state save/restore. This test pins both halves of that
invariant:

  * no deadlock under heavy render_mtx contention + concurrent add_task(),
    for BOTH the no-callback (GIL-held) and callback (GIL-dropped) paths;
  * counters stay exact (no lost increments) under concurrency.

A watchdog thread fails the test loudly if the run ever wedges, rather than
letting the suite hang.
"""

import threading
import time

import pytest

import barflow
from barflow.columns import BarColumn, CallbackColumn, CountColumn, DescriptionColumn

PER = 20_000
NPROD = 4
WATCHDOG_S = 20.0


def _hammer(p):
    """NPROD producers hammer update() on tasks 0..3 while another thread
    spams add_task() to force the task vector to reallocate under render_mtx."""
    tids = [0, 1, 2, 3]
    barrier = threading.Barrier(NPROD + 1)
    errors = []

    def worker(tid):
        try:
            barrier.wait()
            for _ in range(PER):
                p.update(tid, 1)
        except BaseException as e:  # pragma: no cover - surfaced via errors
            errors.append(e)

    def adder():
        try:
            barrier.wait()
            for _ in range(40):
                p.add_task(total=10 ** 12)
                time.sleep(0.0002)
        except BaseException as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(t,)) for t in tids]
    threads.append(threading.Thread(target=adder))
    for t in threads:
        t.start()
    deadline = time.perf_counter() + WATCHDOG_S
    for t in threads:
        remaining = deadline - time.perf_counter()
        t.join(timeout=max(0.0, remaining))
        if t.is_alive():
            pytest.fail("update()/add_task() deadlocked (watchdog fired) — "
                        "render_mtx/GIL invariant violated")
    assert not errors, f"worker errors: {errors!r}"


@pytest.mark.parametrize("with_callback", [False, True], ids=["no_callback", "callback"])
def test_update_no_deadlock_and_exact_counts(with_callback):
    cols = [DescriptionColumn(), BarColumn(), CountColumn()]
    if with_callback:
        cols.append(CallbackColumn(lambda t: str(t.completed)))
    # tiny min_interval => render thread grabs render_mtx almost continuously
    p = barflow.Progress(*cols, total=10 ** 12, desc="t0", min_interval=0.001)
    p.__enter__()
    try:
        for _ in range(3):
            p.add_task(total=10 ** 12, desc="x")
        _hammer(p)
        # task 0 received exactly PER increments from its single producer.
        assert p.completed == PER
    finally:
        p.__exit__(None, None, None)

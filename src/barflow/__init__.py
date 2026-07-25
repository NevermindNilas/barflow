"""BarFlow — fast Python progress bars with a C++ core.

Top-level imports are kept minimal so `from barflow import track` stays
cold-startup-cheap (~1 ms). Columns, themes, spinners, hooks, and the
asyncio wrapper are lazy-loaded via `__getattr__` on first access.
"""

from . import _core
from ._core import Tracker

__version__ = "0.5.1"
__all__ = ["Progress", "Tracker", "track", "wrap_file", "wrapattr", "__version__"]


# ---- Fast path -------------------------------------------------------------

def _auto_disable():
    """True when stderr is not an interactive terminal. BarFlow renders to
    stderr, so on a pipe/file/redirect we suppress the bar (tqdm's
    `disable=None` behavior) rather than spraying ANSI frames into the sink."""
    import sys
    stream = sys.stderr
    try:
        return not (stream is not None and stream.isatty())
    except Exception:
        return True


def _build_progress(total, desc, columns, theme, disable, min_interval,
                    capture_output, smoothing, leave, unit, unit_scale,
                    unit_divisor, initial, delay):
    """Construct the Progress backing a track()/atrack() call.

    Fast path: no columns, no theme, no capture_output → straight to
    `_core.Progress` (one C-extension construction, no Python subclass).
    Slow path: any decoration → route through the Python `Progress` class,
    which resolves themes/columns before calling into the core.
    """
    if columns or theme or capture_output:
        from . import _progress
        return _progress.Progress(
            *(columns or ()),
            total=total,
            desc=desc,
            theme=theme,
            disable=disable,
            min_interval=min_interval,
            capture_output=capture_output,
            smoothing=smoothing,
            leave=leave,
            unit=unit,
            unit_scale=unit_scale,
            unit_divisor=unit_divisor,
            initial=initial,
            delay=delay,
        )
    return _core.Progress(
        total=total,
        desc=desc,
        min_interval=min_interval,
        disable=disable,
        smoothing=smoothing,
        leave=leave,
        unit=unit,
        unit_scale=unit_scale,
        unit_divisor=float(unit_divisor),
        initial=initial,
        delay=delay,
    )


def track(iterable, total=None, desc=None, *, columns=None, theme=None,
          task_id=0, disable=False, min_interval=0.05, capture_output=False,
          smoothing=0.0, leave=True, unit="it", unit_scale=False,
          unit_divisor=1000, initial=0, delay=0.0):
    """Wrap `iterable` in a live progress bar. Returns an iterator.

    Fast path: no columns, no theme, no capture_output → goes straight to
    `_core.Progress` (one C-extension construction, no Python subclass).
    Slow path: any decoration → route through the Python `Progress` class.

    `disable`      False (default) always shows; True hides; None auto-disables
                   when stderr is not a TTY (tqdm's `disable=None` semantics).
    `smoothing`    0 = whole-run average rate (default); (0,1] = EMA weight on
                   the most recent interval for a responsive it/s and ETA.
    `leave`        False clears the bar on completion instead of leaving it.
    `unit`         noun in the rate suffix ("it" → "N it/s", "B" → "N B/s").
    `unit_scale`   humanize counts/rates with SI-style k/M/G scaling.
    `unit_divisor` scaling base — 1000 (SI) or 1024 (binary/bytes).
    `initial`      count already done (resume); shown but excluded from rate.
    `delay`        seconds to wait before showing the bar (hide fast jobs).
    """
    if task_id != 0:
        # track() always builds a single-task (task 0) bar; a non-zero
        # task_id would otherwise reach the C Tracker bounds check and raise
        # an opaque "task_id out of range". Fail fast with guidance instead.
        raise ValueError(
            "track() creates a single-task bar, so task_id must be 0. "
            "For multiple bars use barflow.Progress + add_task()."
        )

    if disable is None:
        disable = _auto_disable()

    if total is None:
        try:
            total = len(iterable)
        except TypeError:
            total = 0

    progress = _build_progress(
        total, desc, columns, theme, disable, min_interval, capture_output,
        smoothing, leave, unit, unit_scale, unit_divisor, initial, delay,
    )

    progress.__enter__()
    tracker = Tracker(iter(iterable), progress, task_id=task_id, owns_progress=True)
    if capture_output:
        # The C Tracker tears the progress down via close(), which bypasses
        # the Python __exit__ that uninstalls stdout/stderr capture — so an
        # exhausted track(capture_output=True) would otherwise leave sys.stdout
        # permanently replaced. Guard the iteration so __exit__ always runs.
        return _capture_guard(tracker, progress)
    return tracker


def _capture_guard(tracker, progress):
    """Yield from `tracker`, guaranteeing `progress.__exit__` runs on
    exhaustion, early break (generator close), or exception — so the
    stdout/stderr capture is always uninstalled."""
    try:
        yield from tracker
    finally:
        progress.__exit__(None, None, None)


# ---- Lazy layer ------------------------------------------------------------

def __getattr__(name):
    # Lazy-load the Progress Python subclass on first access.
    if name == "Progress":
        from . import _progress
        Progress = _progress.Progress
        globals()["Progress"] = Progress
        return Progress
    # File-object progress wrapping (barflow.wrap_file / .wrapattr) is lazy so
    # the byte-humanization import cost is only paid by callers that use it.
    if name in ("wrap_file", "wrapattr"):
        from . import _wrap
        globals()["wrap_file"] = _wrap.wrap_file
        globals()["wrapattr"] = _wrap.wrapattr
        return globals()[name]
    # Hand-rolled dispatch avoids importing `importlib` and building a dict
    # at module-load time. Each branch resolves to a single __import__ call.
    if name == "columns":
        mod = __import__("barflow.columns", fromlist=("columns",))
    elif name == "themes":
        mod = __import__("barflow.themes", fromlist=("themes",))
    elif name == "spinners":
        mod = __import__("barflow.spinners", fromlist=("spinners",))
    elif name == "aio":
        mod = __import__("barflow.aio", fromlist=("aio",))
    elif name == "hooks":
        mod = __import__("barflow.hooks", fromlist=("hooks",))
    else:
        raise AttributeError(f"module 'barflow' has no attribute {name!r}")
    globals()[name] = mod
    return mod

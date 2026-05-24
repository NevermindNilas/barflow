"""BarFlow — fast Python progress bars with a C++ core.

Top-level imports are kept minimal so `from barflow import track` stays
cold-startup-cheap (~1 ms). Columns, themes, spinners, hooks, and the
asyncio wrapper are lazy-loaded via `__getattr__` on first access.
"""

from . import _core
from ._core import Tracker

__version__ = "0.2.3"
__all__ = ["Progress", "Tracker", "track", "__version__"]


# ---- Fast path -------------------------------------------------------------

def track(iterable, total=None, desc=None, *, columns=None, theme=None,
          task_id=0, disable=False, min_interval=0.05, capture_output=False):
    """Wrap `iterable` in a live progress bar. Returns a Tracker iterator.

    Fast path: no columns, no theme, no capture_output → goes straight to
    `_core.Progress` (one C-extension construction, no Python subclass).
    Slow path: any decoration → route through the Python `Progress` class.
    """
    if total is None:
        try:
            total = len(iterable)
        except TypeError:
            total = 0

    if columns or theme or capture_output:
        from . import _progress
        progress = _progress.Progress(
            *(columns or ()),
            total=total,
            desc=desc,
            theme=theme,
            disable=disable,
            min_interval=min_interval,
            capture_output=capture_output,
        )
    else:
        progress = _core.Progress(
            total=total,
            desc=desc,
            min_interval=min_interval,
            disable=disable,
        )

    progress.__enter__()
    return Tracker(iter(iterable), progress, task_id=task_id, owns_progress=True)


# ---- Lazy layer ------------------------------------------------------------

def __getattr__(name):
    # Lazy-load the Progress Python subclass on first access.
    if name == "Progress":
        from . import _progress
        Progress = _progress.Progress
        globals()["Progress"] = Progress
        return Progress
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

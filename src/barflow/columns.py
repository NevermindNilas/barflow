"""Column factories — shape-compatible with rich.progress.

A column is represented to the C core as a 5-tuple:

    (type: int, text: str, width: int, frames: list[str]|None, style: str)

Every factory accepts a `style=` keyword that takes a
`barflow.style`-parseable string: named colors, hex colors, 256-color
indexes, text styles (bold/italic/underline/...), and backgrounds —
see `barflow/style.py`. `color=` is kept as an alias for backward
compatibility.

`Progress(*columns, ...)` accepts strings as shorthand for TextColumn.
"""

from __future__ import annotations

from ._core import (
    COL_TEXT, COL_DESCRIPTION, COL_BAR, COL_PERCENT, COL_COUNT,
    COL_RATE, COL_ELAPSED, COL_ETA, COL_SPINNER, COL_CALLBACK,
)
from .style import style as _style


def _resolve(style=None, color=None):
    """Prefer `style`, fall back to `color`. Both accept the same grammar."""
    spec = style if style is not None else color
    if not spec:
        return ""
    if isinstance(spec, str) and spec.startswith("\x1b"):
        return spec
    return _style(spec)


def TextColumn(text, *, style=None, color=None):
    """Literal text, interpolated into the bar line."""
    return (COL_TEXT, text, 0, None, _resolve(style, color))


def DescriptionColumn(*, style=None, color=None):
    """The task's description string."""
    return (COL_DESCRIPTION, "", 0, None, _resolve(style, color))


def BarColumn(width=40, *, style="cyan", color=None, glyphs="smooth"):
    """A progress bar with customizable glyphs and style.

    `width`   character width of the bar body (excludes borders). 40.
              Pass `None` to flex to the terminal width — the column
              claims whatever cells remain after every other column
              has rendered, re-measured on each frame. Falls back to
              40 when the terminal width cannot be detected.
    `style`   colour/style spec applied to the whole bar + borders.
              Accepts named colors, hex, 256-color, combined styles.
              See `barflow.style` for the full grammar.
    `glyphs`  name from `barflow.bar_styles.BAR_STYLES` (e.g. "smooth",
              "shade", "ascii", "equals", "dots", "hearts", "arrows",
              "sharp", "braille", "line", "double", "round", "stars",
              "pipe", "pipes", "blocks") or a dict with keys
              `fill`, `empty`, `partials`, `left`, `right` to build
              a custom set.
    `color`   backward-compat alias for `style`.
    """
    from .bar_styles import to_tuple
    g = to_tuple(glyphs)
    # -1 is the on-the-wire sentinel for "flex width". Keeps the column
    # tuple schema flat — the C core detects width < 0 and flips the
    # column's flex flag on.
    w = -1 if width is None else int(width)
    return (COL_BAR, "", w, None, _resolve(style, color), g)


def PercentColumn(*, style=None, color=None):
    """Percent complete as an integer followed by '%'."""
    return (COL_PERCENT, "", 0, None, _resolve(style, color))


def CountColumn(*, style=None, color=None):
    """`completed/total` numeric pair."""
    return (COL_COUNT, "", 0, None, _resolve(style, color))


def RateColumn(*, style=None, color=None):
    """Iterations per second with SI scaling."""
    return (COL_RATE, "", 0, None, _resolve(style, color))


def ElapsedColumn(*, style=None, color=None):
    """Elapsed wall time `MM:SS` or `H:MM:SS`."""
    return (COL_ELAPSED, "", 0, None, _resolve(style, color))


def EtaColumn(*, style=None, color=None):
    """Estimated time remaining."""
    return (COL_ETA, "", 0, None, _resolve(style, color))


def SpinnerColumn(frames=None, *, name="dots", style=None, color=None):
    """Animated spinner. `frames` overrides `name`; both fall back to dots."""
    if frames is None:
        from .spinners import SPINNERS
        frames = SPINNERS.get(name, SPINNERS["dots"])
    return (COL_SPINNER, "", 0, list(frames), _resolve(style, color))


def CallbackColumn(func, *, style=None, color=None):
    """Python-rendered column. `func(task)` is called on every frame
    from the render thread with a `types.SimpleNamespace` snapshot of
    the task state (`.completed`, `.total`, `.elapsed`, `.rate`,
    `.speed`, `.percentage`, `.fraction`, `.description`, `.frame_tick`,
    `.task_id`). Its return value must be a `str`; it is appended to
    the frame buffer verbatim (so embed your own ANSI escapes if you
    need inline styling — the `style=` wrapper is applied around the
    whole column output, as with the other column types).

    `func` is invoked under `PyGILState_Ensure`; exceptions raised from
    it are printed via `sys.unraisablehook` and the bar keeps running.
    """
    if not callable(func):
        raise TypeError("CallbackColumn requires a callable")
    return (COL_CALLBACK, "", 0, None, _resolve(style, color), func)


def resolve_columns(columns):
    """Turn a mixed list of factories and strings into column tuples.

    Bare strings become TextColumn. Factory tuples (5-tuple for most
    columns, 6-tuple for BarColumn with glyphs) are passed through.
    """
    out = []
    for c in columns:
        t = type(c)
        if t is str:
            out.append((COL_TEXT, c, 0, None, ""))
        elif t is tuple and len(c) in (5, 6):
            out.append(c)
        else:
            raise TypeError(
                f"column must be a factory tuple or str, got {t.__name__}"
            )
    return out


__all__ = [
    "TextColumn", "DescriptionColumn", "BarColumn", "PercentColumn",
    "CountColumn", "RateColumn", "ElapsedColumn", "EtaColumn",
    "SpinnerColumn", "CallbackColumn", "resolve_columns",
]

"""Column factories — shape-compatible with rich.progress.

A column is represented to the C core as a 5-tuple:

    (type: int, text: str, width: int, frames: list[str]|None, style: str)

BarColumn appends a 6th element (the glyph 5-tuple) and, when it carries an
animated leading-edge tip, a 7th (the list of tip frames). CallbackColumn's
6th element is its Python callable.

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
    COL_POSTFIX,
)
from .style import style as _style

# Lazily-bound helpers, cached on first use. Keeping these out of the
# module-level import list means `import barflow.columns` does not pull in
# bar_styles / spinners (preserving cold-import laziness for text-only
# column sets), while caching the resolved object avoids re-running the
# `from . import X` machinery (_handle_fromlist / parent) on every factory
# call — measurable on repeated Progress construction.
_to_tuple = None   # bar_styles.to_tuple
_tip_for = None    # bar_styles.tip_for
_SPINNERS = None   # spinners.SPINNERS


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


def BarColumn(width=40, *, style="cyan", color=None, glyphs="smooth", tip=None):
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
    `tip`     animated leading-edge frames (alive-progress-style motion):
              the boundary cell cycles through them while the bar is
              incomplete. `None` (default) inherits the glyph style's
              built-in tip if it has one; pass a list of single-cell
              strings to set one explicitly, a style name to borrow that
              style's tip, or `[]` to force a static edge.
    `color`   backward-compat alias for `style`.
    """
    global _to_tuple, _tip_for
    if _to_tuple is None:
        from .bar_styles import to_tuple as _tt, tip_for as _tf
        _to_tuple = _tt
        _tip_for = _tf
    g = _to_tuple(glyphs)
    # -1 is the on-the-wire sentinel for "flex width". Keeps the column
    # tuple schema flat — the C core detects width < 0 and flips the
    # column's flex flag on.
    w = -1 if width is None else int(width)
    # Resolve the tip: None inherits the glyph style's built-in tip; a str
    # borrows another style's; anything else is taken as an explicit frame
    # list (so `tip=[]` deliberately disables an inherited one).
    if tip is None:
        tip_frames = _tip_for(glyphs)
    elif isinstance(tip, str):
        tip_frames = _tip_for(tip)
    else:
        tip_frames = list(tip)
    base = (COL_BAR, "", w, None, _resolve(style, color), g)
    # Emit the 7-tuple form only when a tip exists so tip-less bars keep the
    # exact 6-tuple wire shape the rest of the code (and tests) expect.
    return base + (tip_frames,) if tip_frames else base


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
        global _SPINNERS
        if _SPINNERS is None:
            from .spinners import SPINNERS as _S
            _SPINNERS = _S
        frames = _SPINNERS.get(name, _SPINNERS["dots"])
    return (COL_SPINNER, "", 0, list(frames), _resolve(style, color))


def PostfixColumn(*, style=None, color=None):
    """The task's postfix string (set via `Progress.set_postfix(**fields)` or
    `set_postfix_str(task_id, text)`). Renders nothing until a postfix is set,
    and self-prefixes a single space so it can trail other columns cleanly —
    the default column set already ends with one, so `set_postfix` works out
    of the box without composing a custom layout.
    """
    return (COL_POSTFIX, "", 0, None, _resolve(style, color))


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
    columns, 6-tuple for BarColumn with glyphs, 7-tuple for a BarColumn
    that also carries an animated tip) are passed through.
    """
    out = []
    for c in columns:
        t = type(c)
        if t is str:
            out.append((COL_TEXT, c, 0, None, ""))
        elif t is tuple and len(c) in (5, 6, 7):
            out.append(c)
        else:
            raise TypeError(
                f"column must be a factory tuple or str, got {t.__name__}"
            )
    return out


__all__ = [
    "TextColumn", "DescriptionColumn", "BarColumn", "PercentColumn",
    "CountColumn", "RateColumn", "ElapsedColumn", "EtaColumn",
    "SpinnerColumn", "PostfixColumn", "CallbackColumn", "resolve_columns",
]

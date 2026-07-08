"""Python-side Progress subclass — resolves columns and themes before
calling into the C core. Imported lazily by `barflow.__getattr__`.
"""

from __future__ import annotations

from . import _core

# Lazily-bound submodules, cached on first use. Kept out of the top-level
# import list so importing `_progress` (and thus `barflow.Progress`) does not
# eagerly pull in themes/columns; cached so repeated construction does not
# re-run the `from . import X` machinery on every __init__.
_themes_mod = None
_columns_mod = None


class Progress(_core.Progress):
    def __init__(self, *columns, total=None, desc=None, disable=False,
                 min_interval=0.05, theme=None, capture_output=False,
                 align=False, smoothing=0.0, leave=True, unit="it",
                 unit_scale=False, unit_divisor=1000, initial=0, delay=0.0):
        if disable is None:
            from . import _auto_disable
            disable = _auto_disable()
        resolved = None
        if theme is not None and not columns:
            global _themes_mod
            if _themes_mod is None:
                from . import themes as _t
                _themes_mod = _t
            columns = tuple(_themes_mod.get(theme))
        if columns:
            global _columns_mod
            if _columns_mod is None:
                from . import columns as _c
                _columns_mod = _c
            resolved = _columns_mod.resolve_columns(list(columns))

        super().__init__(
            total=total,
            desc=desc,
            min_interval=min_interval,
            disable=disable,
            columns=resolved,
            align=align,
            smoothing=smoothing,
            leave=leave,
            unit=unit,
            unit_scale=unit_scale,
            unit_divisor=float(unit_divisor),
            initial=initial,
            delay=delay,
        )
        self._capture = None
        if capture_output:
            from .hooks import StdoutCapture
            self._capture = StdoutCapture(self, capture_stdout=True, capture_stderr=False)

    def set_postfix(self, task_id=0, /, **fields):
        """Set a task's trailing annotation from `key=value` pairs, tqdm-style.

        `p.set_postfix(loss=0.031, acc=0.98)` renders `loss=0.031, acc=0.98`
        after the bar. Floats are shown with up to 3 significant decimals;
        everything else uses `str()`. Pass a positional `task_id` to target a
        bar other than task 0. For a pre-formatted string use
        `set_postfix_str(task_id, text)` instead.
        """
        parts = []
        for k, v in fields.items():
            if isinstance(v, float):
                parts.append(f"{k}={v:.3g}")
            else:
                parts.append(f"{k}={v}")
        self.set_postfix_str(task_id, ", ".join(parts))

    def __enter__(self):
        r = super().__enter__()
        if self._capture:
            self._capture.install()
        return r

    def __exit__(self, exc_type, exc, tb):
        if self._capture:
            self._capture.uninstall()
        return super().__exit__(exc_type, exc, tb)

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
                 min_interval=0.05, theme=None, capture_output=False):
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
        )
        self._capture = None
        if capture_output:
            from .hooks import StdoutCapture
            self._capture = StdoutCapture(self, capture_stdout=True, capture_stderr=False)

    def __enter__(self):
        r = super().__enter__()
        if self._capture:
            self._capture.install()
        return r

    def __exit__(self, exc_type, exc, tb):
        if self._capture:
            self._capture.uninstall()
        return super().__exit__(exc_type, exc, tb)

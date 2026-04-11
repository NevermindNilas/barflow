"""Python-side Progress subclass — resolves columns and themes before
calling into the C core. Imported lazily by `barflow.__getattr__`.
"""

from __future__ import annotations

from . import _core


class Progress(_core.Progress):
    def __init__(self, *columns, total=None, desc=None, disable=False,
                 min_interval=0.05, theme=None, capture_output=False):
        resolved = None
        if theme is not None and not columns:
            from . import themes as _themes
            columns = tuple(_themes.get(theme))
        if columns:
            from . import columns as _columns
            resolved = _columns.resolve_columns(list(columns))

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
